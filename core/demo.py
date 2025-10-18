import shutil, logging, os
from pathlib import Path
from utils import load_meta, save_meta

logger = logging.getLogger("manager")

def _seed_demo_if_empty(AGENTS_DIR: Path):
    try:
        meta = load_meta()
        if any(not a.get("is_folder") for a in meta):
            return
        demo_dir = AGENTS_DIR / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        demo_agents = [
            {"name":"Стратег","slug":"strategist","folder":"demo","connections":["copywriter","designer"]},
            {"name":"Копирайтер","slug":"copywriter","folder":"demo","connections":["designer"]},
            {"name":"Дизайнер","slug":"designer","folder":"demo","connections":["copywriter"]},
        ]
        folder_entry = {"folder":"demo","is_folder":True,"name":"demo","slug":"folder_demo",
                        "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z'}
        new_meta = [folder_entry]
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
            new_meta.append({"name": a["name"], "slug": a["slug"], "folder": "demo",
                             "path": str(adir), "connections": a["connections"], "status":"ready"})
        save_meta(new_meta)
        logger.info("✅ Демо-агенты созданы")
    except Exception as e:
        logger.warning("seed demo error: %s", e)

def ensure_assistant_llm(AGENTS_DIR: Path, BASE: Path):
    try:
        root_dir = AGENTS_DIR / "root"
        assistant_dir = root_dir / "assistant_default"
        template_path = BASE / "bot_template.py"
        assistant_dir.mkdir(parents=True, exist_ok=True)
        bot_path = assistant_dir / "bot.py"
        if not bot_path.exists():
            shutil.copy(template_path, bot_path)
            return
        text = bot_path.read_text(encoding="utf-8")
        if "AmveraLLM" not in text or "PROMPT" not in text:
            shutil.copy(template_path, bot_path)
            logger.info("✅ Ассистент обновлён до версии с LLM.")
    except Exception as e:
        logger.exception("Ошибка при проверке/обновлении ассистента: %s", e)

def ensure_demo_agents_llm(AGENTS_DIR: Path, BASE: Path):
    try:
        demo_dir = AGENTS_DIR / "demo"
        template_path = BASE / "bot_template.py"
        if not demo_dir.exists():
            logger.info("Каталог demo не найден — пропуск обновления.")
            return
        role_prompts = {
            "strategist": "Ты стратег. Предлагай системные и дальновидные идеи, фокусируйся на целях и планировании.",
            "copywriter": "Ты копирайтер. Пиши ярко, лаконично и с эмоциональным вовлечением.",
            "designer": "Ты дизайнер. Предлагай визуальные решения, композиционные идеи и стиль.",
        }
        for agent_folder in demo_dir.iterdir():
            if not agent_folder.is_dir():
                continue
            bot_path = agent_folder / "bot.py"
            role = agent_folder.name
            role_prompt = role_prompts.get(role, f"Ты {role}. Отвечай кратко и по делу.")
            if (not bot_path.exists()) or ("AmveraLLM" not in bot_path.read_text(encoding="utf-8")):
                text = template_path.read_text(encoding="utf-8")
                text = text.replace("__PROMPT_PLACEHOLDER__", f'"""{role_prompt}"""')
                text = text.replace("__TELEGRAM_TOKEN_PLACEHOLDER__", 'TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")')
                bot_path.write_text(text, encoding="utf-8")
                logger.info(f"✅ Обновлён демо-агент {role}")
        logger.info("✅ Демо-агенты проверены и обновлены при необходимости.")
    except Exception as e:
        logger.exception(f"Ошибка при обновлении демо-агентов: {e}")
