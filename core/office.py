import re
import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.auth import get_current_user
from utils import load_meta, save_meta, ensure_user_root, filter_meta_by_owner

logger = logging.getLogger("manager")
router = APIRouter()

BASE = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def slugify(name: str):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip()).lower()


# 🟢 HTML-страница офиса (без Depends — проверка токена выполняется на фронте)
@router.get("/office", response_class=HTMLResponse)
async def office_page(request: Request):
    """
    Главная HTML-страница офисного интерфейса.
    Проверка авторизации выполняется на фронтенде через JS.
    """
    return templates.TemplateResponse("office.html", {"request": request})


# 📁 Получение всех каталогов пользователя
@router.get("/folders")
def get_folders(user: str = Depends(get_current_user)):
    """
    Возвращает список всех каталогов (папок) текущего пользователя.
    Показывает только те, у которых is_folder=True.
    """
    meta = load_meta()
    user_meta = filter_meta_by_owner(meta, user)
    folders = sorted({
        a.get("folder", "root")
        for a in user_meta
        if a.get("is_folder", False)
    })
    return JSONResponse(folders)

# 📂 Получение агентов конкретного каталога пользователя
@router.get("/folder/{folder_name}", response_class=JSONResponse)
async def get_folder_agents(folder_name: str, user: str = Depends(get_current_user)):
    """
    Возвращает всех агентов текущего пользователя внутри заданного каталога.
    """
    meta = load_meta()
    folder = folder_name.strip().lower()
    agents = [
        a for a in meta
        if not a.get("is_folder", False)
        and a.get("folder", "").strip().lower() == folder
        and a.get("owner") == user
    ]
    return JSONResponse(agents)


# 🤖 Получение всех агентов пользователя
@router.get("/agents", response_class=JSONResponse)
async def list_agents(user: str = Depends(get_current_user)):
    """Возвращает список всех агентов текущего пользователя."""
    meta = load_meta()
    agents = [a for a in meta if not a.get("is_folder", False) and a.get("owner") == user]
    return JSONResponse(agents)


# 🧩 Инициализация рабочего окружения пользователя
@router.post("/init_user_workspace")
async def init_user_workspace(user: str = Depends(get_current_user)):
    """
    Гарантирует, что у пользователя есть директория /agents/{user},
    папка root и агент assistant_default.
    """
    meta = load_meta()
    
    # Удаляем старые дубликаты ассистентов этого пользователя
    assistants = [
        a for a in meta
        if a.get("slug") == "assistant_default" and a.get("owner") == user
    ]
    if len(assistants) > 1:
        logger.warning(f"⚠️ Найдено {len(assistants)} ассистентов у пользователя {user}, оставляем одного.")
        keep = min(assistants, key=lambda a: a.get("created_at", ""))
        for extra in assistants:
            if extra != keep:
                try:
                    path = Path(extra.get("path", ""))
                    if path.exists():
                        shutil.rmtree(path)
                    meta.remove(extra)
                except Exception as e:
                    logger.warning(f"Ошибка удаления дубликата ассистента: {e}")
        save_meta(meta)
    
    user_root = ensure_user_root(user)

    # Проверяем наличие root-папки
    has_root = any(
        a.get("is_folder") and a.get("folder") == "root" and a.get("owner") == user
        for a in meta
    )
    if not has_root:
        meta.append({
            "folder": "root",
            "is_folder": True,
            "name": "root",
            "slug": f"folder_root_{user}",
            "owner": user,
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z'
        })
        save_meta(meta)

    # Проверяем наличие assistant_default
    # Проверяем наличие ассистента пользователя (по slug и owner)
    has_default_assistant = any(
        a.get("slug") == "assistant_default"
        and a.get("folder") == "root"
        and a.get("owner") == user
        and Path(a.get("path", "")) == (user_root / "root" / "assistant_default")
        for a in meta
    )

    if not has_default_assistant:
        default_path = user_root / "root" / "assistant_default"
        default_path.mkdir(parents=True, exist_ok=True)

        # === Создаём полноценный Amvera LLM-бот ===
        bot_code = """import os
            import re
            import base64
            import logging
            import requests
            from fastapi import FastAPI, Request
            from telegram import Update
            from langchain_amvera import AmveraLLM
            from dotenv import load_dotenv
            from pathlib import Path

            # === Загрузка переменных окружения ===
            load_dotenv()

            # --- ЛОГИРОВАНИЕ ---
            logger = logging.getLogger("agent")
            logger.setLevel(logging.DEBUG)
            log_dir = Path(__file__).parent
            fh = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(fh)

            # --- КОНСТАНТЫ ---
            AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
            AMVERA_MODEL = os.getenv("AMVERA_MODEL", "gpt-4.1")

            if not AMVERA_API_KEY:
                logger.warning("⚠️ AMVERA_API_KEY не найден! Установите его в .env")

            TELEGRAM_TOKEN = globals().get("TELEGRAM_TOKEN", None)
            TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

            PROMPT = 'Ты корпоративный ассистент. Отвечай кратко и по делу.'

            app = FastAPI()
            llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)


            def send_message(chat_id: int, text: str, parse_mode="Markdown"):
                if not TELEGRAM_API_URL:
                    logger.debug(f"[NoTelegram] -> {chat_id}: {text[:120]}")
                    return
                try:
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage",
                                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}, timeout=10)
                except Exception as e:
                    logger.warning(f"Ошибка при отправке Telegram-сообщения: {e}")


            def process_llm_response(chat_id: int, response: str):
                pattern = re.compile(r"```(.*?)```|(https?://[^\s]+\\.(?:png|jpg|jpeg|gif|webp))|(data:image[^\s]+)", re.DOTALL)
                last_end = 0
                for match in pattern.finditer(response):
                    start, end = match.span()
                    if start > last_end:
                        text_chunk = response[last_end:start].strip()
                        if text_chunk:
                            send_message(chat_id, text_chunk)
                    if match.group(1):
                        send_message(chat_id, f"```\n{match.group(1)}\n```")
                    elif match.group(2):
                        send_message(chat_id, f"🖼 {match.group(2)}")
                    elif match.group(3):
                        send_message(chat_id, "📸 [Изображение base64]")
                    last_end = end
                if last_end < len(response):
                    tail = response[last_end:].strip()
                    if tail:
                        send_message(chat_id, tail)


            def handle_task(task: str):
                try:
                    if not AMVERA_API_KEY:
                        return "⚠️ Ошибка: отсутствует AMVERA_API_KEY. Укажите его в .env"

                    if not task:
                        return "⚠️ Ошибка: пустая задача"

                    query = PROMPT + "\\n\\nПользователь: " + task.strip()
                    logger.info(f"Запрос к LLM: {query[:120]}...")

                    if len(query) > 4000:
                        query = query[-4000:]
                    resp = llm.invoke(query)

                    if hasattr(resp, "content"):
                        return resp.content
                    elif isinstance(resp, dict) and "content" in resp:
                        return resp["content"]
                    elif isinstance(resp, str):
                        return resp
                    else:
                        return str(resp)

                except Exception as e:
                    logger.exception(f"Ошибка LLM: {e}")
                    return f"⚠️ Ошибка при обработке запроса: {e}"


            @app.post("/webhook")
            async def webhook(request: Request):
                try:
                    data = await request.json()
                    update = Update.de_json(data, None)
                    if update.message and update.message.text:
                        user_text = update.message.text
                        chat_id = update.message.chat.id
                        result = handle_task(user_text)
                        process_llm_response(chat_id, result)
                    return {"ok": True}
                except Exception as e:
                    logger.exception(f"Ошибка Webhook: {e}")
                    return {"ok": False, "error": str(e)}
            """

        (default_path / "bot.py").write_text(bot_code, encoding="utf-8")

        entry = {
            "name": "Ассистент",
            "slug": "assistant_default",
            "folder": "root",
            "is_folder": False,
            "owner": user,
            "created_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            "path": str(default_path),
            "deploy_url": "",
            "status": "ready"
        }
        meta.append(entry)
        save_meta(meta)
        logger.info(f"✅ Создан assistant_default с Amvera LLM для пользователя {user}")
    else:
        logger.info(f"ℹ️ assistant_default уже существует для пользователя {user}")

    return {"ok": True, "message": f"Рабочее окружение {user} готово"}




# 🧾 Получение информации о текущем пользователе
@router.get("/me", response_class=JSONResponse)
async def get_user_info(user: str = Depends(get_current_user)):
    """Простая проверка токена — возвращает имя текущего пользователя."""
    return JSONResponse({"ok": True, "user": user})
