# Architecture

The project is split into three separate applications.

- `bot/` is the frontend. It talks to the user in Telegram and shows task progress.
- `backend/` is the cloud FastAPI service. It stores tasks, interrupts, task events, and client status.
- `client/` is the local Windows process. It polls the backend, runs the computer-use agent, and reports progress back.

The execution path is:

1. Telegram message arrives in `bot/`.
2. `bot/` creates a task through the backend API.
3. `client/` polls `/api/v1/client/next-task` and claims the task.
4. `client/agent/` executes the task on the local PC using the migrated runtime from the original prototype.
5. Events and completion are posted to the backend.
6. `bot/` polls task state and events and sends progress back to Telegram.
