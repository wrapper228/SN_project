from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskRecord, TaskStatus


class SQLiteStorage:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        task = TaskRecord(id=str(uuid4()), chat_id=request.chat_id, text=request.text)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (id, chat_id, text, status, result_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.chat_id,
                    task.text,
                    task.status.value,
                    task.result_text,
                ),
            )
        return task

    def assign_next_task(self, client_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, chat_id, text, status, result_text
                FROM tasks
                WHERE status = ?
                ORDER BY rowid
                LIMIT 1
                """,
                (TaskStatus.PENDING.value,),
            ).fetchone()
            if row is None:
                return None

            connection.execute(
                "UPDATE tasks SET status = ?, assigned_client_id = ? WHERE id = ?",
                (TaskStatus.RUNNING.value, client_id, row["id"]),
            )
            connection.execute(
                """
                INSERT INTO client_status (client_id, is_busy, current_task_id)
                VALUES (?, 1, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    is_busy = excluded.is_busy,
                    current_task_id = excluded.current_task_id
                """,
                (client_id, row["id"]),
            )
            return TaskRecord(
                id=row["id"],
                chat_id=row["chat_id"],
                text=row["text"],
                status=TaskStatus.RUNNING,
                result_text=row["result_text"],
            )

    def add_interrupt(self, task_id: str, text: str) -> None:
        if not self._task_exists(task_id):
            raise ValueError(f"Unknown task_id: {task_id}")

        with self._connect() as connection:
            connection.execute(
                "INSERT INTO interrupts (task_id, text, consumed) VALUES (?, ?, 0)",
                (task_id, text),
            )

    def consume_interrupts(self, task_id: str) -> list[str]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT id, text
                FROM interrupts
                WHERE task_id = ? AND consumed = 0
                ORDER BY id
                """,
                (task_id,),
            ).fetchall()
            if not rows:
                return []

            connection.executemany(
                "UPDATE interrupts SET consumed = 1 WHERE id = ?",
                [(row["id"],) for row in rows],
            )
            return [row["text"] for row in rows]

    def record_heartbeat(self, heartbeat: ClientHeartbeat) -> ClientHeartbeat:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO client_status (client_id, is_busy, current_task_id)
                VALUES (?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    is_busy = excluded.is_busy,
                    current_task_id = excluded.current_task_id
                """,
                (
                    heartbeat.client_id,
                    int(heartbeat.is_busy),
                    heartbeat.current_task_id,
                ),
            )
        return heartbeat

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_client_id TEXT,
                    result_text TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    image_base64 TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS interrupts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS client_status (
                    client_id TEXT PRIMARY KEY,
                    is_busy INTEGER NOT NULL,
                    current_task_id TEXT,
                    FOREIGN KEY (current_task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );
                """
            )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "assigned_client_id" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN assigned_client_id TEXT"
                )
            self._migrate_legacy_task_linked_tables(connection)

    def _task_exists(self, task_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return row is not None

    def _migrate_legacy_task_linked_tables(self, connection: sqlite3.Connection) -> None:
        if self._table_has_foreign_keys(connection, "task_events"):
            task_events_ready = True
        else:
            self._rebuild_table(
                connection=connection,
                table_name="task_events",
                create_sql="""
                CREATE TABLE task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    image_base64 TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
                """,
                copy_sql="""
                INSERT INTO task_events (id, task_id, event_type, message, image_base64)
                SELECT legacy.id, legacy.task_id, legacy.event_type, legacy.message, legacy.image_base64
                FROM task_events_legacy AS legacy
                INNER JOIN tasks ON tasks.id = legacy.task_id
                """,
            )
            task_events_ready = True

        if self._table_has_foreign_keys(connection, "interrupts"):
            interrupts_ready = True
        else:
            self._rebuild_table(
                connection=connection,
                table_name="interrupts",
                create_sql="""
                CREATE TABLE interrupts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
                """,
                copy_sql="""
                INSERT INTO interrupts (id, task_id, text, consumed)
                SELECT legacy.id, legacy.task_id, legacy.text, legacy.consumed
                FROM interrupts_legacy AS legacy
                INNER JOIN tasks ON tasks.id = legacy.task_id
                """,
            )
            interrupts_ready = True

        if self._table_has_foreign_keys(connection, "client_status"):
            client_status_ready = True
        else:
            self._rebuild_table(
                connection=connection,
                table_name="client_status",
                create_sql="""
                CREATE TABLE client_status (
                    client_id TEXT PRIMARY KEY,
                    is_busy INTEGER NOT NULL,
                    current_task_id TEXT,
                    FOREIGN KEY (current_task_id) REFERENCES tasks(id) ON DELETE SET NULL
                )
                """,
                copy_sql="""
                INSERT INTO client_status (client_id, is_busy, current_task_id)
                SELECT
                    legacy.client_id,
                    legacy.is_busy,
                    CASE
                        WHEN legacy.current_task_id IS NULL THEN NULL
                        WHEN EXISTS (SELECT 1 FROM tasks WHERE id = legacy.current_task_id)
                            THEN legacy.current_task_id
                        ELSE NULL
                    END
                FROM client_status_legacy AS legacy
                """,
            )
            client_status_ready = True

        if task_events_ready or interrupts_ready or client_status_ready:
            connection.execute("PRAGMA foreign_keys = ON")

    def _table_has_foreign_keys(
        self, connection: sqlite3.Connection, table_name: str
    ) -> bool:
        rows = connection.execute(
            f"PRAGMA foreign_key_list({table_name})"
        ).fetchall()
        return bool(rows)

    def _rebuild_table(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        create_sql: str,
        copy_sql: str,
    ) -> None:
        legacy_table_name = f"{table_name}_legacy"
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(f"ALTER TABLE {table_name} RENAME TO {legacy_table_name}")
        connection.execute(create_sql)
        connection.execute(copy_sql)
        connection.execute(f"DROP TABLE {legacy_table_name}")
