multiagent-manager (updated)

This version supports:
- create/delete agents (each agent stored in agents/<slug>/bot.py)
- assign tasks to agents; if agent has deploy_url manager will POST to /webhook,
  otherwise manager will call local handle_task function in agent's bot.py.
- logging: manager.log in logs/, agent local logs saved as agents/<slug>/agent.log

How to use:
- fill .env with AMVERA_API_KEY etc
- run locally: uvicorn main:app --reload
- create agent via web UI at /
- assign task to agent via the form; results will be shown and saved in agents/workers.json
- to auto-deploy workers, ensure create_and_push.sh env vars are set and run with auto deploy in UI (if enabled)
