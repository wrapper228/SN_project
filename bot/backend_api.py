from __future__ import annotations

import httpx

from shared.schemas import TaskRecord


class BackendApi:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=20.0)

    def submit_message(self, chat_id: int, text: str) -> TaskRecord:
        response = self.client.post(
            f"{self.base_url}/api/v1/frontend/messages",
            json={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()
        return TaskRecord.model_validate(response.json())

    def interrupt_task(self, task_id: str, text: str) -> bool:
        response = self.client.post(
            f"{self.base_url}/api/v1/frontend/tasks/{task_id}/interrupt",
            json={"text": text},
        )
        response.raise_for_status()
        return bool(response.json()["ok"])

    def get_task(self, task_id: str) -> TaskRecord:
        response = self.client.get(f"{self.base_url}/api/v1/frontend/tasks/{task_id}")
        response.raise_for_status()
        return TaskRecord.model_validate(response.json())

    def list_events(self, task_id: str) -> list[dict]:
        response = self.client.get(
            f"{self.base_url}/api/v1/frontend/tasks/{task_id}/events"
        )
        response.raise_for_status()
        return response.json()["events"]
