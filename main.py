import os
import json
import logging
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
import requests

# === Настройки ===
BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BASE_DIR / "agents"
AGENTS_FILE = BASE_DIR / "agents.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# === Шаблон бота ===
BOT_TEMPLATE = """import os, re, base64, requests
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv
load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY") or os.getenv("AMVERA_API_TOKEN")
TELEGRAM_TOKEN = "{telegram_token}"
PROMT = \"\"\"{prompt}\"\"\"

llm = AmveraLLM(model="gpt-4.1", api_token=AMVERA_API_KEY)
app = FastAPI()

@app.post("/task")
async def task_endpoint(request: Request):
    data = await request.json()
    user_task = data.get("task")
    result = llm.invoke(f"{PROMT}\\n\\nЗадача: {user_task}")
    return {{"agent": "{name}", "response": str(result)}}
"""

# === Хранилище сотрудников ===
if not AGENTS_DIR.exists():
    AGENTS_DIR.mkdir()
if not AGENTS_FILE.exists():
    AGENTS_FILE.write_text(json.dumps([]))


def load_agents():
    return json.loads(AGENTS_FILE.read_text())


def save_agents(agents):
    AGENTS_FILE.write_text(json.dumps(agents, indent=2))


@app.get("/", response_class=HTMLResponse)
async def index():
    agents = load_agents()
    has_agents = len(agents) > 0

    html = f"""
    <html>
    <head>
        <title>🧠 Multiagent Manager</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background-color: #f4f4f9;
                padding: 40px;
                color: #333;
            }}
            h1 {{ color: #222; }}
            input, textarea {{
                padding: 10px;
                margin: 5px;
                width: 300px;
                border-radius: 8px;
                border: 1px solid #ccc;
            }}
            button {{
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                cursor: pointer;
            }}
            button:hover {{ background: #45a049; }}
            .agent {{
                background: white;
                padding: 15px;
                border-radius: 10px;
                margin-top: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .task-area {{
                background: #fff;
                padding: 15px;
                border-radius: 10px;
                margin-top: 30px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
        </style>
    </head>
    <body>
        <h1>🧠 Multiagent Manager</h1>

        <h2>Создать нового сотрудника</h2>
        <form action="/create_agent" method="post">
            <input name="name" placeholder="Название" required><br>
            <textarea name="prompt" placeholder="Промт-инструкция" required></textarea><br>
            <input name="telegram_token" placeholder="Telegram Token (опционально)"><br>
            <button type="submit">Создать сотрудника</button>
        </form>

        <h2>Список сотрудников</h2>
    """

    if has_agents:
        html += '<ul>'
        for a in agents:
            html += f"""
            <div class="agent">
                <b>{a['name']}</b><br>
                <small>{a['prompt'][:100]}...</small><br>
                <form action="/delete_agent" method="post" style="display:inline;">
                    <input type="hidden" name="name" value="{a['name']}">
                    <button style="background:red;">Удалить</button>
                </form>
            </div>
            """
        html += "</ul>"

        html += """
        <div class="task-area">
            <h3>🧩 Поручить задачу сотрудникам</h3>
            <form action="/assign_task" method="post">
                <textarea name="task" placeholder="Введите задачу..." required></textarea><br>
                <button type="submit">Поручить задачу сотрудникам</button>
            </form>
        </div>
        """
    else:
        html += "<p><i>Создайте хотя бы одного сотрудника, чтобы поручить задачу.</i></p>"

    html += "</body></html>"
    return HTMLResponse(html)


@app.post("/create_agent")
async def create_agent(name: str = Form(...), prompt: str = Form(...), telegram_token: str = Form("")):
    agents = load_agents()
    agent_path = AGENTS_DIR / f"{name}_bot.py"

    if agent_path.exists():
        return HTMLResponse(f"<h3>⚠️ Агент '{name}' уже существует!</h3>")

    code = BOT_TEMPLATE.format(name=name, prompt=prompt, telegram_token=telegram_token)
    agent_path.write_text(code)
    agents.append({"name": name, "prompt": prompt, "telegram_token": telegram_token})
    save_agents(agents)

    logging.info(f"✅ Создан новый агент: {name}")
    return RedirectResponse("/", status_code=303)


@app.post("/delete_agent")
async def delete_agent(name: str = Form(...)):
    agents = load_agents()
    agents = [a for a in agents if a["name"] != name]
    save_agents(agents)

    path = AGENTS_DIR / f"{name}_bot.py"
    if path.exists():
        path.unlink()
    logging.info(f"🗑 Удален агент: {name}")
    return RedirectResponse("/", status_code=303)


@app.post("/assign_task", response_class=HTMLResponse)
async def assign_task(task: str = Form(...)):
    agents = load_agents()
    results = []

    for a in agents:
        try:
            url = f"https://{a['name'].lower()}.onrender.com/task"
            logging.info(f"📤 Отправка задачи агенту {a['name']} по адресу {url}")
            resp = requests.post(url, json={"task": task}, timeout=30)
            if resp.ok:
                results.append(resp.json())
            else:
                results.append({"agent": a["name"], "response": f"Ошибка {resp.status_code}: {resp.text}"})
        except Exception as e:
            logging.error(f"❌ Ошибка при обращении к агенту {a['name']}: {e}")
            results.append({"agent": a["name"], "response": f"Ошибка: {e}"})

    result_html = "<h2>📋 Результаты выполнения:</h2><ul>"
    for r in results:
        result_html += f"<li><b>{r['agent']}</b>: {r['response']}</li>"
    result_html += "</ul><a href='/'>Назад</a>"

    return HTMLResponse(result_html)
