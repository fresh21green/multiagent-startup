from core.auth import get_current_user


import sys
import os, re, shutil, markdown, logging, json
sys.path.append(os.path.dirname(__file__))

import asyncio
from pathlib import Path
import importlib.util
from fastapi import APIRouter, Request, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from utils import load_meta, save_meta, call_agent_local, call_agent_remote, save_memory, ensure_user_root, filter_meta_by_owner
from mcp import load_context, save_context



logger = logging.getLogger("manager")
router = APIRouter()

BASE = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE / "agents"
TEMPLATES_DIR = BASE / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def slugify(name: str):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip()).lower()

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Главная страница: доступна всем, но frontend перенаправит неавторизованных на /login.
    """
    meta = load_meta()

    folders = {}
    for a in meta:
        folder = a.get("folder") or "root"
        if a.get("is_folder"):
            folders.setdefault(folder, [])
        else:
            folders.setdefault(folder, []).append(a)

    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/folder/{folder_name}")
async def get_folder_agents(folder_name: str, user: str = Depends(get_current_user)):
    meta = load_meta()
    agents = [
        a for a in meta
        if not a.get("is_folder", False)
        and a.get("folder") == folder_name
        and a.get("owner") == user
    ]
    return JSONResponse(agents)


@router.get("/agent/{slug}", response_class=HTMLResponse)
async def view_agent(request: Request, slug: str):
    """
    HTML-страница агента.
    Доступна без токена, чтобы можно было открыть через обычную ссылку.
    Реальные данные агента подтягиваются фронтом с /api/agent/{slug},
    где уже стоит проверка Depends(get_current_user).
    """
    return templates.TemplateResponse("agent.html", {"request": request, "slug": slug})
    

@router.get("/api/agent/{slug}")
async def get_agent_data(slug: str, user: str = Depends(get_current_user)):
    """Возвращает данные агента (только для владельца)."""
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug and a.get("owner") == user), None)
    if not agent:
        raise HTTPException(status_code=403, detail="Access denied")

    bot_file = Path(agent["path"]) / "bot.py"
    prompt = ""
    if bot_file.exists():
        text = bot_file.read_text(encoding="utf-8")
        m = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.DOTALL)
        if m:
            prompt = m.group(1).strip()

    return {
        "name": agent["name"],
        "folder": agent.get("folder", "root"),
        "status": agent.get("status", "ready"),
        "prompt": prompt,
        "path": agent["path"],
    }


@router.post('/create_agent')
async def create_agent(
    request: Request,
    name: str = Form(...),
    prompt: str = Form(''),
    telegram_token: str = Form(''),
    folder: str = Form('root'),
    team_bias: float = Form(0.5),
    user: str = Depends(get_current_user)
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name required')

    slug = slugify(name)
    folder = folder.strip() or "root"

    meta = load_meta()
    # Фильтрация только по текущему пользователю
    user_meta = filter_meta_by_owner(meta, user)

    if any(a.get("slug") == slug or a.get("name").lower() == name.lower() for a in user_meta):
        return JSONResponse({"ok": False, "error": f"Сотрудник '{name}' уже существует"})

    # 🔹 создаём личную директорию пользователя
    user_root = ensure_user_root(user)
    dest = user_root / folder / slug

    try:
        dest.mkdir(parents=True, exist_ok=False)
    except Exception as e:
        logger.exception("Ошибка создания директории агента: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # === Создание bot.py ===
    template = (BASE / 'bot_template.py').read_text(encoding='utf-8')
    safe_prompt = prompt.replace('"""', '\"\"\"')
    worker_code = template.replace('__PROMPT_PLACEHOLDER__', f'"""{safe_prompt}"""')

    if telegram_token.strip():
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__',
                                          f'TELEGRAM_TOKEN = "{telegram_token.strip()}"')
    else:
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__',
                                          'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')

    (dest / 'bot.py').write_text(worker_code, encoding='utf-8')

    # Копируем шаблонные файлы
    for fn in ['requirements.txt', '.env.example', 'README_worker.md']:
        src = BASE / 'agents' / fn
        if src.exists():
            shutil.copy(src, dest / fn)

    # === Добавляем запись в agents.json ===
    entry = {
        "name": name,
        "slug": slug,
        "folder": folder,
        "is_folder": False,
        "owner": user,  # ✅ теперь есть владелец
        "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        "path": str(dest),
        "deploy_url": "",
        "status": "created"
    }
    meta.append(entry)
    save_meta(meta)

    # === Telegram webhook (если указан токен) ===
    if telegram_token.strip():
        try:
            import requests, os as _os
            BASE_URL = _os.getenv("BASE_URL") or "https://your-domain.com"
            webhook_url = f"{BASE_URL.rstrip('/')}/agents/{folder}/{slug}/webhook"
            r = requests.get(
                f"https://api.telegram.org/bot{telegram_token}/setWebhook",
                params={"url": webhook_url},
                timeout=10
            )
            if r.status_code == 200 and r.json().get("ok"):
                entry["deploy_url"] = webhook_url
                save_meta(meta)
            else:
                logger.warning("Не удалось установить webhook: %s", r.text)
        except Exception as e:
            logger.exception("Ошибка при установке Telegram webhook: %s", e)

    return JSONResponse({"ok": True, "message": f"Сотрудник '{name}' успешно создан"})


@router.post("/update_agent/{slug}")
async def update_agent(
    request: Request,
    slug: str,
    name: str = Form(...),
    prompt: str = Form(''),
    telegram_token: str = Form(''),
    deploy_url: str = Form(''),
    folder: str = Form(''),
    team_bias: float = Form(0.5),
    user: str = Depends(get_current_user)
):
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug and a.get("owner") == user), None)
    if not agent:
        raise HTTPException(status_code=403, detail="Access denied")

    agent.update({
        "name": name.strip(),
        "deploy_url": deploy_url.strip(),
        "folder": folder.strip() or agent.get("folder", "root"),
        "team_bias": team_bias
    })

    # обновляем PROMPT в bot.py
    bot_file = Path(agent["path"]) / "bot.py"
    if bot_file.exists():
        code = bot_file.read_text(encoding="utf-8")
        code = re.sub(r'PROMPT\s*=\s*""".*?"""', f'PROMPT = """{prompt.strip()}"""', code, flags=re.DOTALL)
        bot_file.write_text(code, encoding="utf-8")

    save_meta(meta)
    logger.info(f"✅ Обновлены данные агента {slug}")
    return JSONResponse({"ok": True, "message": f"Изменения агента '{slug}' сохранены"})



@router.post("/create_folder")
async def create_folder(name: str = Form(...), user: str = Depends(get_current_user)):
    folder = name.strip()
    if not folder:
        return JSONResponse({"ok": False, "error": "empty_name"})

    # 🔹 создаём личную директорию пользователя
    user_root = ensure_user_root(user)
    folder_path = user_root / folder

    if folder_path.exists():
        return JSONResponse({"ok": False, "error": "exists"})

    folder_path.mkdir(parents=True, exist_ok=True)

    meta = load_meta()
    if not any(a.get("is_folder") and a.get("folder") == folder and a.get("owner") == user for a in meta):
        meta.append({
            "folder": folder,
            "is_folder": True,
            "name": folder,
            "slug": f"folder_{folder}_{user}",
            "owner": user,  # ✅ владелец
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z'
        })
        save_meta(meta)

    return JSONResponse({"ok": True, "folder": folder})


@router.post('/delete_folder')
async def delete_folder(name: str = Form(...), user: str = Depends(get_current_user)):
    """
    Удаляет каталог текущего пользователя, если он пуст,
    и убирает запись из agents.json.
    """
    import json
    folder = name.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="Не указано имя каталога")

    user_root = ensure_user_root(user)
    folder_path = user_root / folder
    print(f"🟢 Удаление каталога '{folder}' пользователя '{user}' → {folder_path}")

    if not folder_path.exists():
        print(f"⚠️ Папка {folder_path} не найдена")
        raise HTTPException(status_code=404, detail=f"Каталог '{folder}' не найден")

    meta = load_meta()

    # Проверяем, есть ли агенты в каталоге пользователя
    agents_in_folder = [
        a for a in meta
        if not a.get("is_folder", False)
        and a.get("folder") == folder
        and a.get("owner") == user
    ]
    if agents_in_folder:
        count = len(agents_in_folder)
        print(f"❌ Каталог '{folder}' пользователя '{user}' не пуст ({count} агентов)")
        return JSONResponse({"ok": False, "error": "not_empty", "count": count})

    try:
        # Удаляем сам каталог с диска
        shutil.rmtree(folder_path, ignore_errors=True)

        # Фильтруем записи meta
        new_meta = [
            a for a in meta
            if not (
                (a.get("is_folder") and a.get("folder") == folder and a.get("owner") == user)
                or (a.get("folder") == folder and a.get("owner") == user)
                or (a.get("slug") == f"folder_{folder}_{user}")
            )
        ]

        removed = len(meta) - len(new_meta)
        save_meta(new_meta)
        print(f"✅ Каталог '{folder}' ({user}) удалён. Убрано {removed} записей из agents.json")

        return JSONResponse({"ok": True, "folder": folder, "removed": removed})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)









@router.get('/download/{name}')
async def download(name: str):
    p = AGENTS_DIR / f"{name}.zip"
    if p.exists():
        return FileResponse(p, filename=p.name)
    raise HTTPException(status_code=404, detail='Not found')

def parse_llm_response(res):
    """
    Преобразует ответ агента (строку) в HTML.
    Если в тексте есть Markdown — конвертирует его.
    Если текст уже HTML — вставляет как есть.
    """
    import re
    from markdown2 import markdown

    # если res — dict, достаём текст
    content = res.get("html") if isinstance(res, dict) else str(res)

    # если выглядит как готовый HTML — не трогаем
    if content.strip().startswith("<") or "</" in content:
        html_text = content
    else:
        # иначе рендерим Markdown
        html_text = markdown(content, extras=["fenced-code-blocks", "tables"])

    # извлекаем изображения (если есть base64)
    base64_images = re.findall(r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", content)

    return {"html": html_text, "images": base64_images}


@router.post("/assign_task_folder")
async def assign_task_folder(
    task: str = Form(...),
    folder: str = Form(...),
    user: str = Depends(get_current_user)
):
    """
    🧩 Поручает задачу всем агентам в указанном каталоге.
    Каждый агент получает свою роль (PROMPT), общий контекст коллег и задачу.
    """
    from core.mcp import load_context, save_context, merge_contexts
    from utils import call_agent_with_context, save_memory
    import json, asyncio
    logger.info(f"[assign_task_folder] {user=} folder='{folder}' task='{task}'")

    meta = load_meta()
    agents_in_folder = [
        a for a in meta
        if a.get("folder") == folder
        and not a.get("is_folder")
        and a.get("owner") == user
    ]
    if not agents_in_folder:
        return JSONResponse({"ok": False, "error": f"Нет сотрудников в каталоге '{folder}'"}, status_code=404)

    # 🧠 Групповой контекст
    all_contexts = {a["slug"]: load_context(a["slug"]) for a in agents_in_folder}
    merged_context = merge_contexts(*all_contexts.values())
    context_text = json.dumps(merged_context, ensure_ascii=False, indent=2)

    results = []

    async def handle(agent):
        slug = agent["slug"]
        try:
            enriched_task = (
                f"{task}\n\n"
                f"📘 Контексты коллег:\n{context_text}\n\n"
                f"Ответь с учётом своей роли и общего контекста команды."
            )

            res = await call_agent_with_context(agent, enriched_task)
            result_text = res.get("result") if isinstance(res, dict) else str(res)

            save_memory(Path(agent["path"]), {"task": f"GroupTask: {task}", "result": result_text})
            ctx = load_context(slug)
            ctx.update({
                "last_group_task": task,
                "last_group_result": result_text,
                "colleague_contexts": list(all_contexts.keys())
            })
            save_context(slug, ctx)

            results.append({"agent": slug, "result": result_text})
        except Exception as e:
            logger.exception(f"Ошибка у агента {slug}: {e}")
            results.append({"agent": slug, "error": str(e)})

    await asyncio.gather(*[handle(a) for a in agents_in_folder])
    return JSONResponse({"ok": True, "folder": folder, "results": results})





@router.post("/assign_task")
async def assign_task(
    slug: str = Form(...),
    task: str = Form(...),
    user: str = Depends(get_current_user)
):
    """Отправляет индивидуальную задачу агенту текущего пользователя."""
    import traceback, json
    logger.info("Назначаем задачу '%s' агенту %s", task, slug)

    try:
        meta = load_meta()
        entry = next((e for e in meta if e["slug"] == slug and e.get("owner") == user), None)
        if not entry:
            raise HTTPException(status_code=403, detail="Access denied")

        from utils import call_agent_with_context
        res = await call_agent_with_context(entry, task)

        # 🧠 Нормализуем результат
        if isinstance(res, dict):
            raw_text = res.get("result") or str(res)
        else:
            raw_text = str(res or "").strip()

        if not raw_text:
            raw_text = "(пустой ответ от агента)"

        # 🔧 Безопасная обработка JSON
        if raw_text.lstrip().startswith(("{", "[")):
            try:
                parsed_json = json.loads(raw_text)
                raw_text = json.dumps(parsed_json, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning(f"[assign_task] ответ агента невалидный JSON, обрабатываю как текст")

        # 🧩 Формируем HTML для вывода
        from markdown2 import markdown
        rendered_html = markdown(raw_text, extras=["fenced-code-blocks", "tables"])

        parsed = {"html": rendered_html}
        entry["last_task"] = {"task": task, "result": parsed}
        save_meta(meta)

        return JSONResponse({"ok": True, "agent": slug, "result": parsed})

    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
        logger.exception("Ошибка при назначении задачи агенту %s: %s", slug, error_text)
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": error_text}, status_code=500)

    



@router.post("/assign_task_to_folder")
async def assign_task_to_folder(
    folder: str = Form(...),
    task: str = Form(...),
    user: str = Depends(get_current_user)
):
    """Назначает задачу всем агентам пользователя в указанном каталоге."""
    meta = load_meta()
    agents = [
        a for a in meta
        if not a.get("is_folder", False)
        and a.get("folder") == folder
        and a.get("owner") == user
    ]

    if not agents:
        return JSONResponse({"ok": False, "error": f"Нет сотрудников в каталоге '{folder}'"}, status_code=404)

    results = []
    for agent in agents:
        slug = agent.get("slug")
        try:
            res = await assign_task(slug=slug, task=task, user=user)
            if isinstance(res, JSONResponse):
                body = res.body.decode()
                res = json.loads(body) if body.strip() else {"ok": False, "error": "empty response"}
            results.append({"agent": slug, "result": res})
        except Exception as e:
            results.append({"agent": slug, "error": str(e)})

    return JSONResponse({"ok": True, "results": results})



@router.post('/agents/{slug}/webhook')
@router.post('/agents/{folder}/{slug}/webhook')
async def proxy_agent_webhook(request: Request, slug: str, folder: str = None):
    try:
        meta = load_meta()
        if folder:
            agent = next((a for a in meta if a['slug'] == slug and a.get('folder') == folder), None)
        else:
            agent = next((a for a in meta if a['slug'] == slug and not a.get('folder')), None) or                     next((a for a in meta if a['slug'] == slug), None)
        if not agent:
            raise HTTPException(status_code=404, detail='Agent not found')
        bot_path = Path(agent['path']) / 'bot.py'
        if not bot_path.exists():
            raise HTTPException(status_code=404, detail='bot.py not found')
        spec = importlib.util.spec_from_file_location(f"agent_{slug}", str(bot_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data = await request.json()
        if hasattr(mod, 'app'):
            from fastapi.testclient import TestClient
            client = TestClient(mod.app)
            resp = client.post('/webhook', json=data)
            try:
                return JSONResponse(resp.json(), status_code=resp.status_code)
            except Exception:
                return JSONResponse({'ok': True, 'status_code': resp.status_code, 'text': resp.text}, status_code=resp.status_code)
        if hasattr(mod, 'handle_task'):
            text = data.get('message', {}).get('text', '')
            res = mod.handle_task(text)
            return JSONResponse({'ok': True, 'result': res})
        raise HTTPException(status_code=500, detail='No webhook or handler found for agent')
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error proxying webhook for agent %s: %s", slug, e)
        raise HTTPException(status_code=500, detail=str(e))
    
    
from fastapi.responses import JSONResponse

@router.get("/folders")
def get_folders(user: str = Depends(get_current_user)):
    """
    Возвращает список всех каталогов (папок) текущего пользователя.
    Показывает только те, у которых is_folder=True.
    """
    meta = load_meta()
    user_meta = filter_meta_by_owner(meta, user)
    folders = sorted({
        a.get("folder", "root")
        for a in user_meta
        if a.get("is_folder", False)
    })
    return JSONResponse(folders)

@router.get("/agents")
async def list_agents(user: str = Depends(get_current_user)):
    """Возвращает список сотрудников текущего пользователя."""
    try:
        meta = load_meta()
        agents = [
            a for a in meta
            if not a.get("is_folder", False)
            and a.get("owner") == user
        ]
        return JSONResponse(agents)
    except Exception as e:
        logger.exception("Ошибка при получении списка агентов: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    

@router.post("/cleanup_meta")
async def cleanup_meta(user: str = Depends(get_current_user)):
    """
    Очищает agents.json от несуществующих агентов/каталогов
    и удаляет физические папки без записей.
    """
    import json, shutil
    removed = 0
    meta = load_meta()
    user_root = ensure_user_root(user)
    cleaned = []

    for a in meta:
        try:
            if a.get("owner") != user:
                cleaned.append(a)
                continue

            if a.get("is_folder"):
                folder_path = user_root / a.get("folder")
                if not folder_path.exists():
                    removed += 1
                    continue
            else:
                path = Path(a.get("path", ""))
                if not path.exists() or not (path / "bot.py").exists():
                    removed += 1
                    continue
            cleaned.append(a)
        except Exception as e:
            print(f"⚠️ Ошибка при проверке {a.get('name')}: {e}")

    # Удаляем папки, которых нет в JSON
    existing_folders = {a.get("folder") for a in cleaned if a.get("is_folder")}
    for f in user_root.iterdir():
        if f.is_dir() and f.name not in existing_folders:
            try:
                shutil.rmtree(f)
                print(f"🧹 Удалена пустая папка без записи: {f}")
            except Exception as e:
                print(f"⚠️ Не удалось удалить {f}: {e}")

    save_meta(cleaned)
    print(f"✅ Очистка завершена: удалено {removed}, осталось {len(cleaned)}")
    return {"ok": True, "removed": removed, "total": len(cleaned)}


@router.post("/delete_agent")
async def delete_agent(slug: str = Form(...), user: str = Depends(get_current_user)):
    meta = load_meta()
    entry = next((e for e in meta if e["slug"] == slug and e.get("owner") == user), None)
    if not entry:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        p = Path(entry['path'])
        if p.exists():
            shutil.rmtree(p)
        meta = [e for e in meta if not (e['slug'] == slug and e.get("owner") == user)]
        save_meta(meta)
        return JSONResponse({"ok": True, "message": f"Агент '{slug}' удалён"})
    except Exception as e:
        logger.exception("Ошибка при удалении агента: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)




