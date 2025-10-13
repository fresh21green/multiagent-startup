import os
import re
import base64
import logging
import requests
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv

# Загружаем переменные окружения (.env)
load_dotenv()

# --- ЛОГИРОВАНИЕ ---
logger = logging.getLogger("agent")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler("agent.log", encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(fh)

# --- КОНСТАНТЫ И НАСТРОЙКИ ---
AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
AMVERA_MODEL = "gpt-4.1"

# Здесь менеджер подставит реальные данные
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Подсказка (промпт) агента
PROMPT = """sdasd"""

# --- ИНИЦИАЛИЗАЦИЯ LLM И API ---
llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)
app = FastAPI()


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def send_message(chat_id: int, text: str, parse_mode="Markdown", reply_markup=None):
    """Отправляет текстовое сообщение пользователю."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)


def send_photo(chat_id: int, photo_url: str, caption=None):
    """Отправляет изображение по URL."""
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    requests.post(f"{TELEGRAM_API_URL}/sendPhoto", json=payload)


def send_photo_file(chat_id: int, image_bytes: bytes, caption=None):
    """Отправляет изображение в виде файла (например, из base64)."""
    files = {"photo": ("image.png", image_bytes)}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(f"{TELEGRAM_API_URL}/sendPhoto", data=data, files=files)


def process_llm_response(chat_id: int, response: str):
    """
    Обрабатывает ответ LLM:
    - Разделяет блоки текста, кода и изображений.
    - Отправляет их пользователю в Telegram красиво и последовательно.
    """
    logger.info("Processing LLM response for chat %s", chat_id)

    # Регулярка для Markdown-блоков, ссылок и base64
    pattern = re.compile(
        r"```(.*?)```|(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp))|(data:image[^\s]+)",
        re.DOTALL
    )

    last_end = 0
    for match in pattern.finditer(response):
        start, end = match.span()

        # Отправляем текст между блоками
        if start > last_end:
            text_chunk = response[last_end:start].strip()
            if text_chunk:
                send_message(chat_id, text_chunk, parse_mode="Markdown")

        # --- Код-блок ---
        if match.group(1):
            code_block = match.group(1)
            if "\n" in code_block:
                lang, code = code_block.split("\n", 1)
            else:
                lang, code = "text", code_block
            send_message(chat_id, f"```{lang}\n{code.strip()}\n```")

        # --- Изображение по ссылке ---
        elif match.group(2):
            send_photo(chat_id, match.group(2), caption="🖼 Изображение")

        # --- Base64 изображение ---
        elif match.group(3):
            try:
                header, encoded = match.group(3).split(",", 1)
                send_photo_file(chat_id, base64.b64decode(encoded), caption="🖼 Сгенерированное изображение")
            except Exception as e:
                logger.exception("Ошибка при обработке base64: %s", e)
                send_message(chat_id, "⚠️ Ошибка при обработке изображения")

        last_end = end

    # Отправляем "хвост" текста
    if last_end < len(response):
        tail = response[last_end:].strip()
        if tail:
            send_message(chat_id, tail, parse_mode="Markdown")


# === ОСНОВНОЙ ИНТЕРФЕЙС ===

def handle_task(task: str):
    """
    Выполняет задачу агента локально (через LLM).
    Вызывается менеджером или вебхуком.
    """
    logger.info("handle_task called with task: %s", task)
    try:
        query = (PROMPT or "") + "\nUser: " + task
        resp = llm.invoke(query)

        if hasattr(resp, "content"):
            return resp.content
        elif isinstance(resp, dict) and "content" in resp:
            return resp["content"]
        return str(resp)

    except Exception as e:
        logger.exception("Error in handle_task: %s", e)
        return f"Error: {e}"


@app.post("/webhook")
async def webhook(request: Request):
    """Обрабатывает входящие сообщения Telegram через webhook."""
    logger.info("request: %s", request)
    data = await request.json()
    update = Update.de_json(data, None)
    
    if update.message and update.message.text:
        user_text = update.message.text
        chat_id = update.message.chat.id
        try:
            result = handle_task(user_text)
            process_llm_response(chat_id, result)
        except Exception as e:
            logger.exception("Webhook processing failed: %s", e)

    return {"ok": True}
