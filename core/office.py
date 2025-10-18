from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from utils import load_meta

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/office", response_class=HTMLResponse)
async def office(request: Request):
    meta = load_meta()
    valid = {a["slug"] for a in meta if not a.get("is_folder")}
    for a in meta:
        if a.get("is_folder"):
            continue
        a["connections"] = [c for c in (a.get("connections") or []) if c in valid]
    return templates.TemplateResponse("office.html", {"request": request, "agents": meta})
