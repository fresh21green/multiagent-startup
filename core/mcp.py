import json, os, datetime

CONTEXT_PATH = "data/context"

def load_context(agent_id):
    path = os.path.join(CONTEXT_PATH, f"{agent_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_context(agent_id, context):
    os.makedirs(CONTEXT_PATH, exist_ok=True)
    path = os.path.join(CONTEXT_PATH, f"{agent_id}.json")
    context["_updated"] = datetime.datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

def merge_contexts(*contexts):
    merged = {}
    for c in contexts:
        for k, v in c.items():
            if k not in merged:
                merged[k] = v
    return merged
