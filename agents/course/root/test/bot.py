import os
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
AMVERA_MODEL = os.getenv("AMVERA_MODEL", "gpt")

# === Проверка ключа и модели ===
if not AMVERA_API_KEY:
    logger.warning("⚠️ AMVERA_API_KEY не найден! Установите его в .env")
if not AMVERA_MODEL:
    AMVERA_MODEL = "gpt-4.1"


# Здесь менеджер подставит реальные данные
TELEGRAM_TOKEN = globals().get("TELEGRAM_TOKEN", None)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

# Подсказка (промпт) агента
PROMPT = """(данные не получены)"""

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI()
# Поддерживаемые модели: llama8b, llama70b, gpt-4.1, gpt-5
llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def send_message(chat_id: int, text: str, parse_mode="Markdown"):
    if not TELEGRAM_API_URL:
        # Логируем, но не падаем
        logger.debug(f"[NoTelegram] -> {chat_id}: {text[:120]}")
        return
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=30)
    except Exception as e:
        logger.warning(f"Ошибка при отправке Telegram-сообщения: {e}")


def process_llm_response(chat_id: int, response: str):
    """
    Обрабатывает ответ LLM:
    - выделяет текст, код, изображения
    - отправляет их пользователю (если Telegram используется)
    """
    pattern = re.compile(
        r"```(.*?)```|(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp))|(data:image[^\s]+)",
        re.DOTALL
    )

    last_end = 0
    for match in pattern.finditer(response):
        start, end = match.span()

        if start > last_end:
            text_chunk = response[last_end:start].strip()
            if text_chunk:
                send_message(chat_id, text_chunk)

        if match.group(1):  # код
            send_message(chat_id, f"```\n{match.group(1)}\n```")
        elif match.group(2):  # URL изображения
            send_message(chat_id, f"🖼 {match.group(2)}")
        elif match.group(3):  # base64 изображение
            send_message(chat_id, "📸 [Изображение base64]")
        last_end = end

    if last_end < len(response):
        tail = response[last_end:].strip()
        if tail:
            send_message(chat_id, tail)


# === ГЛАВНАЯ ФУНКЦИЯ ===

def handle_task(task: str):
    """
    Выполняет задачу агента через LLM Amvera.
    Возвращает чистый текст результата.
    """
    if isinstance(task, str) and len(task) > 4000:
        task = task[-4000:]

    try:
        if not AMVERA_API_KEY:
            return "⚠️ Ошибка: отсутствует AMVERA_API_KEY. Укажите его в .env"

        if not task or not isinstance(task, str):
            return "⚠️ Ошибка: пустая задача"

        query = (PROMPT or "") + "\n\nПользователь: " + task.strip()
        logger.info(f"Запрос к LLM: {query[:120]}...")

        # Основной вызов LLM
        if len(query) > 4000:
            logger.warning(f"⚠️ Контекст слишком длинный ({len(query)} символов) — обрезаем до 4000.")
            query = query[-4000:]
        resp = llm.invoke(query)
        

        # Обработка результатов
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


# === TELEGRAM WEBHOOK ===
@app.post("/webhook")
async def webhook(request: Request):
    """Обрабатывает входящие Telegram-сообщения."""
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
