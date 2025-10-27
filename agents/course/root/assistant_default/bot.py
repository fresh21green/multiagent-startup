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
                pattern = re.compile(r"```(.*?)```|(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp))|(data:image[^\s]+)", re.DOTALL)
                last_end = 0
                for match in pattern.finditer(response):
                    start, end = match.span()
                    if start > last_end:
                        text_chunk = response[last_end:start].strip()
                        if text_chunk:
                            send_message(chat_id, text_chunk)
                    if match.group(1):
                        send_message(chat_id, f"```
{match.group(1)}
```")
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

                    query = PROMPT + "\n\nПользователь: " + task.strip()
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
            