
# Патчер для multiagent-startup
import re, json, shutil
from pathlib import Path

BASE = Path(__file__).parent
MAIN = BASE / "main.py"
UTILS = BASE / "utils.py"
TPL_DIR = BASE / "templates"
AGENTS_DIR = BASE / "agents"
PACK_TPL = Path(__file__).with_name("templates").joinpath("office.html")

def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak")
    if not b.exists():
        shutil.copy(p, b)

def ensure_imports_main(text: str) -> str:
    if "from utils import" not in text:
        return text
    def repl(m):
        line = m.group(0)
        if "save_memory" in line:
            return line
        if line.rstrip().endswith("\\"):
            return line + ", save_memory"
        return line.rstrip() + ", save_memory"
    return re.sub(r'^from utils import[^\n]+$', repl, text, flags=re.M)

OFFICE_ENDPOINT = r'''
@app.get("/office", response_class=HTMLResponse)
async def office(request: Request):
    """Интерактивная карта агентов и их связей."""
    meta = load_meta()
    valid = {a["slug"] for a in meta if not a.get("is_folder")}
    for a in meta:
        if a.get("is_folder"):
            continue
        a["connections"] = [c for c in (a.get("connections") or []) if c in valid]
    return templates.TemplateResponse("office.html", {"request": request, "agents": meta})
'''

DELEGATE_ENDPOINT = r'''
@app.post("/delegate_task")
async def delegate_task(from_slug: str = Form(...), to_slug: str = Form(...), message: str = Form(...)):
    """Агент A отправляет задачу агенту B. Локально приоритетно; если локально невозможно — пробуем deploy_url."""
    meta = load_meta()
    from_agent = next((a for a in meta if a.get("slug") == from_slug and not a.get("is_folder")), None)
    to_agent   = next((a for a in meta if a.get("slug") == to_slug   and not a.get("is_folder")), None)
    if not from_agent or not to_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    res = None
    try:
        to_path = Path(to_agent.get("path") or "")
        if to_path.exists():
            res = await call_agent_local(to_path, f"Сообщение от {from_agent['name']}: {message}")
        elif to_agent.get("deploy_url"):
            res = await call_agent_remote(to_agent["deploy_url"], f"Сообщение от {from_agent['name']}: {message}")
        else:
            raise RuntimeError("no_local_or_remote")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        save_memory(Path(from_agent["path"]), {"date": __import__("datetime").datetime.utcnow().isoformat()+"Z", "task": f"Отправил {to_agent['name']}: {message}", "result": res.get("result") if isinstance(res, dict) else str(res)})
        save_memory(Path(to_agent["path"]), {"date": __import__("datetime").datetime.utcnow().isoformat()+"Z", "task": f"Получил от {from_agent['name']}: {message}", "result": (res.get("result") or res.get("text")) if isinstance(res, dict) else str(res)})
    except Exception:
        pass
    return JSONResponse({"ok": True, "result": res})
'''

BRAINSTORM_ENDPOINT = r'''
@app.post("/brainstorm")
async def brainstorm(topic: str = Form(...)):
    """Собираем ответы всех агентов по теме (локально → удалённо)."""
    agents = [a for a in load_meta() if not a.get("is_folder")]
    results = []
    async def run(a):
        try:
            out = None
            p = Path(a.get("path") or "")
            if p.exists():
                r = await call_agent_local(p, f"Тема мозгового штурма: {topic}")
                out = r.get("result") if isinstance(r, dict) else str(r)
            elif a.get("deploy_url"):
                r = await call_agent_remote(a["deploy_url"], f"Тема мозгового штурма: {topic}")
                out = (r.get("text") or str(r)) if isinstance(r, dict) else str(r)
            else:
                out = "no path or deploy_url"
            results.append({"agent": a["name"], "response": out})
            try:
                save_memory(p, {"date": __import__("datetime").datetime.utcnow().isoformat()+"Z", "task": f"Brainstorm: {topic}", "result": out})
            except Exception:
                pass
        except Exception as e:
            results.append({"agent": a["name"], "error": str(e)})
    await asyncio.gather(*[run(a) for a in agents])
    return JSONResponse({"ok": True, "topic": topic, "results": results})
'''

ADD_CONNECTION_ENDPOINT = r'''
@app.post("/add_connection")
async def add_connection(from_slug: str = Form(...), to_slug: str = Form(...)):
    """Добавляет направленную связь (from → to) между агентами."""
    meta = load_meta()
    from_agent = next((a for a in meta if a.get("slug") == from_slug and not a.get("is_folder")), None)
    to_agent   = next((a for a in meta if a.get("slug") == to_slug   and not a.get("is_folder")), None)
    if not from_agent or not to_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    conns = from_agent.get("connections") or []
    if to_slug not in conns:
        conns.append(to_slug)
        from_agent["connections"] = conns
        save_meta(meta)
        return JSONResponse({"ok": True, "added": True})
    return JSONResponse({"ok": True, "added": False, "message": "already_exists"})
'''

SEED_DEMO = r'''
# === Автосоздание демо-команды при первом запуске ===
# === Автосоздание демо-команды при первом запуске ===
def _seed_demo_if_empty():
    try:
        meta = load_meta()

        # Если уже есть агенты, ничего не делаем
        if any(not a.get("is_folder") for a in meta):
            return

        demo_dir = AGENTS_DIR / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)

        # Демо-агенты
        demo_agents = [
            {"name": "Стратег", "slug": "strategist", "folder": "demo", "connections": ["copywriter", "designer"]},
            {"name": "Копирайтер", "slug": "copywriter", "folder": "demo", "connections": ["designer"]},
            {"name": "Дизайнер", "slug": "designer", "folder": "demo", "connections": ["copywriter"]},
        ]

        # Создаём папку "demo" в agents.json как каталог
        folder_entry = {
            "folder": "demo",
            "is_folder": True,
            "name": "demo",
            "slug": "folder_demo",
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z'
        }

        # Список для записи в agents.json
        new_meta = [folder_entry]

        # Создаём агентов внутри demo/
        for a in demo_agents:
            adir = demo_dir / a["slug"]
            adir.mkdir(parents=True, exist_ok=True)
            (adir / "bot.py").write_text(
                "import time\n"
                "def handle_task(task: str):\n"
                "    time.sleep(0.2)\n"
                "    return f'[DEMO] {task} — обработано демо-ботом'\n",
                encoding="utf-8"
            )
            (adir / "memory.json").write_text("[]", encoding="utf-8")

            new_meta.append({
                "name": a["name"],
                "slug": a["slug"],
                "folder": "demo",
                "path": str(demo_dir / a["slug"]),
                "connections": a["connections"],
                "status": "ready"
            })

        save_meta(new_meta)

    except Exception as e:
        import logging
        logging.getLogger("manager").warning("seed demo error: %s", e)
'''

def insert_endpoints(text: str) -> str:
    anchor = text.find("# --- СОЗДАНИЕ НОВОГО АГЕНТА ---")
    if anchor == -1:
        anchor = text.find("@app.post('/create_agent')")
    blocks = OFFICE_ENDPOINT + DELEGATE_ENDPOINT + BRAINSTORM_ENDPOINT + ADD_CONNECTION_ENDPOINT
    if anchor == -1:
        return text + "\n" + blocks
    return text[:anchor] + blocks + text[anchor:]

def insert_seed(text: str) -> str:
    anchor = text.find("if __name__ == '__main__':")
    if anchor == -1:
        return text + "\n" + SEED_DEMO
    return text[:anchor] + SEED_DEMO + text[anchor:]

def patch_main():
    if not MAIN.exists():
        print("main.py not found. Run from project root.")
        return
    backup(MAIN)
    txt = MAIN.read_text(encoding="utf-8")
    txt = ensure_imports_main(txt)
    txt = insert_endpoints(txt)
    txt = insert_seed(txt)
    MAIN.write_text(txt, encoding="utf-8")
    print("main.py updated. Backup at main.py.bak")

def ensure_save_memory_utils():
    if not UTILS.exists():
        print("utils.py not found. Skipping utils patch.")
        return
    backup(UTILS)
    u = UTILS.read_text(encoding="utf-8")
    if "def save_memory(" in u:
        print("save_memory already present.")
        return
    addition = r'''

import json
from pathlib import Path
import logging
logger = logging.getLogger("manager")
def save_memory(agent_path: Path, record: dict):
    try:
        mem_file = Path(agent_path) / "memory.json"
        if mem_file.exists():
            try:
                data = json.loads(mem_file.read_text(encoding="utf-8"))
            except Exception:
                data = []
        else:
            data = []
        data.append(record)
        mem_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("save_memory error: %s", e)
'''
    UTILS.write_text(u + addition, encoding="utf-8")
    print("utils.py updated. Backup at utils.py.bak")

def ensure_office_template():
    TPL_DIR.mkdir(parents=True, exist_ok=True)
    office = TPL_DIR / "office.html"
    if not office.exists():
        office.write_text(PACK_TPL.read_text(encoding="utf-8"), encoding="utf-8")
        print("templates/office.html created.")
    else:
        print("templates/office.html already exists.")

def main():
    patch_main()
    ensure_save_memory_utils()
    ensure_office_template()
    print("Done. Restart your server and open /office")

if __name__ == "__main__":
    main()
