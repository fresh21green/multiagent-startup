# import os
# import logging
# import asyncio
# import requests
# from pathlib import Path
# from fastapi import FastAPI, Request, Form, HTTPException
# from fastapi.responses import HTMLResponse, JSONResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates



import os
import json
import shutil
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

load_dotenv()

BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
LOGS_DIR = BASE / "logs"
AGENTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

META_FILE = AGENTS_DIR / "agents.json"
if not META_FILE.exists():
    META_FILE.write_text("[]", encoding="utf-8")

# logging
logger = logging.getLogger("manager")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOGS_DIR / "manager.log", encoding="utf-8")
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(fmt)
ch.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(ch)

app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / "static")), name='static')
templates = Jinja2Templates(directory=str(BASE / "templates"))



def slugify(name: str):
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip()).lower()

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    meta = load_meta()
    return templates.TemplateResponse('index.html', {'request': request, 'agents': meta})

@app.post('/create_agent')
async def create_agent(request: Request, name: str = Form(...), prompt: str = Form(''), telegram_token: str = Form('')):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name required')
    slug = slugify(name)
    dest = AGENTS_DIR / slug
    logger.info("Creating agent '%s' at %s", slug, dest)
    if dest.exists():
        import datetime
        slug = f"{slug}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        dest = AGENTS_DIR / slug
    try:
        dest.mkdir(parents=True, exist_ok=False)
    except Exception as e:
        logger.exception("Failed to create directory for agent: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # create bot.py from template
    template = (BASE / 'bot_template.py').read_text(encoding='utf-8')
    safe_prompt = prompt.replace('"""', '\"\"\"')
    worker_code = template.replace('__PROMPT_PLACEHOLDER__', f'"""{safe_prompt}"""')
    if telegram_token and telegram_token.strip():
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', f'TELEGRAM_TOKEN = "{telegram_token.strip()}"')
    else:
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', 'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')
    try:
        (dest / 'bot.py').write_text(worker_code, encoding='utf-8')
        logger.info("Wrote bot.py for agent %s", slug)
    except Exception as e:
        logger.exception("Failed to write bot.py: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # support files
    for fn in ['requirements.txt', '.env.example', 'README_worker.md']:
        src = BASE / 'agents' / fn
        if src.exists():
            try:
                shutil.copy(src, dest / fn)
            except Exception:
                logger.exception("Failed to copy support file %s", fn)

    # update meta
    meta = load_meta()
    entry = {'name': name, 'slug': slug, 'created_at': __import__('datetime').datetime.utcnow().isoformat()+'Z', 'path': str(dest), 'deploy_url':'', 'status':'created'}
    meta.append(entry)
    save_meta(meta)
    logger.info("Agent %s created and metadata updated", slug)
    return RedirectResponse('/', status_code=303)

@app.post('/delete_agent')
async def delete_agent(slug: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e['slug']==slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail='Not found')
    # delete files
    try:
        p = Path(entry['path'])
        if p.exists():
            shutil.rmtree(p)
            logger.info("Deleted agent directory %s", p)
    except Exception as e:
        logger.exception("Error deleting agent files: %s", e)
    meta = [e for e in meta if e['slug']!=slug]
    save_meta(meta)
    return RedirectResponse('/', status_code=303)

async def call_agent_local(path: Path, task: str):
    # try to import module and call handle_task if exists
    try:
        spec = importlib.util.spec_from_file_location(f"agent_{path.name}", str(path / 'bot.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, 'handle_task'):
            logger.info("Calling local handle_task for %s", path.name)
            res = mod.handle_task(task)
            return {'ok': True, 'source': 'local', 'result': res}
        else:
            logger.warning("Local module has no handle_task: %s", path)
            return {'ok': False, 'error': 'no_handle_task'}
    except Exception as e:
        logger.exception("Error calling local agent: %s", e)
        return {'ok': False, 'error': str(e)}

async def call_agent_remote(url: str, task: str):
    import requests
    try:
        payload = {'message': {'message_id':1, 'from':{'id':1111,'is_bot':False,'first_name':'Manager'}, 'chat':{'id':123456,'type':'private'}, 'date': int(__import__('time').time()), 'text': task}}
        r = requests.post(url.rstrip('/') + '/webhook', json=payload, timeout=20)
        logger.info("Remote agent %s responded with status %s", url, r.status_code)
        return {'ok': True, 'source': 'remote', 'status': r.status_code, 'text': r.text}
    except Exception as e:
        logger.exception("Error calling remote agent: %s", e)
        return {'ok': False, 'error': str(e)}

# @app.post('/assign_task')
# async def assign_task(slug: str = Form(...), task: str = Form(...)):
#     logger.info("Assign task '%s' to %s", task, slug)
#     meta = load_meta()
#     entry = next((e for e in meta if e['slug']==slug), None)
#     if not entry:
#         raise HTTPException(status_code=404, detail='Worker not found')
#     # prefer remote URL
#     if entry.get('deploy_url'):
#         res = await call_agent_remote(entry['deploy_url'], task)
#     else:
#         path = Path(entry.get('path') or '') 
#         if path.exists():
#             res = await call_agent_local(path, task)
#         else:
#             res = {'ok': False, 'error': 'no_path_or_url'}
#     # attach log to meta
#     entry.setdefault('last_task', {}) 
#     entry['last_task'] = {'task': task, 'result': res}
#     save_meta(meta)
#     return JSONResponse(res)
@app.post("/assign_task_all")
async def assign_task_all(task: str = Form(...)):
    """Отправить одну задачу всем сотрудникам"""
    logger.info("Поручаем задачу всем сотрудникам: %s", task)
    meta = load_meta() 
    if not meta:
        logger.warning("Нет сотрудников для поручения задачи.")
        return {"ok": False, "error": "no_agents"}

    results = []

    async def handle(entry):
        slug = entry["slug"]
        logger.info(f" → Отправляем задачу агенту {slug}")
        try:
            if entry.get("deploy_url"):
                res = await call_agent_remote(entry["deploy_url"], task)
            else:
                path = Path(entry.get("path") or "")
                res = await call_agent_local(path, task) if path.exists() else {"ok": False, "error": "no_path"}
            entry["last_task"] = {"task": task, "result": res}
            results.append({"agent": slug, "result": res})
        except Exception as e:
            logger.exception(f"Ошибка при поручении агенту {slug}: {e}")
            results.append({"agent": slug, "result": {"ok": False, "error": str(e)}})

    await asyncio.gather(*[handle(e) for e in meta])
    save_meta(meta)
    logger.info("Все сотрудники завершили выполнение задачи.")
    # return {"ok": True, "results": results}
    return JSONResponse({"ok": True, "results": results})

@app.post("/assign_task")
async def assign_task(slug: str = Form(...), task: str = Form(...)):
    """Отправка индивидуальной задачи сотруднику"""
    logger.info("Assign task '%s' to %s", task, slug)
    meta = load_meta()
    entry = next((e for e in meta if e["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Worker not found")

    if entry.get("deploy_url"):
        res = await call_agent_remote(entry["deploy_url"], task)
    else:
        path = Path(entry.get("path") or "")
        if path.exists():
            res = await call_agent_local(path, task)
        else:
            res = {"ok": False, "error": "no_path_or_url"}

    entry["last_task"] = {"task": task, "result": res}
    save_meta(meta)
    logger.info("Task completed for %s", slug,res)
    # return JSONResponse(res)
    return JSONResponse({"ok": True, "agent": slug, "result": res})

@app.get('/download/{name}')
async def download(name: str):
    p = AGENTS_DIR / f"{name}.zip"
    if p.exists():
        return FileResponse(p, filename=p.name)
    raise HTTPException(status_code=404, detail='Not found')

if __name__ == '__main__':
    import uvicorn, os
    port = int(os.getenv('PORT', 8000))
    logger.info("Starting manager on port %s", port)
    uvicorn.run('main:app', host='0.0.0.0', port=port)
