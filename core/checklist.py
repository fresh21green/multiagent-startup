from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import json

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE / "agents"
TEMPLATES_DIR = BASE / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/checklist", response_class=HTMLResponse)
async def checklist(request: Request):
    # return HTMLResponse((TEMPLATES_DIR / "checklist.html").read_text(encoding="utf-8"))
    return templates.TemplateResponse(
            "checklist.html",
            {"request": request, "active": "checklist"}
        )

@router.get("/check_memory")
async def check_memory():
    results = {}
    try:
        for folder in AGENTS_DIR.rglob("memory.json"):
            try:
                data = json.loads(folder.read_text(encoding="utf-8"))
                agent_name = folder.parent.name
                results[agent_name] = data[-3:] if len(data) > 3 else data
            except Exception as e:
                results[folder.parent.name] = f"Ошибка чтения: {e}"
        return JSONResponse({"ok": True, "memories": results})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
@router.get("/memory")
async def memory_alias():
    """Алиас для совместимости с фронтом."""
    return await check_memory()
