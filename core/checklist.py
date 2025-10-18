from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import json

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE / "agents"
TEMPLATES_DIR = BASE / "templates"

@router.get("/checklist", response_class=HTMLResponse)
async def checklist(request: Request):
    return HTMLResponse((TEMPLATES_DIR / "checklist.html").read_text(encoding="utf-8"))

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
