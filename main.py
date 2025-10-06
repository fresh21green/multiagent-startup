# main.py
import os
import re
import json
import shutil
import zipfile
import datetime
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
TEMPLATE_FILE = AGENTS_DIR / "bot_template.py"
META_FILE = AGENTS_DIR / "workers.json"

AGENTS_DIR.mkdir(exist_ok=True)
if not META_FILE.exists():
    META_FILE.write_text("[]", encoding="utf-8")

app = FastAPI()

# mount static (CSS, images, etc.)
STATIC_DIR = BASE / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(BASE / "templates"))

# helper funcs
def load_meta():
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_meta(meta):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def slugify(name: str):
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
    return s.lower()

# pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    meta = load_meta()
    return templates.TemplateResponse("index.html", {"request": request, "agents": meta})

@app.get("/create_agent", response_class=HTMLResponse)
async def create_agent_page(request: Request):
    return templates.TemplateResponse("create_agent.html", {"request": request})

@app.post("/create_agent")
async def create_agent(
    request: Request,
    name: str = Form(...),
    prompt: str = Form(""),
    telegram_token: str = Form(""),
    auto_deploy: str = Form("0")
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    slug = slugify(name)
    dest = AGENTS_DIR / slug
    if dest.exists():
        ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        slug = f"{slug}_{ts}"
        dest = AGENTS_DIR / slug
    dest.mkdir(parents=True, exist_ok=False)

    if not TEMPLATE_FILE.exists():
        raise HTTPException(status_code=500, detail="agent template missing")

    template_text = TEMPLATE_FILE.read_text(encoding="utf-8")
    safe_prompt = prompt.replace('"""', r'\"\"\"')
    worker_code = template_text.replace("__PROMPT_PLACEHOLDER__", f'"""{safe_prompt}"""')

    if telegram_token and telegram_token.strip():
        worker_code = worker_code.replace("__TELEGRAM_TOKEN_PLACEHOLDER__", f'TELEGRAM_TOKEN = "{telegram_token.strip()}"')
    else:
        worker_code = worker_code.replace("__TELEGRAM_TOKEN_PLACEHOLDER__", 'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')

    (dest / "bot.py").write_text(worker_code, encoding="utf-8")

    # copy support files if they exist in agents/ root
    for fname in ("requirements.txt", "render.yaml", ".env.example", "README_worker.md"):
        src = AGENTS_DIR / fname
        if src.exists():
            shutil.copy(src, dest / fname)

    # zip for download
    zip_path = AGENTS_DIR / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(dest):
            for f in files:
                full = Path(root) / f
                arcname = Path(slug) / full.relative_to(dest)
                zf.write(full, arcname.as_posix())

    entry = {
        "name": name,
        "slug": slug,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "zip": f"/download/{zip_path.name}",
        "repo": "",
        "render_service_id": "",
        "deploy_url": "",
        "status": "created",
        "test_chat_id": ""
    }

    meta = load_meta()
    meta.append(entry)
    save_meta(meta)

    # auto-deploy if requested (calls create_and_push.sh)
    if auto_deploy == "1":
        script = BASE / "create_and_push.sh"
        if script.exists():
            try:
                subprocess.run(["bash", str(script), slug, str(dest)], check=True)
                # mark as in progress; create_and_push.sh prints render response to stdout
                entry["status"] = "deploy_in_progress"
                save_meta(meta)
            except Exception as e:
                entry["status"] = "deploy_failed"
                entry.setdefault("errors", []).append(str(e))
                save_meta(meta)
        else:
            entry.setdefault("errors", []).append("create_and_push.sh not found on server")
            save_meta(meta)

    return RedirectResponse("/", status_code=303)

@app.get("/download/{zipname}")
async def download_zip(zipname: str):
    path = AGENTS_DIR / zipname
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP not found")
    return FileResponse(path, filename=zipname)

@app.post("/api/set_worker_url")
async def set_worker_url(slug: str = Form(...), deploy_url: str = Form(...), test_chat_id: str = Form("")):
    meta = load_meta()
    found = False
    for e in meta:
        if e.get("slug") == slug:
            e["deploy_url"] = deploy_url
            if test_chat_id:
                e["test_chat_id"] = test_chat_id
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Worker not found")
    save_meta(meta)
    return JSONResponse({"ok": True})

@app.post("/api/delete_agent")
async def delete_agent(slug: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Agent not found")

    # attempt remote deletion if IDs present (best-effort)
    render_id = entry.get("render_service_id")
    if render_id and os.getenv("RENDER_API_KEY"):
        try:
            import requests
            r = requests.delete(f"https://api.render.com/v1/services/{render_id}", headers={"Authorization": f"Bearer {os.getenv('RENDER_API_KEY')}"})
            # ignore response check — best-effort
        except Exception as ex:
            entry.setdefault("errors", []).append(f"render_delete_error:{ex}")

    repo_url = entry.get("repo") or ""
    if repo_url and os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_USER"):
        try:
            m = re.match(r"https?://github.com/([^/]+)/([^/.]+)", repo_url)
            if m:
                owner, repo_name = m.group(1), m.group(2)
                # delete via GitHub API
                import requests
                headers = {"Authorization": f"token {os.getenv('GITHUB_TOKEN')}", "Accept": "application/vnd.github.v3+json"}
                resp = requests.delete(f"https://api.github.com/repos/{owner}/{repo_name}", headers=headers)
        except Exception as ex:
            entry.setdefault("errors", []).append(f"github_delete_error:{ex}")

    # delete local files and zip
    local_dir = AGENTS_DIR / slug
    if local_dir.exists():
        shutil.rmtree(local_dir)
    z = AGENTS_DIR / f"{slug}.zip"
    if z.exists():
        z.unlink()

    meta = [e for e in meta if e["slug"] != slug]
    save_meta(meta)
    return JSONResponse({"ok": True})

@app.post("/api/assign_task")
async def assign_task(slug: str = Form(...), task: str = Form(...)):
    meta = load_meta()
    entry = next((e for e in meta if e["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Worker not found")
    deploy_url = entry.get("deploy_url") or ""
    if not deploy_url:
        raise HTTPException(status_code=400, detail="Worker not deployed. Paste URL in manager or auto-deploy.")
    try:
        chat_id = int(entry.get("test_chat_id") or 123456789)
    except Exception:
        chat_id = 123456789
    payload = {
        "message": {
            "message_id": 1,
            "from": {"id": 1111, "is_bot": False, "first_name": "Manager"},
            "chat": {"id": chat_id, "type": "private"},
            "date": int(datetime.datetime.utcnow().timestamp()),
            "text": task
        }
    }
    import requests
    try:
        resp = requests.post(deploy_url.rstrip("/") + "/webhook", json=payload, timeout=25)
        return JSONResponse({"ok": True, "status": resp.status_code, "text": resp.text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
