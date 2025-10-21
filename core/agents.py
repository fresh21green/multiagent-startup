import sys
import os, re, shutil, markdown, logging
sys.path.append(os.path.dirname(__file__))

import asyncio
from pathlib import Path
import importlib.util
from fastapi import APIRouter, Request, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from utils import load_meta, save_meta, call_agent_local, call_agent_remote, save_memory
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
    meta = load_meta()

    root_folder_path = AGENTS_DIR / "root"
    root_folder_path.mkdir(exist_ok=True)
    if not any(a.get("is_folder") and a.get("folder") == "root" for a in meta):
        meta.append({
            "folder": "root", "is_folder": True, "name": "root", "slug": "folder_root",
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z'
        })
        save_meta(meta)

    if not any(a.get("slug") == "assistant_default" for a in meta):
        default_path = root_folder_path / "assistant_default"
        default_path.mkdir(parents=True, exist_ok=True)
        (default_path / "bot.py").write_text(
            'def handle_task(task: str):\n'
            '    return f"🤖 Ассистент получил задачу: {task}"\n',
            encoding="utf-8"
        )
        meta.append({
            "name": "Ассистент", "slug": "assistant_default", "folder": "root", "is_folder": False,
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            "path": str(default_path), "deploy_url": "", "status": "ready"
        })
        save_meta(meta)

    folders = {}
    agents_root = []
    for agent in meta:
        folder = agent.get("folder") or "root"
        if agent.get("is_folder"):
            folders.setdefault(folder, [])
        else:
            folders.setdefault(folder, []).append(agent)
            if folder == "root":
                agents_root.append(agent)

    return templates.TemplateResponse("index.html", {"request": request, "folders": folders, "agents": agents_root})

@router.get("/folder/{folder_name}")
async def get_folder_agents(folder_name: str):
    """
    Возвращает всех агентов, принадлежащих заданному каталогу.
    """
    meta = load_meta()
    folder_name = folder_name.strip().lower()

    agents = []
    # for a in meta:
    #     folder_value = (a.get("folder") or "root").strip().lower().rstrip("/")
    #     if folder_value == folder_name and not a.get("is_folder"):
    #         agents.append(a)
     # 🧩 Возвращаем всех агентов, чья folder == нужная
    agents = [
        a for a in meta
        if not a.get("is_folder", False)
        and a.get("folder", "root") == folder_name
    ]

    return JSONResponse(agents)

@router.get("/agent/{slug}", response_class=HTMLResponse)
async def view_agent(request: Request, slug: str):
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    bot_file = Path(agent["path"]) / "bot.py"
    prompt = ""
    if bot_file.exists():
        text = bot_file.read_text(encoding="utf-8")
        m = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.DOTALL)
        if m:
            prompt = m.group(1).strip()
    # Список всех папок для выпадающего списка
    folders = [a["folder"] for a in meta if a.get("is_folder")]

    return templates.TemplateResponse(
        "agent.html",
        {"request": request, "agent": agent, "prompt": prompt, "folders": folders}
    )

@router.post('/create_agent')
async def create_agent(
    request: Request,
    name: str = Form(...),
    prompt: str = Form(''),
    telegram_token: str = Form(''),
    folder: str = Form('root')
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name required')

    slug = slugify(name)
    folder = folder.strip() or "root"
    dest = AGENTS_DIR / folder / slug

    meta = load_meta()

    # ✅ Проверка: существует ли агент с таким именем или slug
    if any(a.get("slug") == slug or a.get("name").lower() == name.lower() for a in meta):
        return JSONResponse({"ok": False, "error": f"Сотрудник с именем '{name}' уже существует"})

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

    # Копируем шаблонные файлы (если есть)
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
    folder: str = Form('')
):
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent["name"] = name.strip()
    agent["deploy_url"] = deploy_url.strip()

    # 🟢 сохраняем старую папку, если новая не указана
    new_folder = folder.strip() or agent.get("folder", "root")
    agent["folder"] = new_folder

    # Обновляем bot.py (PROMPT и TELEGRAM_TOKEN)
    bot_file = Path(agent["path"]) / "bot.py"
    if bot_file.exists():
        code = bot_file.read_text(encoding="utf-8")
        code = re.sub(r'PROMPT\s*=\s*""".*?"""', f'PROMPT = """{prompt.strip()}"""', code, flags=re.DOTALL)
        if telegram_token.strip():
            code = re.sub(r'TELEGRAM_TOKEN\s*=\s*.*', f'TELEGRAM_TOKEN = "{telegram_token.strip()}"', code)
        bot_file.write_text(code, encoding="utf-8")

    save_meta(meta)
    logger.info("Обновлены данные агента %s", slug)
    return JSONResponse({"ok": True, "message": f"Обновлены данные агента '{slug}'"})


@router.post("/create_folder")
async def create_folder(name: str = Form(...)):
    folder = name.strip()
    if not folder:
        return JSONResponse({"ok": False, "error": "empty_name"})
    folder_path = AGENTS_DIR / folder
    if folder_path.exists():
        return JSONResponse({"ok": False, "error": "exists"})
    folder_path.mkdir(parents=True, exist_ok=True)
    meta = load_meta()
    if not any(a.get("is_folder") and a.get("folder") == folder for a in meta):
        meta.append({"folder": folder, "is_folder": True, "name": folder,
                     "slug": f"folder_{folder}",
                     "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',})
        save_meta(meta)
    return JSONResponse({"ok": True, "folder": folder})

@router.post('/delete_agent')
async def delete_agent(slug: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e['slug'] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail='Not found')
    try:
        p = Path(entry['path'])
        if p.exists():
            shutil.rmtree(p)
    except Exception as e:
        logger.exception("Ошибка при удалении агента: %s", e)
    meta = [e for e in meta if e['slug'] != slug]
    save_meta(meta)
    return JSONResponse({"ok": True, "message": f"Агент '{slug}' успешно удалён"})

@router.post('/delete_folder')
async def delete_folder(name: str = Form(...)):
    """Удаляет каталог, если он пустой, и запись из agents.json"""
    folder = name.encode('latin1').decode('utf-8').strip()
    folder_path = AGENTS_DIR / folder
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Каталог не найден")

    # Проверяем, есть ли агенты внутри каталога
    meta = load_meta()
    agents_in_folder = [a for a in meta if a.get("folder") == folder and not a.get("is_folder")]
    if agents_in_folder:
        return JSONResponse({"ok": False, "error": "not_empty", "count": len(agents_in_folder)})

    try:
        # Удаляем папку с диска
        shutil.rmtree(folder_path)

        # Удаляем записи о каталоге и всех агентах внутри (на всякий случай)
        new_meta = [a for a in meta if a.get("folder") != folder]
        save_meta(new_meta)

        logger.info(f"✅ Удалён каталог '{folder}' и его запись из agents.json")
        return JSONResponse({"ok": True, "folder": folder})
    except Exception as e:
        logger.exception(f"Ошибка удаления каталога {folder}: {e}")
        return JSONResponse({"ok": False, "error": str(e)}) 


@router.get('/download/{name}')
async def download(name: str):
    p = AGENTS_DIR / f"{name}.zip"
    if p.exists():
        return FileResponse(p, filename=p.name)
    raise HTTPException(status_code=404, detail='Not found')

def parse_llm_response(res):
    content = getattr(res, 'content', str(res))
    base64_images = re.findall(r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", content)
    import markdown2
    html_text = markdown2.markdown(content, safe_mode="escape")
    return {"html": html_text, "images": base64_images}

@router.post("/assign_task_folder")
async def assign_task_folder(task: str = Form(...), folder: str = Form(...)):
    """
    Поручает задачу всем агентам в указанном каталоге.
    Форматирует ответы через parse_llm_response (единый стиль).
    """
    logger.info(f"Поручаем задачу '{task}' всем агентам в каталоге '{folder}'")

    meta = load_meta()
    if not meta:
        return JSONResponse({"ok": False, "error": "no_agents"})

    # выбираем агентов только из нужного каталога
    agents_in_folder = [a for a in meta if a.get("folder") == folder and not a.get("is_folder")]
    if not agents_in_folder:
        return JSONResponse({"ok": False, "error": f"no_agents_in_folder_{folder}"})

    results = []

    async def handle(entry):
        slug = entry["slug"]
        try:
            path = Path(entry.get("path") or "")
            if not (path / "bot.py").exists():
                raise FileNotFoundError(f"bot.py не найден у агента {slug}")

            # Вызов агента
            res = await call_agent_local(path, task)

            # Форматируем через parse_llm_response (единый стиль)
            parsed = parse_llm_response(res["result"]) if isinstance(res, dict) and "result" in res else {"html": str(res), "images": []}
            logger.info(f"parsed result: {parsed}")
            entry["last_task"] = {"task": task, "result": parsed}
            lock = asyncio.Lock()
            async with lock:
                results.append({"agent": slug, "result": parsed})
            
            # Сохраняем память агента
            try:
                save_memory(path, {
                    "date": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                    "task": task,
                    "result": res.get("result") if isinstance(res, dict) else str(res)
                })
            except Exception as e:
                logger.warning(f"Ошибка записи памяти агента {slug}: {e}")

        except Exception as e:
            logger.exception(f"Ошибка при поручении агенту {slug}: {e}")
            results.append({"agent": slug, "result": {"html": f"⚠️ Ошибка: {e}", "images": []}})

    # Запускаем все параллельно
    await asyncio.gather(*[handle(a) for a in agents_in_folder])
    save_meta(meta)

    logger.info(f"Все агенты в каталоге '{folder}' завершили выполнение задачи.")
    return JSONResponse({"ok": True, "folder": folder, "results": results})


@router.post("/assign_task")
async def assign_task(slug: str = Form(...), task: str = Form(...)):
    """Отправляет индивидуальную задачу агенту и всегда возвращает корректный JSON."""
    import traceback
    logger.info("Назначаем задачу '%s' агенту %s", task, slug)
    try:
        meta = load_meta()
        entry = next((e for e in meta if e["slug"] == slug), None)
        if not entry:
            raise HTTPException(status_code=404, detail="Worker not found")

        # --- вызов агента ---
        if entry.get("deploy_url"):
            res = await call_agent_remote(entry["deploy_url"], task)
        else:
            path = Path(entry.get("path") or "")
            if not path.exists():
                raise FileNotFoundError(f"Папка агента {path} не найдена")
            res = await call_agent_local(path, task)

        # --- безопасное парсирование ---
        parsed = parse_llm_response(res.get("result", str(res)) if isinstance(res, dict) else str(res))
        # Загружаем старый контекст
        ctx = load_context(slug)
        ctx["last_task"] = task
        ctx["last_result"] = parsed
        ctx["interaction_count"] = ctx.get("interaction_count", 0) + 1

        # сохраняем новый контекст
        save_context(slug, ctx)
        # return {"ok": True, "result": result, "context": ctx}
        entry["last_task"] = {"task": task, "result": parsed}
        save_meta(meta)

        return JSONResponse({"ok": True, "agent": slug, "result": parsed})

    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
        logger.exception("Ошибка при назначении задачи агенту %s: %s", slug, error_text)
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": error_text}, status_code=500)



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
from utils import load_meta

@router.get("/folders")
def get_folders():
    """Возвращает список всех каталогов (папок)."""
    meta = load_meta()
    folders = sorted({a.get("folder", "root") for a in meta})
    return JSONResponse(folders)

@router.get('/agents')
async def list_agents():
    """
    Возвращает список всех сотрудников (агентов) в формате JSON.
    Используется для проверки уникальности имён и фронтенд-интерфейса.
    """
    try:
        meta = load_meta()
        agents = [a for a in meta if not a.get("is_folder", False)]
        return JSONResponse(agents)
    except Exception as e:
        logger.exception("Ошибка при получении списка агентов: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


