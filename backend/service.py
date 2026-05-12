from __future__ import annotations

from pathlib import Path

from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskRecord

from backend.config import DEFAULT_DB_PATH
from backend.storage import SQLiteStorage


class BackendService:
    def __init__(self, db_path: Path | None = None):
        self._storage = SQLiteStorage(db_path or DEFAULT_DB_PATH)

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        return self._storage.create_task(request)

    def assign_next_task(self, client_id: str) -> TaskRecord | None:
        return self._storage.assign_next_task(client_id)

    def add_interrupt(self, task_id: str, text: str) -> None:
        self._storage.add_interrupt(task_id, text)

    def consume_interrupts(self, task_id: str) -> list[str]:
        return self._storage.consume_interrupts(task_id)

    def record_heartbeat(self, heartbeat: ClientHeartbeat) -> ClientHeartbeat:
        return self._storage.record_heartbeat(heartbeat)
