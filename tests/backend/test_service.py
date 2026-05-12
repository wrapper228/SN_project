import sqlite3

from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskStatus

from backend.service import BackendService


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
        statuses = connection.execute(
            "SELECT id, status FROM tasks ORDER BY rowid"
        ).fetchall()
    finally:
        connection.close()

    assert statuses == [
        (first.id, TaskStatus.RUNNING.value),
        (statuses[1][0], TaskStatus.PENDING.value),
    ]


def test_add_interrupt_and_consume_interrupts_returns_pending_interrupts_once(tmp_path):
    service = BackendService(db_path=tmp_path / "backend.db")
    task = service.create_task(TaskCreateRequest(chat_id=5, text="Long job"))

    service.add_interrupt(task.id, "Pause after current step")
    service.add_interrupt(task.id, "Switch to concise mode")

    first_batch = service.consume_interrupts(task.id)
    second_batch = service.consume_interrupts(task.id)

    assert first_batch == ["Pause after current step", "Switch to concise mode"]
    assert second_batch == []


def test_record_heartbeat_updates_client_presence(tmp_path):
    db_path = tmp_path / "backend.db"
    service = BackendService(db_path=db_path)
    first = ClientHeartbeat(client_id="worker-1", is_busy=False, current_task_id=None)
    second = ClientHeartbeat(client_id="worker-1", is_busy=True, current_task_id="task-123")

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

    assert row == ("worker-1", 1, "task-123")
