# Distributed Telegram Computer Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the copied local prototype into a clean study project with a Telegram frontend, a cloud FastAPI backend, and a separate local Windows execution client while preserving computer-control functionality.

**Architecture:** The backend becomes the source of truth for tasks, events, interrupts, memory snapshots, usage stats, and client presence. The Telegram bot becomes a thin frontend adapter that only forwards user input and renders backend state, while the Windows client owns local agent execution and periodically polls the backend for work.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, sqlite3, httpx, python-telegram-bot, pytest, Anthropic SDK, pyautogui, mss, Pillow

---

## Planned File Structure

### New files and directories

- `backend/__init__.py`
- `backend/app.py`
- `backend/config.py`
- `backend/service.py`
- `backend/storage.py`
- `bot/__init__.py`
- `bot/app.py`
- `bot/backend_api.py`
- `client/__init__.py`
- `client/app.py`
- `client/backend_api.py`
- `client/polling.py`
- `client/agent/__init__.py`
- `client/agent/loop.py`
- `client/agent/memory.py`
- `client/agent/fact_extractor.py`
- `client/agent/tools/__init__.py`
- `client/agent/tools/base.py`
- `client/agent/tools/collection.py`
- `client/agent/tools/computer.py`
- `client/agent/tools/run.py`
- `client/watchdog.py`
- `shared/__init__.py`
- `shared/schemas.py`
- `tests/shared/test_schemas.py`
- `tests/backend/test_service.py`
- `tests/backend/test_app.py`
- `tests/bot/test_backend_api.py`
- `tests/client/test_backend_api.py`
- `tests/client/test_polling.py`
- `tests/integration/test_task_flow.py`
- `docs/architecture.md`
- `docs/deployment.md`

### Existing files to modify

- `requirements.txt`
- `README.md`
- `watchdog.py`
- `src/loop.py`
- `src/memory.py`
- `src/fact_extractor.py`
- `src/tools/__init__.py`
- `src/tools/base.py`
- `src/tools/collection.py`
- `src/tools/computer.py`
- `src/tools/run.py`
- `src/telegram_bot.py`
- `src/main.py`

### Existing files and folders to remove in the final cleanup task

- `CHANGELOG.md`
- `RELEASE_NOTES_v0.4.0.txt`
- `RELEASE_NOTES_v0.4.1.txt`
- `RELEASE_NOTES_v0.4.2.txt`
- `UPGRADE_v0.4.0.md`
- `UPGRADE_v0.4.1.md`
- `UPGRADE_v0.4.2.md`
- `run_agent.bat`
- `run_console.bat`
- `docs/research/`
- `docs/big_problems_using_llm_in_agentic_mode/`
- legacy docs that describe the old monolithic topology

## Conventions for All Tasks

- Use `sqlite3` directly instead of adding an ORM.
- Keep one active user, one client, and one task at a time.
- Prefer copying the current `src/` runtime into `client/agent/` first, then delete the old monolithic wiring later.
- Keep backend APIs synchronous in semantics even if implemented with async FastAPI endpoints.
- Use backend-owned persistence for long-lived state; the client may keep in-memory runtime data only during task execution.

### Task 1: Create the shared contract and project skeleton

**Files:**
- Create: `shared/__init__.py`
- Create: `shared/schemas.py`
- Test: `tests/shared/test_schemas.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write the failing schema tests**

```python
# tests/shared/test_schemas.py
from shared.schemas import (
    ClientHeartbeat,
    InterruptRecord,
    TaskCreateRequest,
    TaskEventCreate,
    TaskRecord,
    TaskStatus,
)


def test_task_create_request_accepts_chat_id_and_text():
    payload = TaskCreateRequest(chat_id=1001, text="Open calculator")
    assert payload.chat_id == 1001
    assert payload.text == "Open calculator"


def test_task_record_defaults_to_pending():
    record = TaskRecord(id="task-1", chat_id=1001, text="Open calculator")
    assert record.status is TaskStatus.PENDING


def test_event_record_can_hold_screenshot_metadata():
    event = TaskEventCreate(
        task_id="task-1",
        event_type="screenshot",
        message="Desktop captured",
        image_base64="abc123",
    )
    assert event.event_type == "screenshot"
    assert event.image_base64 == "abc123"


def test_interrupt_record_defaults_to_unconsumed():
    interrupt = InterruptRecord(task_id="task-1", text="Stop and use Chrome")
    assert interrupt.consumed is False


def test_client_heartbeat_requires_client_id():
    heartbeat = ClientHeartbeat(client_id="desktop-main", is_busy=False)
    assert heartbeat.client_id == "desktop-main"
    assert heartbeat.is_busy is False
```

- [ ] **Step 2: Run the schema tests to verify they fail**

Run: `pytest tests/shared/test_schemas.py -q`

Expected: `ModuleNotFoundError: No module named 'shared'`

- [ ] **Step 3: Add dependencies and implement the shared models**

```text
# requirements.txt
anthropic
fastapi
httpx
mss
pillow
pydantic
pyautogui
python-dotenv
python-telegram-bot
pytest
uvicorn
```

```python
# shared/schemas.py
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskCreateRequest(BaseModel):
    chat_id: int
    text: str = Field(min_length=1)


class TaskRecord(BaseModel):
    id: str
    chat_id: int
    text: str
    status: TaskStatus = TaskStatus.PENDING
    result_text: str = ""


class TaskEventCreate(BaseModel):
    task_id: str
    event_type: str
    message: str = ""
    image_base64: Optional[str] = None


class InterruptRecord(BaseModel):
    task_id: str
    text: str
    consumed: bool = False


class ClientHeartbeat(BaseModel):
    client_id: str
    is_busy: bool
    current_task_id: Optional[str] = None
```

```python
# shared/__init__.py
from .schemas import (
    ClientHeartbeat,
    InterruptRecord,
    TaskCreateRequest,
    TaskEventCreate,
    TaskRecord,
    TaskStatus,
)
```

- [ ] **Step 4: Run the schema tests to verify they pass**

Run: `pytest tests/shared/test_schemas.py -q`

Expected: `5 passed`

- [ ] **Step 5: Commit the shared contract**

```bash
git add requirements.txt shared/__init__.py shared/schemas.py tests/shared/test_schemas.py
git commit -m "feat: add shared task and client schemas"
```

### Task 2: Build backend storage and task service

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/storage.py`
- Create: `backend/service.py`
- Test: `tests/backend/test_service.py`

- [ ] **Step 1: Write the failing backend service tests**

```python
# tests/backend/test_service.py
from pathlib import Path

from backend.service import BackendService
from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskStatus


def test_create_task_persists_pending_task(tmp_path: Path):
    service = BackendService(db_path=tmp_path / "state.db")
    task = service.create_task(TaskCreateRequest(chat_id=1001, text="Open Notepad"))
    assert task.chat_id == 1001
    assert task.status is TaskStatus.PENDING


def test_assign_next_task_marks_it_running(tmp_path: Path):
    service = BackendService(db_path=tmp_path / "state.db")
    created = service.create_task(TaskCreateRequest(chat_id=1001, text="Take screenshot"))
    assigned = service.assign_next_task(client_id="desktop-main")
    assert assigned is not None
    assert assigned.id == created.id
    assert assigned.status is TaskStatus.RUNNING


def test_record_interrupt_and_consume_pending_interrupts(tmp_path: Path):
    service = BackendService(db_path=tmp_path / "state.db")
    task = service.create_task(TaskCreateRequest(chat_id=1001, text="Use browser"))
    service.assign_next_task(client_id="desktop-main")
    service.add_interrupt(task.id, "Stop and use Chrome")
    interrupts = service.consume_interrupts(task.id)
    assert interrupts == ["Stop and use Chrome"]
    assert service.consume_interrupts(task.id) == []


def test_heartbeat_updates_client_presence(tmp_path: Path):
    service = BackendService(db_path=tmp_path / "state.db")
    heartbeat = service.record_heartbeat(ClientHeartbeat(client_id="desktop-main", is_busy=False))
    assert heartbeat.client_id == "desktop-main"
    assert heartbeat.is_busy is False
```

- [ ] **Step 2: Run the backend service tests to verify they fail**

Run: `pytest tests/backend/test_service.py -q`

Expected: import failure for `backend.service`

- [ ] **Step 3: Implement sqlite storage and backend service**

```python
# backend/config.py
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "backend.db"
```

```python
# backend/storage.py
import json
import sqlite3
from pathlib import Path


class SQLiteStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_text TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    image_base64 TEXT
                );
                CREATE TABLE IF NOT EXISTS interrupts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS client_status (
                    client_id TEXT PRIMARY KEY,
                    is_busy INTEGER NOT NULL,
                    current_task_id TEXT,
                    last_heartbeat TEXT NOT NULL
                );
                """
            )
```

```python
# backend/service.py
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from backend.storage import SQLiteStorage
from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskRecord, TaskStatus


class BackendService:
    def __init__(self, db_path: Path):
        self.storage = SQLiteStorage(db_path)

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        task = TaskRecord(id=str(uuid4()), chat_id=request.chat_id, text=request.text)
        with self.storage.connect() as connection:
            connection.execute(
                "INSERT INTO tasks (id, chat_id, text, status, result_text) VALUES (?, ?, ?, ?, ?)",
                (task.id, task.chat_id, task.text, task.status.value, task.result_text),
            )
        return task

    def assign_next_task(self, client_id: str) -> TaskRecord | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT id, chat_id, text, status, result_text FROM tasks WHERE status = ? ORDER BY rowid LIMIT 1",
                (TaskStatus.PENDING.value,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (TaskStatus.RUNNING.value, row["id"]),
            )
            connection.execute(
                "INSERT OR REPLACE INTO client_status (client_id, is_busy, current_task_id, last_heartbeat) VALUES (?, ?, ?, ?)",
                (client_id, 1, row["id"], datetime.now(UTC).isoformat()),
            )
        return TaskRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            text=row["text"],
            status=TaskStatus.RUNNING,
            result_text=row["result_text"],
        )

    def add_interrupt(self, task_id: str, text: str) -> None:
        with self.storage.connect() as connection:
            connection.execute(
                "INSERT INTO interrupts (task_id, text, consumed) VALUES (?, ?, 0)",
                (task_id, text),
            )

    def consume_interrupts(self, task_id: str) -> list[str]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT id, text FROM interrupts WHERE task_id = ? AND consumed = 0 ORDER BY id",
                (task_id,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                connection.executemany(
                    "UPDATE interrupts SET consumed = 1 WHERE id = ?",
                    [(item_id,) for item_id in ids],
                )
        return [row["text"] for row in rows]

    def record_heartbeat(self, heartbeat: ClientHeartbeat) -> ClientHeartbeat:
        with self.storage.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO client_status (client_id, is_busy, current_task_id, last_heartbeat) VALUES (?, ?, ?, ?)",
                (
                    heartbeat.client_id,
                    int(heartbeat.is_busy),
                    heartbeat.current_task_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return heartbeat
```

```python
# backend/__init__.py
from .service import BackendService
```

- [ ] **Step 4: Run the backend service tests to verify they pass**

Run: `pytest tests/backend/test_service.py -q`

Expected: `4 passed`

- [ ] **Step 5: Commit the backend state layer**

```bash
git add backend/__init__.py backend/config.py backend/storage.py backend/service.py tests/backend/test_service.py
git commit -m "feat: add backend task storage service"
```

### Task 3: Expose FastAPI endpoints for bot and client

**Files:**
- Create: `backend/app.py`
- Test: `tests/backend/test_app.py`
- Modify: `backend/service.py`

- [ ] **Step 1: Write the failing API tests**

```python
# tests/backend/test_app.py
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app


def build_client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path / "backend.db")
    return TestClient(app)


def test_frontend_message_creates_task(tmp_path: Path):
    client = build_client(tmp_path)
    response = client.post("/api/v1/frontend/messages", json={"chat_id": 1001, "text": "Open calculator"})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_client_can_poll_next_task(tmp_path: Path):
    client = build_client(tmp_path)
    client.post("/api/v1/frontend/messages", json={"chat_id": 1001, "text": "Take screenshot"})
    response = client.get("/api/v1/client/next-task", params={"client_id": "desktop-main"})
    assert response.status_code == 200
    assert response.json()["task"]["status"] == "running"


def test_client_can_post_event_and_complete_task(tmp_path: Path):
    client = build_client(tmp_path)
    task = client.post("/api/v1/frontend/messages", json={"chat_id": 1001, "text": "Open notepad"}).json()
    assigned = client.get("/api/v1/client/next-task", params={"client_id": "desktop-main"}).json()["task"]
    event_response = client.post(
        f"/api/v1/client/tasks/{assigned['id']}/events",
        json={"task_id": assigned["id"], "event_type": "text", "message": "Working"},
    )
    complete_response = client.post(
        f"/api/v1/client/tasks/{assigned['id']}/complete",
        json={"result_text": "Done", "status": "done"},
    )
    assert event_response.status_code == 200
    assert complete_response.status_code == 200
    assert complete_response.json()["result_text"] == "Done"
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `pytest tests/backend/test_app.py -q`

Expected: import failure for `backend.app`

- [ ] **Step 3: Implement the FastAPI app and missing service methods**

```python
# backend/service.py (append these methods)
from shared.schemas import TaskEventCreate

    def add_event(self, event: TaskEventCreate) -> None:
        with self.storage.connect() as connection:
            connection.execute(
                "INSERT INTO task_events (task_id, event_type, message, image_base64) VALUES (?, ?, ?, ?)",
                (event.task_id, event.event_type, event.message, event.image_base64),
            )

    def complete_task(self, task_id: str, status: TaskStatus, result_text: str) -> TaskRecord:
        with self.storage.connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, result_text = ? WHERE id = ?",
                (status.value, result_text, task_id),
            )
            row = connection.execute(
                "SELECT id, chat_id, text, status, result_text FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return TaskRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            text=row["text"],
            status=TaskStatus(row["status"]),
            result_text=row["result_text"],
        )
```

```python
# backend/app.py
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from backend.config import DEFAULT_DB_PATH
from backend.service import BackendService
from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskEventCreate, TaskStatus


class TaskCompleteRequest(BaseModel):
    status: TaskStatus
    result_text: str


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    service = BackendService(db_path=db_path)
    app = FastAPI(title="SN Project Backend")

    @app.post("/api/v1/frontend/messages")
    def create_task(request: TaskCreateRequest):
        return service.create_task(request)

    @app.get("/api/v1/client/next-task")
    def next_task(client_id: str):
        return {"task": service.assign_next_task(client_id)}

    @app.post("/api/v1/client/heartbeat")
    def heartbeat(payload: ClientHeartbeat):
        return service.record_heartbeat(payload)

    @app.post("/api/v1/client/tasks/{task_id}/events")
    def add_event(task_id: str, payload: TaskEventCreate):
        service.add_event(payload)
        return {"ok": True, "task_id": task_id}

    @app.post("/api/v1/client/tasks/{task_id}/complete")
    def complete_task(task_id: str, payload: TaskCompleteRequest):
        return service.complete_task(task_id, payload.status, payload.result_text)

    @app.post("/api/v1/frontend/tasks/{task_id}/interrupt")
    def interrupt_task(task_id: str, payload: dict):
        service.add_interrupt(task_id, payload["text"])
        return {"ok": True}

    @app.get("/api/v1/client/tasks/{task_id}/interrupts")
    def consume_interrupts(task_id: str):
        return {"interrupts": service.consume_interrupts(task_id)}

    return app


app = create_app()
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `pytest tests/backend/test_app.py -q`

Expected: `3 passed`

- [ ] **Step 5: Commit the FastAPI layer**

```bash
git add backend/app.py backend/service.py tests/backend/test_app.py
git commit -m "feat: add backend api for bot and client"
```

### Task 4: Turn Telegram into a thin frontend adapter

**Files:**
- Create: `bot/__init__.py`
- Create: `bot/backend_api.py`
- Create: `bot/app.py`
- Test: `tests/bot/test_backend_api.py`

- [ ] **Step 1: Write the failing bot adapter tests**

```python
# tests/bot/test_backend_api.py
from httpx import Response

from bot.backend_api import BackendApi


class DummyClient:
    def __init__(self):
        self.calls = []

    def post(self, url, json):
        self.calls.append((url, json))
        return Response(200, json={"id": "task-1", "status": "pending", "chat_id": json["chat_id"], "text": json["text"], "result_text": ""})


def test_submit_message_posts_to_backend():
    api = BackendApi(base_url="https://example.test", client=DummyClient())
    record = api.submit_message(chat_id=1001, text="Open calculator")
    assert record.id == "task-1"
    assert record.status.value == "pending"
```

- [ ] **Step 2: Run the bot adapter tests to verify they fail**

Run: `pytest tests/bot/test_backend_api.py -q`

Expected: import failure for `bot.backend_api`

- [ ] **Step 3: Implement the backend adapter and Telegram entrypoint**

```python
# bot/backend_api.py
import httpx

from shared.schemas import TaskRecord


class BackendApi:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)

    def submit_message(self, chat_id: int, text: str) -> TaskRecord:
        response = self.client.post(
            f"{self.base_url}/api/v1/frontend/messages",
            json={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()
        return TaskRecord.model_validate(response.json())
```

```python
# bot/app.py
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from bot.backend_api import BackendApi


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is connected to the backend and ready.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api = BackendApi(BACKEND_URL)
    task = api.submit_message(chat_id=update.effective_chat.id, text=update.message.text)
    await update.message.reply_text(f"Task accepted: {task.id} ({task.status.value})")


def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.run_polling()


if __name__ == "__main__":
    main()
```

```python
# bot/__init__.py
from .backend_api import BackendApi
```

- [ ] **Step 4: Run the bot adapter tests to verify they pass**

Run: `pytest tests/bot/test_backend_api.py -q`

Expected: `1 passed`

- [ ] **Step 5: Commit the Telegram frontend adapter**

```bash
git add bot/__init__.py bot/backend_api.py bot/app.py tests/bot/test_backend_api.py
git commit -m "feat: add telegram frontend adapter"
```

### Task 5: Build the client polling and backend transport layer

**Files:**
- Create: `client/__init__.py`
- Create: `client/backend_api.py`
- Create: `client/polling.py`
- Create: `client/app.py`
- Test: `tests/client/test_backend_api.py`
- Test: `tests/client/test_polling.py`

- [ ] **Step 1: Write the failing client transport tests**

```python
# tests/client/test_backend_api.py
from httpx import Response

from client.backend_api import ClientBackendApi


class DummyHttpClient:
    def __init__(self):
        self.last_request = None

    def get(self, url, params=None):
        self.last_request = ("GET", url, params)
        return Response(200, json={"task": {"id": "task-1", "chat_id": 1001, "text": "Take screenshot", "status": "running", "result_text": ""}})

    def post(self, url, json):
        self.last_request = ("POST", url, json)
        return Response(200, json={"ok": True})


def test_poll_next_task_returns_task_record():
    api = ClientBackendApi(base_url="https://example.test", client=DummyHttpClient())
    task = api.poll_next_task(client_id="desktop-main")
    assert task is not None
    assert task.id == "task-1"
```

```python
# tests/client/test_polling.py
from shared.schemas import TaskRecord, TaskStatus
from client.polling import run_once


class DummyBackendApi:
    def __init__(self):
        self.completed = None

    def heartbeat(self, client_id: str, is_busy: bool, current_task_id=None):
        return None

    def poll_next_task(self, client_id: str):
        return TaskRecord(id="task-1", chat_id=1001, text="Take screenshot", status=TaskStatus.RUNNING)

    def send_event(self, task_id: str, event_type: str, message: str, image_base64=None):
        return None

    def consume_interrupts(self, task_id: str):
        return []

    def complete_task(self, task_id: str, status: str, result_text: str):
        self.completed = (task_id, status, result_text)


def test_run_once_completes_task_with_executor_result():
    api = DummyBackendApi()

    def executor(task, interrupt_fetcher, event_sender):
        event_sender("text", "Started")
        return "done", "Task finished"

    run_once(api=api, client_id="desktop-main", executor=executor)
    assert api.completed == ("task-1", "done", "Task finished")
```

- [ ] **Step 2: Run the client transport tests to verify they fail**

Run: `pytest tests/client/test_backend_api.py tests/client/test_polling.py -q`

Expected: import failure for `client.backend_api` and `client.polling`

- [ ] **Step 3: Implement the client backend API and single-iteration polling loop**

```python
# client/backend_api.py
import httpx

from shared.schemas import TaskRecord


class ClientBackendApi:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30.0)

    def heartbeat(self, client_id: str, is_busy: bool, current_task_id=None):
        self.client.post(
            f"{self.base_url}/api/v1/client/heartbeat",
            json={"client_id": client_id, "is_busy": is_busy, "current_task_id": current_task_id},
        ).raise_for_status()

    def poll_next_task(self, client_id: str) -> TaskRecord | None:
        response = self.client.get(f"{self.base_url}/api/v1/client/next-task", params={"client_id": client_id})
        response.raise_for_status()
        payload = response.json()["task"]
        return None if payload is None else TaskRecord.model_validate(payload)

    def send_event(self, task_id: str, event_type: str, message: str, image_base64=None):
        response = self.client.post(
            f"{self.base_url}/api/v1/client/tasks/{task_id}/events",
            json={"task_id": task_id, "event_type": event_type, "message": message, "image_base64": image_base64},
        )
        response.raise_for_status()

    def consume_interrupts(self, task_id: str) -> list[str]:
        response = self.client.get(f"{self.base_url}/api/v1/client/tasks/{task_id}/interrupts")
        response.raise_for_status()
        return response.json()["interrupts"]

    def complete_task(self, task_id: str, status: str, result_text: str):
        response = self.client.post(
            f"{self.base_url}/api/v1/client/tasks/{task_id}/complete",
            json={"status": status, "result_text": result_text},
        )
        response.raise_for_status()
```

```python
# client/polling.py
from collections.abc import Callable


def run_once(api, client_id: str, executor: Callable):
    api.heartbeat(client_id=client_id, is_busy=False)
    task = api.poll_next_task(client_id=client_id)
    if task is None:
        return False

    api.heartbeat(client_id=client_id, is_busy=True, current_task_id=task.id)

    def interrupt_fetcher():
        return api.consume_interrupts(task.id)

    def event_sender(event_type: str, message: str, image_base64=None):
        api.send_event(task.id, event_type, message, image_base64=image_base64)

    status, result_text = executor(task, interrupt_fetcher, event_sender)
    api.complete_task(task.id, status, result_text)
    api.heartbeat(client_id=client_id, is_busy=False, current_task_id=None)
    return True
```

```python
# client/app.py
import os
import time

from client.backend_api import ClientBackendApi
from client.polling import run_once


def not_implemented_executor(task, interrupt_fetcher, event_sender):
    event_sender("text", f"Received task: {task.text}")
    return "failed", "Executor not wired yet"


def main() -> None:
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    client_id = os.getenv("CLIENT_ID", "desktop-main")
    api = ClientBackendApi(base_url=backend_url)
    while True:
        worked = run_once(api=api, client_id=client_id, executor=not_implemented_executor)
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
```

```python
# client/__init__.py
from .backend_api import ClientBackendApi
```

- [ ] **Step 4: Run the client transport tests to verify they pass**

Run: `pytest tests/client/test_backend_api.py tests/client/test_polling.py -q`

Expected: `2 passed`

- [ ] **Step 5: Commit the client transport layer**

```bash
git add client/__init__.py client/backend_api.py client/polling.py client/app.py tests/client/test_backend_api.py tests/client/test_polling.py
git commit -m "feat: add polling client transport layer"
```

### Task 6: Migrate the existing agent runtime into `client/agent/`

**Files:**
- Create: `client/agent/__init__.py`
- Create: `client/agent/loop.py`
- Create: `client/agent/memory.py`
- Create: `client/agent/fact_extractor.py`
- Create: `client/agent/tools/__init__.py`
- Create: `client/agent/tools/base.py`
- Create: `client/agent/tools/collection.py`
- Create: `client/agent/tools/computer.py`
- Create: `client/agent/tools/run.py`
- Modify: `client/app.py`
- Test: `tests/integration/test_task_flow.py`

- [ ] **Step 1: Write the failing integration test for executor wiring**

```python
# tests/integration/test_task_flow.py
from shared.schemas import TaskRecord, TaskStatus
from client.app import execute_task


def test_execute_task_uses_event_sender_and_returns_done(monkeypatch):
    events = []

    async def fake_sampling_loop(**kwargs):
        kwargs["output_callback"]({"type": "text", "text": "Agent says hi"})
        return [{"role": "assistant", "content": [{"type": "text", "text": "Finished task"}]}]

    async def fake_extract_facts(**kwargs):
        return {
            "from_user_tasks": [],
            "from_agent_results": [],
            "from_intermediate_steps": [],
            "from_user_interrupts": [],
        }

    monkeypatch.setattr("client.app.load_memory", lambda: {"task_results": [], "facts": {}})
    monkeypatch.setattr("client.app.build_context", lambda memory, text: [{"role": "user", "content": [{"type": "text", "text": text}]}])
    monkeypatch.setattr("client.app.sampling_loop", fake_sampling_loop)
    monkeypatch.setattr("client.app.extract_final_text", lambda messages: "Finished task")
    monkeypatch.setattr("client.app.extract_tool_trace", lambda messages, start_index: [])
    monkeypatch.setattr("client.app.extract_facts", fake_extract_facts)
    monkeypatch.setattr("client.app.merge_facts", lambda memory, facts: memory)
    monkeypatch.setattr("client.app.add_task_result", lambda memory, task, result: memory)
    monkeypatch.setattr("client.app.save_memory", lambda memory: None)

    task = TaskRecord(id="task-1", chat_id=1001, text="Take screenshot", status=TaskStatus.RUNNING)

    status, result = execute_task(
        task=task,
        interrupt_fetcher=lambda: [],
        event_sender=lambda event_type, message, image_base64=None: events.append((event_type, message)),
    )

    assert status == "done"
    assert result == "Finished task"
    assert ("text", "Agent says hi") in events
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `pytest tests/integration/test_task_flow.py -q`

Expected: import failure for `client.app.execute_task`

- [ ] **Step 3: Copy the current runtime into `client/agent/` and wire `execute_task`**

```python
# client/agent/__init__.py
from .fact_extractor import extract_facts
from .loop import sampling_loop
from .memory import (
    add_task_result,
    build_context,
    extract_final_text,
    extract_tool_trace,
    load_memory,
    merge_facts,
    save_memory,
)
```

```python
# client/app.py
import asyncio
import os
import time

from client.agent import (
    add_task_result,
    build_context,
    extract_facts,
    extract_final_text,
    extract_tool_trace,
    load_memory,
    merge_facts,
    sampling_loop,
    save_memory,
)
from client.backend_api import ClientBackendApi
from client.polling import run_once


def execute_task(task, interrupt_fetcher, event_sender):
    memory = load_memory()
    messages = build_context(memory, task.text)
    start_index = len(messages)
    collected_interrupts = []

    def output_callback(block):
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
            event_sender("text", block["text"])

    def consume_interrupt_text():
        items = interrupt_fetcher()
        if not items:
            return None
        collected_interrupts.extend(items)
        return " ".join(items)

    async def _run():
        updated_messages = await sampling_loop(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            messages=messages,
            output_callback=output_callback,
            tool_output_callback=lambda result, tool_id: event_sender("tool_output", result.output or result.error or ""),
            api_response_callback=lambda request, response, error: None,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            max_tokens=4096,
            only_n_most_recent_images=1,
            interrupt_callback=consume_interrupt_text,
        )
        result_text = extract_final_text(updated_messages)
        tool_trace = extract_tool_trace(updated_messages, start_index)
        facts = await extract_facts(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            task=task.text,
            result=result_text,
            intermediate_chain=tool_trace,
            interrupts=collected_interrupts,
        )
        updated_memory = add_task_result(memory, task.text, result_text)
        updated_memory = merge_facts(updated_memory, facts)
        save_memory(updated_memory)
        return "done", result_text

    return asyncio.run(_run())


def main() -> None:
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    client_id = os.getenv("CLIENT_ID", "desktop-main")
    api = ClientBackendApi(base_url=backend_url)
    while True:
        worked = run_once(api=api, client_id=client_id, executor=execute_task)
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
```

```text
# File migration instruction
Copy these files with import-path updates only:
- src/loop.py -> client/agent/loop.py
- src/memory.py -> client/agent/memory.py
- src/fact_extractor.py -> client/agent/fact_extractor.py
- src/tools/__init__.py -> client/agent/tools/__init__.py
- src/tools/base.py -> client/agent/tools/base.py
- src/tools/collection.py -> client/agent/tools/collection.py
- src/tools/computer.py -> client/agent/tools/computer.py
- src/tools/run.py -> client/agent/tools/run.py

Replace all `from src...` imports with `from client.agent...`.
```

- [ ] **Step 4: Run the integration test to verify the executor wiring passes**

Run: `pytest tests/integration/test_task_flow.py -q`

Expected: `1 passed`

- [ ] **Step 5: Commit the migrated client runtime**

```bash
git add client/agent/__init__.py client/agent/loop.py client/agent/memory.py client/agent/fact_extractor.py client/agent/tools/__init__.py client/agent/tools/base.py client/agent/tools/collection.py client/agent/tools/computer.py client/agent/tools/run.py client/app.py tests/integration/test_task_flow.py
git commit -m "feat: migrate agent runtime into client package"
```

### Task 7: Add interrupts, screenshots, watchdog, and backend-to-bot status delivery

**Files:**
- Modify: `backend/storage.py`
- Modify: `backend/service.py`
- Modify: `backend/app.py`
- Modify: `bot/backend_api.py`
- Modify: `bot/app.py`
- Create: `client/watchdog.py`
- Modify: `client/app.py`
- Modify: `watchdog.py`

- [ ] **Step 1: Extend the backend API tests for event retrieval and interrupt delivery**

```python
# tests/backend/test_app.py
def test_interrupts_can_be_consumed_by_client(tmp_path: Path):
    client = build_client(tmp_path)
    created = client.post("/api/v1/frontend/messages", json={"chat_id": 1001, "text": "Use browser"}).json()
    assigned = client.get("/api/v1/client/next-task", params={"client_id": "desktop-main"}).json()["task"]
    client.post(f"/api/v1/frontend/tasks/{assigned['id']}/interrupt", json={"text": "Stop and use Chrome"})
    response = client.get(f"/api/v1/client/tasks/{assigned['id']}/interrupts")
    assert response.status_code == 200
    assert response.json()["interrupts"] == ["Stop and use Chrome"]


def test_frontend_can_read_task_events(tmp_path: Path):
    client = build_client(tmp_path)
    client.post("/api/v1/frontend/messages", json={"chat_id": 1001, "text": "Use browser"})
    assigned = client.get("/api/v1/client/next-task", params={"client_id": "desktop-main"}).json()["task"]
    client.post(
        f"/api/v1/client/tasks/{assigned['id']}/events",
        json={"task_id": assigned["id"], "event_type": "text", "message": "Step 1"},
    )
    response = client.get(f"/api/v1/frontend/tasks/{assigned['id']}/events")
    assert response.status_code == 200
    assert response.json()["events"][0]["message"] == "Step 1"
```

Run: `pytest tests/backend/test_app.py::test_frontend_can_read_task_events tests/backend/test_app.py::test_interrupts_can_be_consumed_by_client -q`

Expected: one or both tests fail because the frontend event-reading endpoints are not implemented yet.

- [ ] **Step 2: Add backend queries for task events and last known task state**

```python
# backend/service.py (append these methods)
    def list_task_events(self, task_id: str) -> list[dict]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT event_type, message, image_base64 FROM task_events WHERE task_id = ? ORDER BY id",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: str) -> TaskRecord:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT id, chat_id, text, status, result_text FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return TaskRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            text=row["text"],
            status=TaskStatus(row["status"]),
            result_text=row["result_text"],
        )
```

```python
# backend/app.py (append these endpoints)
    @app.get("/api/v1/frontend/tasks/{task_id}")
    def get_task(task_id: str):
        return service.get_task(task_id)

    @app.get("/api/v1/frontend/tasks/{task_id}/events")
    def list_events(task_id: str):
        return {"events": service.list_task_events(task_id)}
```

- [ ] **Step 3: Teach the bot to poll task state and emit progress to Telegram**

```python
# bot/backend_api.py (append methods)
    def get_task(self, task_id: str) -> TaskRecord:
        response = self.client.get(f"{self.base_url}/api/v1/frontend/tasks/{task_id}")
        response.raise_for_status()
        return TaskRecord.model_validate(response.json())

    def list_events(self, task_id: str) -> list[dict]:
        response = self.client.get(f"{self.base_url}/api/v1/frontend/tasks/{task_id}/events")
        response.raise_for_status()
        return response.json()["events"]

    def interrupt_task(self, task_id: str, text: str) -> None:
        response = self.client.post(f"{self.base_url}/api/v1/frontend/tasks/{task_id}/interrupt", json={"text": text})
        response.raise_for_status()
```

```python
# bot/app.py (replace message handler shape)
import asyncio

ACTIVE_TASKS: dict[int, str] = {}
LAST_EVENT_INDEX: dict[int, int] = {}


async def stream_task_updates(api: BackendApi, chat_id: int, task_id: str, context: ContextTypes.DEFAULT_TYPE):
    while True:
        task = api.get_task(task_id)
        events = api.list_events(task_id)
        start_index = LAST_EVENT_INDEX.get(chat_id, 0)
        for event in events[start_index:]:
            if event["event_type"] == "screenshot" and event.get("image_base64"):
                await context.bot.send_message(chat_id=chat_id, text="Screenshot event received.")
            else:
                await context.bot.send_message(chat_id=chat_id, text=event["message"])
        LAST_EVENT_INDEX[chat_id] = len(events)
        if task.status.value in {"done", "failed"}:
            await context.bot.send_message(chat_id=chat_id, text=f"Task finished: {task.result_text}")
            ACTIVE_TASKS.pop(chat_id, None)
            LAST_EVENT_INDEX.pop(chat_id, None)
            return
        await asyncio.sleep(2)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api = BackendApi(BACKEND_URL)
    chat_id = update.effective_chat.id
    text = update.message.text

    if chat_id in ACTIVE_TASKS:
        api.interrupt_task(ACTIVE_TASKS[chat_id], text)
        await update.message.reply_text("Interrupt sent to the active task.")
        return

    task = api.submit_message(chat_id=chat_id, text=text)
    ACTIVE_TASKS[chat_id] = task.id
    await update.message.reply_text(f"Task accepted: {task.id}")
    context.application.create_task(stream_task_updates(api, chat_id, task.id, context))
```

```python
# client/watchdog.py
import subprocess
import time


def main() -> None:
    while True:
        process = subprocess.Popen(["python", "-m", "client.app"])
        exit_code = process.wait()
        print(f"Client exited with code {exit_code}. Restarting in 5 seconds.")
        time.sleep(5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify backend, bot, and watchdog behavior**

Run: `pytest tests/backend/test_app.py -q`

Expected: all backend API tests pass, including interrupt consumption.

Run: `python -m client.watchdog`

Expected: the watchdog starts `client.app` and restarts it after a forced exit.

- [ ] **Step 5: Commit progress delivery and resilience**

```bash
git add backend/app.py backend/service.py bot/backend_api.py bot/app.py client/watchdog.py watchdog.py
git commit -m "feat: add interrupt delivery and client watchdog"
```

### Task 8: Clean the repository, rewrite docs, and remove the monolith entrypoints

**Files:**
- Modify: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/deployment.md`
- Delete: `CHANGELOG.md`
- Delete: `RELEASE_NOTES_v0.4.0.txt`
- Delete: `RELEASE_NOTES_v0.4.1.txt`
- Delete: `RELEASE_NOTES_v0.4.2.txt`
- Delete: `UPGRADE_v0.4.0.md`
- Delete: `UPGRADE_v0.4.1.md`
- Delete: `UPGRADE_v0.4.2.md`
- Delete: `run_agent.bat`
- Delete: `run_console.bat`
- Delete: `src/telegram_bot.py`
- Delete: `src/main.py`

- [ ] **Step 1: Extend the integration smoke test for the final public structure**

```python
# tests/integration/test_task_flow.py
from pathlib import Path


def test_new_project_structure_exists():
    assert Path("backend/app.py").exists()
    assert Path("bot/app.py").exists()
    assert Path("client/app.py").exists()
    assert Path("shared/schemas.py").exists()
```

Run: `pytest tests/integration/test_task_flow.py::test_new_project_structure_exists -q`

Expected: fail until the new tree exists completely.

- [ ] **Step 2: Rewrite the README around the new distributed architecture**

```markdown
# SN Project

Study project that demonstrates explicit separation between:

- Telegram frontend
- FastAPI cloud backend
- local Windows execution client

## Components

- `bot/`: user-facing Telegram interface
- `backend/`: API, queue/state, interrupts, events, stats
- `client/`: local agent runtime and Windows computer control
- `shared/`: common Pydantic schemas

## Demo Flow

1. User sends a task in Telegram.
2. Backend stores the task.
3. Client polls the backend and executes the task locally.
4. Backend stores progress and final result.
5. Bot shows updates back to the user.
```

```markdown
# docs/architecture.md

## Overview

This project is split into three applications:

- Telegram bot frontend
- FastAPI backend in the cloud
- local Windows client with computer-control tools

## Responsibility Boundaries

- `bot/` accepts user input and renders progress.
- `backend/` stores tasks, interrupts, task events, memory snapshots, and client status.
- `client/` polls for work and performs actions on the Windows desktop.

## Task Lifecycle

1. User sends a task to Telegram.
2. Bot forwards the message to the backend.
3. Backend creates a pending task.
4. Client polls and starts execution.
5. Client sends progress events and screenshots back to the backend.
6. Bot reads backend events and shows them to the user.
7. Client completes the task and backend stores the final result.
```

```markdown
# docs/deployment.md

## Cloud Backend

Run the FastAPI backend on a small cloud host with:

- Python 3.10+
- environment variables for host, port, and storage path
- a public base URL reachable by the Telegram bot

Command:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## Telegram Bot

Run the bot as a separate process with:

- `TELEGRAM_BOT_TOKEN`
- `BACKEND_URL`

Command:

```bash
python -m bot.app
```

## Local Windows Client

Run the client on the user's PC with:

- `BACKEND_URL`
- `CLIENT_ID`
- `ANTHROPIC_API_KEY`

Command:

```bash
python -m client.watchdog
```
```

- [ ] **Step 3: Delete old monolithic entrypoints and stale historical artifacts**

```text
Delete these files and folders after the new code paths work:
- CHANGELOG.md
- RELEASE_NOTES_v0.4.0.txt
- RELEASE_NOTES_v0.4.1.txt
- RELEASE_NOTES_v0.4.2.txt
- UPGRADE_v0.4.0.md
- UPGRADE_v0.4.1.md
- UPGRADE_v0.4.2.md
- run_agent.bat
- run_console.bat
- src/telegram_bot.py
- src/main.py
- docs/research/
- docs/big_problems_using_llm_in_agentic_mode/
```

- [ ] **Step 4: Run the full test suite and verify the cleaned repo layout**

Run: `pytest tests -q`

Expected: all shared, backend, bot, client, and integration tests pass.

Run: `git status --short`

Expected: only intentional cleanup changes remain.

- [ ] **Step 5: Commit the cleaned study-project layout**

```bash
git add README.md docs/architecture.md docs/deployment.md backend bot client shared tests
git rm CHANGELOG.md RELEASE_NOTES_v0.4.0.txt RELEASE_NOTES_v0.4.1.txt RELEASE_NOTES_v0.4.2.txt UPGRADE_v0.4.0.md UPGRADE_v0.4.1.md UPGRADE_v0.4.2.md run_agent.bat run_console.bat src/telegram_bot.py src/main.py
git commit -m "refactor: reshape repo into distributed study project"
```

## Spec Coverage Check

- Frontend/backend/client separation: covered by Tasks 1, 3, 4, 5, and 8.
- Cloud backend as source of truth: covered by Tasks 2, 3, and 7.
- Local Windows client with computer control preserved: covered by Task 6 and Task 7.
- Polling communication model: covered by Tasks 3 and 5.
- Interrupts, stats, memory, and watchdog retained: covered by Tasks 6 and 7.
- Repo cleanup for study presentation: covered by Task 8.

## Type Consistency Check

- `TaskRecord` is the cross-component task payload in bot, backend, and client.
- `TaskStatus` values remain `pending`, `running`, `done`, and `failed` across service and API layers.
- `TaskEventCreate` is the only payload used to push client-side progress to the backend.
- `ClientHeartbeat` is the only payload used for client presence updates.

## Execution Notes

- Do not delete `src/loop.py`, `src/memory.py`, `src/fact_extractor.py`, or `src/tools/` until `client/agent/` is running and tested.
- Do not remove the old `watchdog.py` until `client/watchdog.py` is functioning and the README points to the new entrypoints.
- Keep commits small and aligned with the task boundaries above.
