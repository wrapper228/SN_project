# SN Project

Study project with explicit separation between:

- Telegram frontend
- FastAPI cloud backend
- local Windows execution client

## Repository Layout

- `bot/` - Telegram interface for the user
- `backend/` - task API, queue/state, interrupts, task events
- `client/` - local Windows agent client and watchdog
- `client/agent/` - migrated computer-use runtime
- `shared/` - shared Pydantic schemas between components

## Demo Flow

1. User sends a task to the Telegram bot.
2. Bot posts the task to the FastAPI backend.
3. Local Windows client polls the backend and claims the task.
4. The client runs the existing computer-control agent locally.
5. Task events, screenshots, and final result return to the backend.
6. Telegram frontend shows progress and final status to the user.

## Run

Backend:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Telegram frontend:

```bash
python -m bot.app
```

Local Windows client:

```bash
python -m client.watchdog
```
# SN_project
