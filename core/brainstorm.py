import logging
from pathlib import Path
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from utils import load_meta, save_memory, call_agent_local, call_agent_remote

logger = logging.getLogger("manager")
router = APIRouter()

@router.post("/delegate_task")
async def delegate_task(from_slug: str = Form(...), to_slug: str = Form(...), message: str = Form(...)):
    meta = load_meta()
    from_agent = next((a for a in meta if a.get("slug") == from_slug and not a.get("is_folder")), None)
    to_agent   = next((a for a in meta if a.get("slug") == to_slug   and not a.get("is_folder")), None)
    if not from_agent or not to_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    res = None
    try:
        to_path = Path(to_agent.get("path") or "")
        if to_path.exists():
            res = await call_agent_local(to_path, f"Сообщение от {from_agent['name']}: {message}")
        elif to_agent.get("deploy_url"):
            res = await call_agent_remote(to_agent["deploy_url"], f"Сообщение от {from_agent['name']}: {message}")
        else:
            raise RuntimeError("no_local_or_remote")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        save_memory(Path(from_agent["path"]), {"date": __import__("datetime").datetime.utcnow().isoformat()+"Z",
                   "task": f"Отправил {to_agent['name']}: {message}", "result": res.get("result") if isinstance(res, dict) else str(res)})
        save_memory(Path(to_agent["path"]), {"date": __import__("datetime").datetime.utcnow().isoformat()+"Z",
                   "task": f"Получил от {from_agent['name']}: {message}", "result": (res.get("result") or res.get("text")) if isinstance(res, dict) else str(res)})
    except Exception:
        pass
    return JSONResponse({"ok": True, "result": res})

@router.post("/add_connection")
async def add_connection(from_slug: str = Form(...), to_slug: str = Form(...)):
    from utils import load_meta, save_meta
    meta = load_meta()
    from_agent = next((a for a in meta if a.get("slug") == from_slug and not a.get("is_folder")), None)
    to_agent   = next((a for a in meta if a.get("slug") == to_slug   and not a.get("is_folder")), None)
    if not from_agent or not to_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    conns = from_agent.get("connections") or []
    if to_slug not in conns:
        conns.append(to_slug)
        from_agent["connections"] = conns
        save_meta(meta)
        return JSONResponse({"ok": True, "added": True})
    return JSONResponse({"ok": True, "added": False, "message": "already_exists"})

@router.post("/brainstorm")
async def brainstorm(topic: str = Form(...)):
    meta = load_meta()
    agents = [a for a in meta if not a.get("is_folder")]
    if not agents:
        raise HTTPException(status_code=404, detail="Нет агентов для мозгового штурма")

    role_order = ["strategist", "copywriter", "designer", "assistant_default"]
    ordered_agents = sorted(agents, key=lambda a: role_order.index(a["slug"]) if a["slug"] in role_order else 99)

    discussion = []
    summary = ""

    for agent in ordered_agents:
        try:
            path = Path(agent.get("path") or "")
            if not (path / "bot.py").exists():
                logger.warning(f"У агента {agent['slug']} нет bot.py, пропуск.")
                continue

            full_context = "\n\n".join([f"{d['agent']}: {d['response']}" for d in discussion])
            context_sent = full_context
            if len(context_sent) > 1500:
                truncated = context_sent[-1500:]
                start = truncated.find(". ")
                context_sent = truncated[start+2:] if start != -1 else truncated

            message = (
                f"Тема мозгового штурма: {topic}\n\n"
                f"Вот что уже предложили другие участники:\n{context_sent}\n\n"
                f"Теперь твой ответ, {agent['name']}:"
            )

            res = await call_agent_local(path, message)
            out = res.get("result") if isinstance(res, dict) else str(res)
            discussion.append({"agent": agent["name"], "response": out})

            try:
                save_memory(path, {
                    "date": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                    "task": f"Brainstorm: {topic}",
                    "full_context": full_context,
                    "context_sent": context_sent,
                    "result": out
                })
            except Exception as e:
                logger.warning(f"Ошибка записи памяти агента {agent['slug']}: {e}")

        except Exception as e:
            logger.exception(f"Ошибка при штурме агента {agent['slug']}: {e}")
            discussion.append({"agent": agent["name"], "response": f"⚠️ Ошибка: {e}"})

    assistant = next((a for a in agents if a["slug"] == "assistant_default"), None)
    if assistant:
        try:
            summary_msg = (
                "Суммируй результаты обсуждения и предложи общий вывод:\n\n" +
                "\n\n".join([f"{d['agent']}: {d['response'][:600]}" for d in discussion])
            )
            if len(summary_msg) > 2000:
                summary_msg = summary_msg[-2000:]
            path = Path(assistant["path"])
            res = await call_agent_local(path, summary_msg)
            summary = res.get("result") if isinstance(res, dict) else str(res)
        except Exception as e:
            summary = f"⚠️ Ошибка при суммировании: {e}"

    return JSONResponse({"ok": True, "topic": topic, "discussion": discussion, "summary": summary})
