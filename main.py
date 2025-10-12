import os
import json
import shutil
import markdown
import re
import asyncio
import subprocess
import logging
import importlib.util
from pathlib import Path
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from utils import load_meta, save_meta, call_agent_local, call_agent_remote
from dotenv import load_dotenv

# Загружаем переменные окружения (.env)
load_dotenv()

# --- ПУТИ ---
BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
LOGS_DIR = BASE / "logs"
AGENTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

META_FILE = AGENTS_DIR / "agents.json"
if not META_FILE.exists():
    META_FILE.write_text("[]", encoding="utf-8")

# --- ЛОГИРОВАНИЕ ---
logger = logging.getLogger("manager")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOGS_DIR / "manager.log", encoding="utf-8")
ch = logging.StreamHandler()
fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(fmt)
ch.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(ch)

# --- FASTAPI ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / "static")), name='static')
templates = Jinja2Templates(directory=str(BASE / "templates"))


def slugify(name: str):
    """Создает безопасный slug из имени агента."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip()).lower()


# --- ГЛАВНАЯ СТРАНИЦА ---
@app.get("/")
async def index(request: Request):
    """Главная страница — список всех агентов."""
    meta = load_meta()
    for agent in meta:
        agent["url"] = f"/agent/{agent['slug']}"
    return templates.TemplateResponse("index.html", {"request": request, "agents": meta})


# --- СОЗДАНИЕ НОВОГО АГЕНТА ---
@app.post('/create_agent')
async def create_agent(request: Request, name: str = Form(...), prompt: str = Form(''), telegram_token: str = Form('')):
    """Создает нового агента на основе шаблона."""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name required')

    slug = slugify(name)
    dest = AGENTS_DIR / slug
    logger.info(f"Создаем агента '{slug}'")

    # Проверка на существование
    if dest.exists():
        import datetime
        slug = f"{slug}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        dest = AGENTS_DIR / slug

    try:
        dest.mkdir(parents=True, exist_ok=False)
    except Exception as e:
        logger.exception("Ошибка создания директории агента: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # --- Формируем код агента из шаблона ---
    template = (BASE / 'bot_template.py').read_text(encoding='utf-8')
    safe_prompt = prompt.replace('"""', '\"\"\"')
    worker_code = template.replace('__PROMPT_PLACEHOLDER__', f'"""{safe_prompt}"""')
    logger.info("worker_code", worker_code)
    if telegram_token.strip():
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', f'TELEGRAM_TOKEN = "{telegram_token.strip()}"')
    else:
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', 'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')

    (dest / 'bot.py').write_text(worker_code, encoding='utf-8')

    # --- Копируем вспомогательные файлы ---
    for fn in ['requirements.txt', '.env.example', 'README_worker.md']:
        src = BASE / 'agents' / fn
        if src.exists():
            shutil.copy(src, dest / fn)

    # --- Обновляем метаданные ---
    meta = load_meta()
    entry = {
        'name': name,
        'slug': slug,
        'created_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'path': str(dest),
        'deploy_url': '',
        'status': 'created'
    }
    meta.append(entry)
    save_meta(meta)
    logger.info("Агент %s успешно создан", slug)
    # --- Устанавливаем Telegram webhook ---
    if telegram_token.strip():
        try:
            import requests
            BASE_URL = os.getenv("BASE_URL") or "https://your-domain.com"
            webhook_url = f"{BASE_URL.rstrip('/')}/agents/{slug}/webhook"
            logger.info("webhook_url", webhook_url)
            response = requests.get(
                f"https://api.telegram.org/bot{telegram_token}/setWebhook",
                params={"url": webhook_url},
                timeout=10
            )
            if response.status_code == 200 and response.json().get("ok"):
                logger.info("Webhook успешно установлен для агента %s: %s", slug, webhook_url)
                entry["deploy_url"] = webhook_url
                save_meta(meta)
            else:
                logger.warning("Не удалось установить webhook: %s", response.text)
        except Exception as e:
            logger.exception("Ошибка при установке Telegram webhook: %s", e)

    return RedirectResponse('/', status_code=303)
    return RedirectResponse('/', status_code=303)


# --- УДАЛЕНИЕ АГЕНТА ---
@app.post('/delete_agent')
async def delete_agent(slug: str = Form(...)):
    """Удаляет агента и его папку."""
    meta = load_meta()
    entry = next((e for e in meta if e['slug'] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail='Not found')

    try:
        p = Path(entry['path'])
        if p.exists():
            shutil.rmtree(p)
            logger.info("Удален агент %s", slug)
    except Exception as e:
        logger.exception("Ошибка при удалении агента: %s", e)

    meta = [e for e in meta if e['slug'] != slug]
    save_meta(meta)
    return RedirectResponse('/', status_code=303)


# --- ПОРУЧЕНИЕ ЗАДАЧ ВСЕМ ---
@app.post("/assign_task_all")
async def assign_task_all(task: str = Form(...)):
    """Поручает одну задачу всем агентам."""
    logger.info("Поручаем задачу всем агентам: %s", task)
    meta = load_meta()
    if not meta:
        return {"ok": False, "error": "no_agents"}

    results = []

    async def handle(entry):
        slug = entry["slug"]
        try:
            if entry.get("deploy_url"):
                res = await call_agent_remote(entry["deploy_url"], task)
            else:
                path = Path(entry.get("path") or "")
                res = await call_agent_local(path, task) if path.exists() else {"ok": False, "error": "no_path"}

            entry["last_task"] = {"task": task, "result": res["result"]}
            results.append({"agent": slug, "result": res["result"]})
        except Exception as e:
            logger.exception(f"Ошибка при поручении агенту {slug}: {e}")
            results.append({"agent": slug, "result": {"ok": False, "error": str(e)}})

    await asyncio.gather(*[handle(e) for e in meta])
    save_meta(meta)
    logger.info("Все агенты завершили выполнение задачи.")
    return JSONResponse({"ok": True, "results": results})


# --- ИНДИВИДУАЛЬНАЯ ЗАДАЧА ---
@app.post("/assign_task")
async def assign_task(slug: str = Form(...), task: str = Form(...)):
    """Отправляет индивидуальную задачу агенту."""
    logger.info("Назначаем задачу '%s' агенту %s", task, slug)
    meta = load_meta()
    entry = next((e for e in meta if e["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Worker not found")

    if entry.get("deploy_url"):
        res = await call_agent_remote(entry["deploy_url"], task)
    else:
        path = Path(entry.get("path") or "")
        res = await call_agent_local(path, task) if path.exists() else {"ok": False, "error": "no_path_or_url"}

    entry["last_task"] = {"task": task, "result": res["result"]}
    save_meta(meta)
    logger.info("Задача для %s завершена", slug)
    return JSONResponse({"ok": True, "agent": slug, "result": res["result"]})


def parse_llm_response(res):
    """Парсит ответ LLM в HTML + base64 изображения."""
    content = getattr(res, 'content', str(res))
    base64_images = re.findall(r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", content)
    html_text = markdown.markdown(content)
    return {"html": html_text, "images": base64_images}


# --- СКАЧИВАНИЕ АГЕНТА ---
@app.get('/download/{name}')
async def download(name: str):
    """Позволяет скачать архив агента."""
    p = AGENTS_DIR / f"{name}.zip"
    if p.exists():
        return FileResponse(p, filename=p.name)
    raise HTTPException(status_code=404, detail='Not found')


if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    logger.info("Запуск менеджера на порту %s", port)
    uvicorn.run('main:app', host='0.0.0.0', port=port)

@app.get("/agent/{slug}", response_class=HTMLResponse)
async def view_agent(request: Request, slug: str):
    """Страница агента — просмотр и редактирование его настроек."""
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Загружаем prompt из bot.py (если есть)
    bot_file = Path(agent["path"]) / "bot.py"
    prompt = ""
    if bot_file.exists():
        text = bot_file.read_text(encoding="utf-8")
        match = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.DOTALL)
        print('match',match,text)
        if match:
            prompt = match.group(1).strip()

    return templates.TemplateResponse(
        "agent.html",
        {"request": request, "agent": agent, "prompt": prompt}
    )


@app.post("/update_agent/{slug}")
async def update_agent(
    request: Request,
    slug: str,
    name: str = Form(...),
    prompt: str = Form(""),
    telegram_token: str = Form(""),
    deploy_url: str = Form("")
):
    """Сохраняет обновлённые данные агента."""
    meta = load_meta()
    agent = next((a for a in meta if a["slug"] == slug), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Обновляем поля
    agent["name"] = name.strip()
    agent["deploy_url"] = deploy_url.strip()

    # Обновляем bot.py (PROMPT и TELEGRAM_TOKEN)
    bot_file = Path(agent["path"]) / "bot.py"
    if bot_file.exists():
        code = bot_file.read_text(encoding="utf-8")
        code = re.sub(r'PROMPT\s*=\s*""".*?"""', f'PROMPT = """{prompt.strip()}"""', code, flags=re.DOTALL)
        if telegram_token.strip():
            code = re.sub(
                r'TELEGRAM_TOKEN\s*=\s*.*',
                f'TELEGRAM_TOKEN = "{telegram_token.strip()}"',
                code
            )
        bot_file.write_text(code, encoding="utf-8")

    save_meta(meta)
    logger.info("Обновлены данные агента %s", slug)
    return RedirectResponse(f"/agent/{slug}", status_code=303)

