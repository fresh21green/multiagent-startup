from fastapi import APIRouter, Form, Depends
from fastapi.responses import JSONResponse
from core.auth import get_current_user
from utils import call_agent_with_context, save_memory
from core.mcp import load_context, save_context, merge_contexts
from utils import load_meta
from pathlib import Path
import asyncio, json, logging

logger = logging.getLogger("brainstorm")
router = APIRouter()

@router.post("/brainstorm")
async def brainstorm(
    folder: str = Form(...),
    topic: str = Form(...),
    user: str = Depends(get_current_user)
):
    """
    💡 Режим коллективного генератора идей (Brainstorm)
    Каждый агент предлагает идеи по теме, учитывая роль и контекст коллег.
    """
    meta = load_meta()
    agents_in_folder = [
        a for a in meta
        if a.get("folder") == folder
        and not a.get("is_folder")
        and a.get("owner") == user
    ]
    if not agents_in_folder:
        return JSONResponse({"ok": False, "error": f"Нет сотрудников в каталоге '{folder}'"}, status_code=404)

    # 🧠 Общий контекст
    all_contexts = {a["slug"]: load_context(a["slug"]) for a in agents_in_folder}
    merged_context = merge_contexts(*all_contexts.values())
    context_text = json.dumps(merged_context, ensure_ascii=False, indent=2)

    results = []

    async def handle(agent):
        slug = agent["slug"]
        try:
            prompt = (
                f"💡 Мозговой штурм по теме:\n{topic}\n\n"
                f"📘 Контексты коллег:\n{context_text}\n\n"
                f"Ты — {slug}. Сгенерируй креативные идеи, "
                f"основанные на знаниях команды и своей специализации."
            )
            res = await call_agent_with_context(agent, prompt)
            result_text = res.get("result") if isinstance(res, dict) else str(res)

            save_memory(Path(agent["path"]), {"task": f"Brainstorm: {topic}", "result": result_text})
            ctx = load_context(slug)
            ctx["brainstorm_topic"] = topic
            ctx["brainstorm_result"] = result_text
            ctx["colleague_contexts"] = list(all_contexts.keys())
            save_context(slug, ctx)

            results.append({"agent": slug, "result": result_text})
        except Exception as e:
            logger.exception(f"[brainstorm] Ошибка у агента {slug}: {e}")
            results.append({"agent": slug, "error": str(e)})

    await asyncio.gather(*[handle(a) for a in agents_in_folder])
    return JSONResponse({"ok": True, "folder": folder, "topic": topic, "results": results})
