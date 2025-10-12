import importlib
import logging
import json
from pathlib import Path

logger = logging.getLogger("manager")

BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
AGENTS_DIR.mkdir(exist_ok=True)
META_FILE = AGENTS_DIR / "workers.json"

if not META_FILE.exists():
    META_FILE.write_text("[]", encoding="utf-8")


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def call_agent_local(path: Path, task: str):
    """Вызывает локального агента (запуск его функции handle_task)."""
    try:
        spec = importlib.util.spec_from_file_location(f"agent_{path.name}", str(path / "bot.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, "handle_task"):
            logger.info("Вызов локального агента %s", path.name)
            res = mod.handle_task(task)
            return {"ok": True, "source": "local", "result": res}
        else:
            logger.warning("У модуля %s нет функции handle_task", path)
            return {"ok": False, "error": "no_handle_task"}

    except Exception as e:
        logger.exception("Ошибка вызова локального агента: %s", e)
        return {"ok": False, "error": str(e)}


async def call_agent_remote(url: str, task: str):
    """Отправляет задачу агенту, развернутому удаленно (через /webhook)."""
    import requests
    try:
        payload = {
            "message": {
                "message_id": 1,
                "from": {"id": 1111, "is_bot": False, "first_name": "Manager"},
                "chat": {"id": 123456, "type": "private"},
                "date": int(__import__("time").time()),
                "text": task
            }
        }
        r = requests.post(url.rstrip("/") + "/webhook", json=payload, timeout=20)
        logger.info("Удалённый агент %s ответил со статусом %s", url, r.status_code)
        return {"ok": True, "source": "remote", "status": r.status_code, "text": r.text}
    except Exception as e:
        logger.exception("Ошибка при вызове удалённого агента: %s", e)
        return {"ok": False, "error": str(e)}


def load_meta():
    """Загружает JSON-файл метаданных агентов."""
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.exception("Не удалось загрузить метаданные: %s", e)
        return []


def save_meta(meta):
    """Сохраняет JSON-файл метаданных агентов."""
    try:
        META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.exception("Не удалось сохранить метаданные: %s", e)
