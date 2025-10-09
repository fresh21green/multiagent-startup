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
print("AMVERA_API_KEY:", AMVERA_API_KEY)
AMVERA_MODEL = 'gpt-4.1'

# manager will replace placeholder text
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

PROMT = """Обьясняй для детей до 7 лет"""

llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)
app = FastAPI()

def send_message(chat_id: int, text: str, parse_mode='Markdown'):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    try:
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
    except Exception as e:
        logger.exception('Failed to send message: %s', e)

def process_llm_response(chat_id: int, response: str):
    # simplified: just send full text
    try:
        send_message(chat_id, response)
    except Exception as e:
        logger.exception('Error processing llm response: %s', e)

def handle_task(task: str):
    """Function used by manager when agent is local: calls LLM and returns result."""
    logger.info('handle_task called with task: %s', task)
    try:
        full = (PROMT or '') + '\nUser: ' + task
        resp = llm.invoke(full)
        text = getattr(resp, 'content', str(resp))
        logger.info('LLM returned: %s', str(text)[:200])
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
