BOT_TEMPLATE = """import os
import requests
import re
import base64
from fastapi import FastAPI, Request
from telegram import Update
from langchain_amvera import AmveraLLM
from dotenv import load_dotenv

load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
TELEGRAM_TOKEN = "{telegram_token}"
PROMT = """{prompt}"""

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
llm = AmveraLLM(model="gpt-4.1", api_token=AMVERA_API_KEY)
app = FastAPI()

def send_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, None)
    if update.message and update.message.text:
        chat_id = update.message.chat.id
        user_text = update.message.text
        resp = llm.invoke(f"{PROMT}\n{user_text}")
        send_message(chat_id, resp.content if hasattr(resp, "content") else str(resp))
    return {"ok": True}
"""
