import os
import requests
import re
import base64
import logging
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv

load_dotenv()

# setup logger for agent
logger = logging.getLogger('agent')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('agent.log', encoding='utf-8')
fh.setLevel(logging.DEBUG)
fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(fmt)
logger.addHandler(fh)

AMVERA_API_KEY = os.getenv('AMVERA_API_KEY')
AMVERA_MODEL = 'gpt-4.1'

# manager will replace placeholder text
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

PROMPT = """Трудолюбивый,юморной,бубука,обидчивый,быстро отходчивый,добрый,строгий,сильный,любит пиво,любитель поспорить, упрямый,надежный,ценит дружбу,однолюб."""

llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)
app = FastAPI()

def send_message(chat_id: int, text: str, parse_mode="Markdown", reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)

def send_photo(chat_id: int, photo_url: str, caption=None):
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    requests.post(f"{TELEGRAM_API_URL}/sendPhoto", json=payload)

def send_photo_file(chat_id: int, image_bytes: bytes, caption=None):
    files = {"photo": ("image.png", image_bytes)}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(f"{TELEGRAM_API_URL}/sendPhoto", data=data, files=files)

def process_llm_response(chat_id: int, response: str):
    """
    Обрабатывает сложный ответ модели (текст, markdown, код, изображения)
    и красиво отправляет его пользователю.
    """
    logger.info("Processing LLM response for chat %s", chat_id)

    # Регулярка: блоки кода, картинки (URL или base64)
    pattern = re.compile(
        r"```(.*?)```|(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp))|(data:image[^\s]+)",
        re.DOTALL
    )

    last_end = 0
    for match in pattern.finditer(response):
        start, end = match.span()

        # --- Отправляем текст между блоками ---
        if start > last_end:
            text_chunk = response[last_end:start].strip()
            if text_chunk:
                send_message(chat_id, text_chunk, parse_mode="Markdown")

        # --- Отправляем код-блок ---
        if match.group(1):
            code_block = match.group(1)
            if "\n" in code_block:
                lang, code = code_block.split("\n", 1)
            else:
                lang, code = "text", code_block

            formatted = f"```{lang}\n{code.strip()}\n```"
            send_message(chat_id, formatted, parse_mode="Markdown")

        # --- Отправляем изображение по ссылке ---
        elif match.group(2):
            img_url = match.group(2)
            send_photo(chat_id, img_url, caption="🖼 Изображение")

        # --- Отправляем base64 изображение ---
        elif match.group(3):
            try:
                header, encoded = match.group(3).split(",", 1)
                image_bytes = base64.b64decode(encoded)
                send_photo_file(chat_id, image_bytes, caption="🖼 Сгенерированное изображение")
            except Exception as e:
                logger.exception("Ошибка обработки base64: %s", e)
                send_message(chat_id, "⚠️ Ошибка при обработке изображения")

        last_end = end

    # --- Хвостовой текст ---
    if last_end < len(response):
        tail = response[last_end:].strip()
        if tail:
            send_message(chat_id, tail, parse_mode="Markdown")

def handle_task(task: str):
    """Function used by manager when agent is local: calls LLM and returns result."""
    logger.info('handle_task called with task: %s', task)
    try:
        full = (PROMPT or '') + '\nUser: ' + task
        resp = llm.invoke(full)
        if hasattr(resp, "content"):
            text = resp.content
        elif isinstance(resp, dict) and "content" in resp:
            text = resp["content"]
        else:
            text = str(resp)
        return text
    except Exception as e:
        logger.exception('Error in handle_task: %s', e)
        return f'Error: {e}'
    
@app.post('/webhook')
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, None)
    if update.message and update.message.text:
        user_text = update.message.text
        chat_id = update.message.chat.id
        try:
            result = handle_task(user_text)
            process_llm_response(chat_id, result)
        except Exception as e:
            logger.exception('Webhook processing failed: %s', e)
    return {'ok': True}
