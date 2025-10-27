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
from core.mcp import load_context, save_context

logger = logging.getLogger("manager")

# === Пути проекта ===
BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BASE_DIR / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)
META_PATH = AGENTS_DIR / "agents.json"




# === Метаданные (agents.json) ===
def load_meta() -> list[dict]:
    """Безопасно загружает agents.json (если поврежден — восстанавливает)."""
    logger.info("META_PATH %s", META_PATH)
    try:
        if not META_PATH.exists():
            META_PATH.write_text("[]", encoding="utf-8")
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("⚠️ Поврежден agents.json — восстановлен.")
        META_PATH.write_text("[]", encoding="utf-8")
        return []


import time

def save_meta(meta: list[dict]):
    tmp_path = META_PATH.with_suffix(".tmp")
    lock = FileLock(str(META_PATH) + ".lock")

    with lock:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        import shutil, time
        for attempt in range(3):
            try:
                shutil.move(str(tmp_path), str(META_PATH))
                logger.debug("✅ agents.json обновлён")
                break
            except PermissionError as e:
                logger.warning(f"⚠️ agents.json занят, попытка {attempt+1}/3: {e}")
                time.sleep(1)




# === Мультипользовательские хелперы ===
def filter_meta_by_owner(meta: list[dict], owner: str) -> list[dict]:
    """Возвращает только объекты, принадлежащие пользователю."""
    return [a for a in meta if a.get("owner") == owner]


def ensure_user_root(owner: str) -> Path:
    """Гарантирует наличие директории /agents/{owner}."""
    user_dir = AGENTS_DIR / owner
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


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
    """Сохраняет запись в memory.json агента (безопасно и атомарно)."""
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


# === Контекст ===
async def call_agent_with_context(agent, task: str):
    """
    Вызывает агента с учётом его контекста и PROMPT из bot.py.
    Теперь:
      - Контролирует размер контекста
      - Подсчитывает примерное количество токенов
      - Логирует всё в debug
    """
    import json, re, importlib.util, logging
    from datetime import datetime
    from pathlib import Path
    from core.mcp import load_context, save_context
    from utils import call_agent_local

    logger = logging.getLogger("context")

    agent_id = agent["slug"]
    path = Path(agent["path"])

    # === 1️⃣ Загружаем контекст ===
    context = load_context(agent_id)
    context_text = json.dumps(context or {}, ensure_ascii=False, indent=2)

    # === 2️⃣ Ограничиваем размер контекста ===
    MAX_CONTEXT_CHARS = 3000  # оптимально ~500–700 токенов
    if len(context_text) > MAX_CONTEXT_CHARS:
        logger.warning(f"[{agent_id}] Контекст слишком длинный ({len(context_text)} символов) — обрезаем.")
        context_text = context_text[-MAX_CONTEXT_CHARS:]

    # === 3️⃣ Извлекаем PROMPT из bot.py ===
    prompt_text = ""
    bot_path = path / "bot.py"
    if bot_path.exists():
        try:
            text = bot_path.read_text(encoding="utf-8")
            match = re.search(r'PROMPT\s*=\s*"""(.*?)"""', text, re.DOTALL)
            if match:
                prompt_text = match.group(1).strip()
        except Exception as e:
            logger.warning(f"[{agent_id}] Ошибка чтения PROMPT: {e}")

    team_bias = float(agent.get("team_bias", 0.5))
    role_weight = 1.0 - team_bias
    context_weight = team_bias

    # === 4️⃣ Формируем объединённый промпт ===
    full_prompt = (
        f"🧠 Роль агента (вес {role_weight:.1f}):\n"
        f"{prompt_text or 'Универсальный сотрудник.'}\n\n"
        f"📘 Контекст команды (вес {context_weight:.1f}):\n"
        f"{context_text}\n\n"
        f"🧩 Новая задача:\n{task}\n\n"
        f"Ответь, учитывая баланс — "
        f"{'ориентируйся на личное мнение' if role_weight > 0.6 else 'учитывай коллективное мнение команды'}."
    )

    # === 5️⃣ Примерная оценка количества токенов ===
    def estimate_tokens(text: str):
        # Простейшая эвристика — 1 токен ≈ 4 символа латиницы
        return int(len(text) / 4)

    token_count = estimate_tokens(full_prompt)
    logger.info(f"[{agent_id}] ➜ {token_count} токенов (≈{len(full_prompt)} символов)")

    # === 6️⃣ Вызов агента ===
    result = await call_agent_local(path, full_prompt)

    # === 7️⃣ Обновляем контекст ===
    new_context = {
        **(context or {}),
        "last_task": task,
        "last_result": result.get("result") if isinstance(result, dict) else str(result),
        "_updated": datetime.now().isoformat(),
        "_token_count": token_count
    }
    save_context(agent_id, new_context)

    return result


