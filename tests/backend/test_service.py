import sqlite3

import pytest

from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskStatus

from backend.service import BackendService
from backend.storage import SQLiteStorage


def test_create_task_persists_a_pending_task(tmp_path):
    db_path = tmp_path / "backend.db"
    service = BackendService(db_path=db_path)

    created = service.create_task(TaskCreateRequest(chat_id=42, text="Write summary"))

    assert created.chat_id == 42
    assert created.text == "Write summary"
    assert created.status is TaskStatus.PENDING

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT id, chat_id, text, status, result_text FROM tasks WHERE id = ?",
            (created.id,),
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        created.id,
        42,
        "Write summary",
        TaskStatus.PENDING.value,
        "",
    )


def test_assign_next_task_marks_next_task_as_running(tmp_path):
    db_path = tmp_path / "backend.db"
    service = BackendService(db_path=db_path)
    first = service.create_task(TaskCreateRequest(chat_id=1, text="First"))
    service.create_task(TaskCreateRequest(chat_id=2, text="Second"))

    assigned = service.assign_next_task(client_id="worker-1")

    assert assigned is not None
    assert assigned.id == first.id
    assert assigned.status is TaskStatus.RUNNING

    connection = sqlite3.connect(db_path)
    try:
        task_rows = connection.execute(
            "SELECT id, status, assigned_client_id FROM tasks ORDER BY rowid"
        ).fetchall()
        client_row = connection.execute(
            "SELECT client_id, is_busy, current_task_id FROM client_status WHERE client_id = ?",
            ("worker-1",),
        ).fetchone()
    finally:
        connection.close()

    assert task_rows == [
        (first.id, TaskStatus.RUNNING.value, "worker-1"),
        (task_rows[1][0], TaskStatus.PENDING.value, None),
    ]
    assert client_row == ("worker-1", 1, first.id)


def test_add_interrupt_and_consume_interrupts_returns_pending_interrupts_once(tmp_path):
    service = BackendService(db_path=tmp_path / "backend.db")
    task = service.create_task(TaskCreateRequest(chat_id=5, text="Long job"))

    service.add_interrupt(task.id, "Pause after current step")
    service.add_interrupt(task.id, "Switch to concise mode")

    first_batch = service.consume_interrupts(task.id)
    second_batch = service.consume_interrupts(task.id)

    assert first_batch == ["Pause after current step", "Switch to concise mode"]
    assert second_batch == []


def test_add_interrupt_rejects_unknown_task_ids(tmp_path):
    service = BackendService(db_path=tmp_path / "backend.db")

    with pytest.raises(ValueError, match="Unknown task_id"):
        service.add_interrupt("missing-task", "Pause now")


def test_record_heartbeat_updates_client_presence(tmp_path):
    db_path = tmp_path / "backend.db"
    service = BackendService(db_path=db_path)
    task = service.create_task(TaskCreateRequest(chat_id=9, text="Heartbeat target"))
    first = ClientHeartbeat(client_id="worker-1", is_busy=False, current_task_id=None)
    second = ClientHeartbeat(client_id="worker-1", is_busy=True, current_task_id=task.id)

    recorded_first = service.record_heartbeat(first)
    recorded_second = service.record_heartbeat(second)

    assert recorded_first == first
    assert recorded_second == second

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT client_id, is_busy, current_task_id FROM client_status WHERE client_id = ?",
            ("worker-1",),
        ).fetchone()
    finally:
        connection.close()

    assert row == ("worker-1", 1, task.id)


def test_storage_migrates_legacy_task_linked_tables_to_enforce_foreign_keys(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                result_text TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                image_base64 TEXT
            );

            CREATE TABLE interrupts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                text TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE client_status (
                client_id TEXT PRIMARY KEY,
                is_busy INTEGER NOT NULL,
                current_task_id TEXT
            );
            """
        )
    finally:
        connection.close()

    SQLiteStorage(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        interrupt_fks = connection.execute("PRAGMA foreign_key_list(interrupts)").fetchall()
        event_fks = connection.execute("PRAGMA foreign_key_list(task_events)").fetchall()
        client_fks = connection.execute("PRAGMA foreign_key_list(client_status)").fetchall()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO interrupts (task_id, text, consumed) VALUES (?, ?, 0)",
                ("missing-task", "orphan interrupt"),
            )
    finally:
        connection.close()

    assert interrupt_fks
    assert event_fks
    assert client_fks
