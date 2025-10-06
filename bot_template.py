BOT_TEMPLATE = '''import os
import requests
import re
import base64
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv

load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
AMVERA_MODEL = "gpt-4.1"

TELEGRAM_TOKEN = "{telegram_token}"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{telegram_token}"
PROMT = """{prompt}"""

llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)
app = FastAPI()

def send_message(chat_id: int, text: str, parse_mode="Markdown"):
    payload = {{"chat_id": chat_id, "text": text, "parse_mode": parse_mode}}
    requests.post(f"{{TELEGRAM_API_URL}}/sendMessage", json=payload)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, None)

    if update.message and update.message.text:
        user_text = update.message.text
        chat_id = update.message.chat.id
        resp = llm.invoke(f"{{PROMT}}\\n\\nПользователь: {{user_text}}")
        reply_text = resp.content if hasattr(resp, "content") else str(resp)
        send_message(chat_id, reply_text)

    return {{"ok": True}}
'''
