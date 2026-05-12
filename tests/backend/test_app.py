import sqlite3

from fastapi.testclient import TestClient

from backend.app import create_app


def test_post_frontend_messages_creates_task_and_returns_pending_status(tmp_path):
    db_path = tmp_path / "backend.db"
    client = TestClient(create_app(db_path=db_path))

    response = client.post(
        "/api/v1/frontend/messages",
        json={"chat_id": 42, "text": "Write a summary"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "chat_id": 42,
        "text": "Write a summary",
        "status": "pending",
        "result_text": "",
    }


def test_get_client_next_task_assigns_and_returns_running_task(tmp_path):
    db_path = tmp_path / "backend.db"
    client = TestClient(create_app(db_path=db_path))
    created = client.post(
        "/api/v1/frontend/messages",
        json={"chat_id": 7, "text": "First task"},
    ).json()

    response = client.get("/api/v1/client/next-task", params={"client_id": "worker-1"})

    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "chat_id": 7,
        "text": "First task",
        "status": "running",
        "result_text": "",
    }


def test_post_task_event_stores_event_and_returns_ok(tmp_path):
    db_path = tmp_path / "backend.db"
    client = TestClient(create_app(db_path=db_path))
    created = client.post(
        "/api/v1/frontend/messages",
        json={"chat_id": 9, "text": "Collect notes"},
    ).json()

    response = client.post(
        f"/api/v1/client/tasks/{created['id']}/events",
        json={
            "event_type": "message",
            "message": "Started collecting notes",
            "image_base64": None,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT task_id, event_type, message, image_base64
            FROM task_events
            WHERE task_id = ?
            """,
            (created["id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        created["id"],
        "message",
        "Started collecting notes",
        None,
    )


def test_post_task_complete_completes_task_and_returns_updated_record(tmp_path):
    db_path = tmp_path / "backend.db"
    client = TestClient(create_app(db_path=db_path))
    created = client.post(
        "/api/v1/frontend/messages",
        json={"chat_id": 13, "text": "Prepare result"},
    ).json()
    client.get("/api/v1/client/next-task", params={"client_id": "worker-1"})

    response = client.post(
        f"/api/v1/client/tasks/{created['id']}/complete",
        json={"status": "done", "result_text": "Finished successfully"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "chat_id": 13,
        "text": "Prepare result",
        "status": "done",
        "result_text": "Finished successfully",
    }
