import os
import json
import asyncio
import logging
import importlib.util
from pathlib import Path
from datetime import datetime
import requests
from typing import Any, Dict
from filelock import FileLock

logger = logging.getLogger("manager")

# === Метаданные (agents.json) ===
META_PATH = Path(__file__).resolve().parent / "agents" / "agents.json"

def load_meta() -> list[dict]:
    """Безопасно загружает agents.json (если поврежден — восстанавливает)."""
    try:
        if not META_PATH.exists():
            META_PATH.write_text("[]", encoding="utf-8")
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("⚠️ Поврежден agents.json — восстановлен.")
        META_PATH.write_text("[]", encoding="utf-8")
        return []

def save_meta(meta: list[dict]):
    """Безопасно сохраняет agents.json (с атомарной записью и блокировкой)."""
    tmp_path = META_PATH.with_suffix(".tmp")
    lock_path = str(META_PATH) + ".lock"
    lock = FileLock(lock_path)

    with lock:
        try:
            # Записываем во временный файл
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # Атомарно заменяем старый файл
            os.replace(tmp_path, META_PATH)
            logger.debug("✅ Метаданные сохранены безопасно.")
        except Exception as e:
            logger.exception(f"Ошибка при сохранении meta: {e}")
            raise


# === Вызов агентов ===
async def call_agent_local(path: Path, task: str) -> Dict[str, Any]:
    """Вызывает локального агента через его bot.py."""
    try:
        bot_file = path / "bot.py"
        if not bot_file.exists():
            raise FileNotFoundError(f"bot.py не найден в {path}")

        spec = importlib.util.spec_from_file_location(f"agent_{path.name}", str(bot_file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not hasattr(mod, "handle_task"):
            raise AttributeError(f"Функция handle_task не найдена в {path.name}")

        logger.info(f"🧠 Вызов локального агента: {path.name}")
        res = mod.handle_task(task)
        return {"ok": True, "source": "local", "result": res}

    except Exception as e:
        logger.exception(f"Ошибка вызова локального агента: {e}")
        return {"ok": False, "error": str(e)}

async def call_agent_remote(url: str, task: str) -> Dict[str, Any]:
    """Отправляет задачу агенту, развернутому удаленно (через webhook)."""
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
        r.raise_for_status()
        return {"ok": True, "source": "remote", "status": r.status_code, "result": r.text}
    except Exception as e:
        logger.exception(f"Ошибка вызова удалённого агента: {e}")
        return {"ok": False, "error": str(e)}

# === Память агента ===
def save_memory(agent_path: Path, record: dict[str, Any]):
    """Сохраняет запись в memory.json агента (с file-lock, безопасно и атомарно)."""
    mem_file = agent_path / "memory.json"
    tmp_file = mem_file.with_suffix(".tmp")
    lock = FileLock(str(mem_file) + ".lock")

    with lock:
        try:
            memory = []
            if mem_file.exists():
                try:
                    memory = json.loads(mem_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Поврежден memory.json у {agent_path.name}, восстановлен.")
                    memory = []

            record["date"] = record.get("date") or datetime.utcnow().isoformat() + "Z"
            memory.append(record)

            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, mem_file)
        except Exception as e:
            logger.warning(f"Ошибка записи памяти агента {agent_path.name}: {e}")

