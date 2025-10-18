import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from core import agents, brainstorm, checklist, office, demo

# === Настройки ===
load_dotenv()
BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
LOGS_DIR = BASE / "logs"
AGENTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# === Логирование ===
logger = logging.getLogger("manager")
logger.setLevel(logging.INFO)

# === Инициализация FastAPI ===
app = FastAPI()
app.state.BASE = BASE
app.state.AGENTS_DIR = AGENTS_DIR

# === Подключение статических файлов ===
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# === Подключение роутеров ===
app.include_router(agents.router)  # без prefix
app.include_router(brainstorm.router)
app.include_router(checklist.router)
app.include_router(office.router)

# === Демо ===
@app.on_event("startup")
async def startup_event():
    demo._seed_demo_if_empty(AGENTS_DIR)
    demo.ensure_assistant_llm(AGENTS_DIR, BASE)
    demo.ensure_demo_agents_llm(AGENTS_DIR, BASE)

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.getenv("PORT", 8000))
    logger.info("Запуск менеджера на порту %s", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port)
