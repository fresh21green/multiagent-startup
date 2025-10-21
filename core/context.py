# app/routes/context.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CONTEXT_DIR = Path("data/context")

@router.get("/context", response_class=HTMLResponse)
async def context_page(request: Request):
    """Отображение страницы контекста агентов"""
    return templates.TemplateResponse("context.html", {"request": request})


@router.get("/api/context", response_class=JSONResponse)
async def context_data():
    """Возвращает объединённый контекст всех агентов"""
    if not CONTEXT_DIR.exists() or not CONTEXT_DIR.is_dir():
        return JSONResponse(
            {"error": f"Папка {CONTEXT_DIR} не найдена"}, status_code=404
        )

    all_contexts = {}
    for file in CONTEXT_DIR.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            agent_name = file.stem  # имя файла без .json
            all_contexts[agent_name] = data
        except Exception as e:
            all_contexts[file.name] = {"error": str(e)}

    return all_contexts
