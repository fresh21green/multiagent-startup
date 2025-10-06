import os, json, shutil, subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import gradio as gr
from gradio.routes import mount_gradio_app
from dotenv import load_dotenv
load_dotenv()
BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
AGENTS_DIR.mkdir(exist_ok=True)
META_FILE = AGENTS_DIR / "workers.json"
if not META_FILE.exists():
    META_FILE.write_text('[]', encoding='utf-8')
app = FastAPI()
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')
templates = Jinja2Templates(directory=str(BASE / 'templates'))
def load_meta():
    try:
        return json.loads(META_FILE.read_text(encoding='utf-8'))
    except:
        return []
def save_meta(meta):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
def slugify(name: str):
    import re
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip()).lower()
@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    meta = load_meta()
    return templates.TemplateResponse('index.html', {'request': request, 'agents': meta})
@app.get('/create_agent', response_class=HTMLResponse)
async def create_agent_page(request: Request):
    return templates.TemplateResponse('create_agent.html', {'request': request})
@app.post('/create_agent')
async def create_agent(request: Request, name: str = Form(...), prompt: str = Form(''), telegram_token: str = Form(''), auto_deploy: str = Form('0')):
    name = name.strip()
    if not name: raise HTTPException(status_code=400, detail='Name required')
    slug = slugify(name)
    dest = AGENTS_DIR / slug
    if dest.exists():
        import datetime
        slug = f"{slug}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        dest = AGENTS_DIR / slug
    dest.mkdir(parents=True, exist_ok=False)
    template = (AGENTS_DIR / 'bot_template.py').read_text(encoding='utf-8')
    safe_prompt = prompt.replace('"""', '\"\"\"')
    worker_code = template.replace('__PROMPT_PLACEHOLDER__', f'"""{safe_prompt}"""')
    if telegram_token and telegram_token.strip():
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', f'TELEGRAM_TOKEN = "{telegram_token.strip()}"')
    else:
        worker_code = worker_code.replace('__TELEGRAM_TOKEN_PLACEHOLDER__', 'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')
    (dest / 'bot.py').write_text(worker_code, encoding='utf-8')
    for fn in ['requirements.txt','render.yaml','.env.example','README_worker.md']:
        src = AGENTS_DIR / fn
        if src.exists(): shutil.copy(src, dest / fn)
    zip_path = AGENTS_DIR / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dest):
            for f in files:
                full = Path(root) / f
                arc = Path(slug) / full.relative_to(dest)
                zf.write(full, arc.as_posix())
    meta = load_meta()
    entry = {'name': name, 'slug': slug, 'created_at': __import__('datetime').datetime.utcnow().isoformat()+'Z', 'zip': f'/download/{zip_path.name}', 'repo':'', 'render_service_id':'', 'deploy_url':'', 'status':'created'}
    meta.append(entry)
    save_meta(meta)
    if auto_deploy == '1':
        script = BASE / 'create_and_push.sh'
        try:
            subprocess.run(['bash', str(script), slug, str(dest)], check=True)
            entry['status'] = 'deploy_in_progress'
            save_meta(meta)
        except Exception as e:
            entry['status'] = 'deploy_failed'
            entry.setdefault('errors', []).append(str(e))
            save_meta(meta)
    return RedirectResponse('/', status_code=303)
@app.get('/download/{name}')
async def download(name: str):
    path = AGENTS_DIR / name
    if path.exists():
        return FileResponse(path, filename=name)
    raise HTTPException(status_code=404, detail='Not found')
@app.post('/api/delete_agent')
async def delete_agent(slug: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e['slug']==slug), None)
    if not entry: raise HTTPException(status_code=404, detail='Not found')
    p = AGENTS_DIR / slug
    if p.exists(): shutil.rmtree(p)
    z = AGENTS_DIR / f"{slug}.zip"
    if z.exists(): z.unlink()
    meta = [e for e in meta if e['slug']!=slug]
    save_meta(meta)
    return JSONResponse({'ok': True})
@app.post('/api/assign_task')
async def assign_task(slug: str = Form(...), task: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e['slug']==slug), None)
    if not entry: raise HTTPException(status_code=404, detail='Worker not found')
    deploy_url = entry.get('deploy_url') or ''
    if not deploy_url: raise HTTPException(status_code=400, detail='Worker not deployed yet. Paste URL or auto-deploy.')
    chat_id = entry.get('test_chat_id') or 123456789
    payload = {'message': {'message_id':1, 'from':{'id':1111,'is_bot':False,'first_name':'Manager'}, 'chat':{'id':int(chat_id),'type':'private'}, 'date': int(__import__('time').time()), 'text': task}}
    try:
        import requests
        resp = requests.post(deploy_url.rstrip('/') + '/webhook', json=payload, timeout=25)
        return JSONResponse({'ok': True, 'status': resp.status_code, 'text': resp.text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Gradio UI
def list_workers():
    return load_meta()
def create_worker_ui(name, prompt, token, auto):
    import requests, os
    data = {'name':name, 'prompt':prompt, 'telegram_token': token, 'auto_deploy': '1' if auto else '0'}
    try:
        resp = requests.post(f'http://127.0.0.1:{os.getenv("PORT","8000")}/create_agent', data=data, allow_redirects=False, timeout=5)
        return 'ok', list_workers()
    except Exception as e:
        return str(e), list_workers()
demo = gr.Blocks()
with demo:
    gr.Markdown('# 🤖 multiagent-manager (Gradio UI)')
    with gr.Tab('Create agent'):
        name = gr.Textbox(label='Name')
        prompt = gr.Textbox(label='Prompt', lines=4)
        token = gr.Textbox(label='Telegram token (optional)')
        auto = gr.Checkbox(label='Auto deploy to GitHub & Render', value=False)
        create_btn = gr.Button('Create agent')
        out = gr.Textbox(label='Result')
        workers_json = gr.JSON(value=list_workers(), label='Workers')
        create_btn.click(lambda n,p,t,a: create_worker_ui(n,p,t,a), inputs=[name,prompt,token,auto], outputs=[out, workers_json])
    with gr.Tab('Workers'):
        workers_view = gr.JSON(value=list_workers(), label='Workers list')
    with gr.Tab('Assign task'):
        sel_slug = gr.Textbox(label='Worker slug')
        task = gr.Textbox(label='Task')
        send_btn = gr.Button('Assign')
        result = gr.Textbox(label='Result')
        def assign_local(slug, task):
            import requests, os
            try:
                r = requests.post(f'http://127.0.0.1:{os.getenv("PORT","8000")}/api/assign_task', data={'slug':slug,'task':task}, timeout=10)
                return r.text
            except Exception as e:
                return str(e)
        send_btn.click(assign_local, [sel_slug, task], result)
mount_gradio_app(app, demo, path='/gradio')
if __name__ == '__main__':
    import uvicorn, os
    port = int(os.getenv('PORT', 8000))
    uvicorn.run('main:app', host='0.0.0.0', port=port)
