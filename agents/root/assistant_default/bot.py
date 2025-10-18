from langchain_amvera import AmveraLLM
import os
from dotenv import load_dotenv
load_dotenv()

AMVERA_API_KEY = os.getenv("AMVERA_API_KEY")
AMVERA_MODEL = os.getenv("AMVERA_MODEL", "gpt-4o-mini")
llm = AmveraLLM(model=AMVERA_MODEL, api_token=AMVERA_API_KEY)

PROMPT = """Ты ассистент и модератор команды. 
Обобщай ответы участников, выявляй общие идеи и предлагай общий вывод."""

def handle_task(task: str):
    query = PROMPT + "\n\n" + task
    resp = llm.invoke(query)
    return getattr(resp, "content", str(resp))