import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from pathlib import Path
from bot_template import BOT_TEMPLATE
from pathlib import Path
Path("agents").mkdir(exist_ok=True)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BASE_DIR / "agents"
AGENTS_DIR.mkdir(exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    agents = [f.stem for f in AGENTS_DIR.glob("*.py")]
    return templates.TemplateResponse("index.html", {"request": request, "agents": agents})

@app.post("/create_agent")
async def create_agent(name: str = Form(...), prompt: str = Form(...), telegram_token: str = Form("")):
    bot_code = BOT_TEMPLATE.format(prompt=prompt, telegram_token=telegram_token)
    agent_path = Path("agents") / f"{name}.py"
    agent_path.write_text(bot_code)
    return {"status": "ok", "message": f"✅ Агент {name} создан"}


@app.post("/delete_agent")
async def delete_agent(name: str = Form(...)):
    target = AGENTS_DIR / f"{name}.py"
    if target.exists():
        target.unlink()
    return RedirectResponse("/", status_code=303)
