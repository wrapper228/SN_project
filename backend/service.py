from __future__ import annotations

from pathlib import Path

from shared.schemas import (
    ClientHeartbeat,
    TaskCreateRequest,
    TaskEventCreate,
    TaskRecord,
    TaskStatus,
)

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

    def add_event(self, event: TaskEventCreate) -> None:
        with self._storage._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_events (task_id, event_type, message, image_base64)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.task_id,
                    event.event_type,
                    event.message,
                    event.image_base64,
                ),
            )

    def complete_task(
        self, task_id: str, status: TaskStatus, result_text: str
    ) -> TaskRecord:
        with self._storage._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, result_text = ? WHERE id = ?",
                (status.value, result_text, task_id),
            )
            row = connection.execute(
                """
                SELECT id, chat_id, text, status, result_text
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"Unknown task_id: {task_id}")

        return TaskRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            text=row["text"],
            status=TaskStatus(row["status"]),
            result_text=row["result_text"],
        )
