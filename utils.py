
import importlib
import logging
import json
from pathlib import Path  

logger = logging.getLogger("manager")
BASE = Path(__file__).parent
AGENTS_DIR = BASE / "agents"
AGENTS_DIR.mkdir(exist_ok=True)
META_FILE = AGENTS_DIR / "workers.json"
if not META_FILE.exists():
    META_FILE.write_text('[]', encoding='utf-8')
async def call_agent_local(path: Path, task: str):
    # try to import module and call handle_task if exists
    try:
        spec = importlib.util.spec_from_file_location(f"agent_{path.name}", str(path / 'bot.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, 'handle_task'):
            logger.info("Calling local handle_task for %s", path.name)
            res = mod.handle_task(task)
            return {'ok': True, 'source': 'local', 'result': res}
        else:
            logger.warning("Local module has no handle_task: %s", path)
            return {'ok': False, 'error': 'no_handle_task'}
    except Exception as e:
        logger.exception("Error calling local agent: %s", e)
        return {'ok': False, 'error': str(e)}

async def call_agent_remote(url: str, task: str):
    import requests
    try:
        payload = {'message': {'message_id':1, 'from':{'id':1111,'is_bot':False,'first_name':'Manager'}, 'chat':{'id':123456,'type':'private'}, 'date': int(__import__('time').time()), 'text': task}}
        r = requests.post(url.rstrip('/') + '/webhook', json=payload, timeout=20)
        logger.info("Remote agent %s responded with status %s", url, r.status_code)
        return {'ok': True, 'source': 'remote', 'status': r.status_code, 'text': r.text}
    except Exception as e:
        logger.exception("Error calling remote agent: %s", e)
        return {'ok': False, 'error': str(e)}
def load_meta():
    try:
        return json.loads(META_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        logger.exception("Failed to load metadata: %s", e)
        return []

def save_meta(meta):
    try:
        META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        logger.exception("Failed to save metadata: %s", e)