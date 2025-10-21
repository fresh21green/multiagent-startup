import logging
import asyncio
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from utils import load_meta, call_agent_local, save_memory

router = APIRouter()
logger = logging.getLogger("manager")

@router.post("/brainstorm")
async def brainstorm(topic: str = Form(...)):
    """
    Мозговой штурм между агентами (последовательное обсуждение).
    Каждый агент видит ответы предыдущих.
    """
    meta = load_meta()
    agents = [a for a in meta if not a.get("is_folder")]
    if not agents:
        raise HTTPException(status_code=404, detail="Нет агентов для мозгового штурма")

    # Сортировка по ролям для консистентности
    role_order = ["strategist", "copywriter", "designer", "assistant_default"]
    ordered = sorted(agents, key=lambda a: role_order.index(a["slug"]) if a["slug"] in role_order else 99)

    discussion = []
    summary = ""

    for agent in ordered:
        try:
            path = Path(agent["path"])
            if not (path / "bot.py").exists():
                logger.warning(f"⚠️ У агента {agent['slug']} нет bot.py, пропуск.")
                continue

            # Контекст мозгового штурма
            full_context = "\n\n".join(f"{d['agent']}: {d['response']}" for d in discussion)
            truncated = full_context[-1500:]
            if ". " in truncated:
                context_sent = truncated.split(". ", 1)[-1]
            else:
                context_sent = truncated

            message = (
                f"🧩 Тема мозгового штурма: {topic}\n\n"
                f"Вот что уже предложили другие участники:\n{context_sent}\n\n"
                f"Теперь твой ответ, {agent['name']}:"
            )

            res = await call_agent_local(path, message)
            answer = res.get("result") if isinstance(res, dict) else str(res)
            discussion.append({"agent": agent["name"], "response": answer})

            save_memory(path, {
                "task": f"Brainstorm: {topic}",
                "context": full_context,
                "result": answer
            })

        except Exception as e:
            logger.exception(f"Ошибка при штурме агента {agent['slug']}: {e}")
            discussion.append({"agent": agent["name"], "response": f"⚠️ Ошибка: {e}"})

    # Ассистент суммирует общий вывод
    assistant = next((a for a in agents if a["slug"] == "assistant_default"), None)
    if assistant:
        try:
            summary_text = (
                "📊 Суммируй идеи и предложи общий вывод:\n\n" +
                "\n\n".join(f"{d['agent']}: {d['response'][:800]}" for d in discussion)
            )
            summary_text = summary_text[-2500:]
            res = await call_agent_local(Path(assistant["path"]), summary_text)
            summary = res.get("result") if isinstance(res, dict) else str(res)
        except Exception as e:
            summary = f"⚠️ Ошибка при суммировании: {e}"

    return JSONResponse({"ok": True, "topic": topic, "discussion": discussion, "summary": summary})


@router.get("/brainstorm/stream")
async def brainstorm_stream(topic: str):
    async def gen():
        for agent in agents_in_order():
            res = await call_agent_local(... )
            yield f"data: {json.dumps({'agent': agent, 'text': res})}\n\n"
        yield f"data: {json.dumps({'summary': '...'} )}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
