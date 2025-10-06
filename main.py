from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import os
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv
import importlib.util

load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
AMVERA_MODEL = "gpt-4.1"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

employees = []

BOT_TEMPLATE = '''import os
import requests
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv

load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
AMVERA_MODEL = "gpt-4.1"

TELEGRAM_TOKEN = "{telegram_token}"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{telegram_token}"
PROMT = """{prompt}"""

llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)

def solve(task):
    full_prompt = f"{PROMT}\\n\\nПользователь: {task}"
    resp = llm.invoke(full_prompt)
    return resp.content if hasattr(resp, "content") else str(resp)
'''

def create_employee_file(name: str, prompt: str, telegram_token: str):
    os.makedirs("employees", exist_ok=True)
    file_path = f"employees/{name}.py"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(BOT_TEMPLATE.format(prompt=prompt, telegram_token=telegram_token))
    return file_path

def load_employee_module(file_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Employee:
    def __init__(self, name: str, prompt: str, telegram_token: str):
        self.name = name
        self.status = "Готов"
        file_path = create_employee_file(name, prompt, telegram_token)
        self.module = load_employee_module(file_path, name)

    async def solve_task(self, task: str):
        self.status = "В работе"
        result = await asyncio.to_thread(lambda: self.module.solve(task))
        self.status = "Готов"
        return result

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "employees": employees})

@app.post("/add_employee", response_class=HTMLResponse)
def add_employee(request: Request, name: str = Form(...), prompt: str = Form(...), telegram_token: str = Form(...)):
    employees.append(Employee(name=name, prompt=prompt, telegram_token=telegram_token))
    return templates.TemplateResponse("index.html", {"request": request, "employees": employees})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if "task" in data:
                task = data["task"]
                for emp in employees:
                    await websocket.send_json({"name": emp.name, "status": emp.status, "result": None})

                tasks = [emp.solve_task(task) for emp in employees]
                results = await asyncio.gather(*tasks)

                for emp, result in zip(employees, results):
                    await websocket.send_json({"name": emp.name, "status": emp.status, "result": result})

    except WebSocketDisconnect:
        print("Клиент отключился")
