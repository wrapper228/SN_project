from __future__ import annotations

import httpx

from shared.schemas import TaskRecord


class ClientBackendApi:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30.0)

    def heartbeat(
        self, client_id: str, is_busy: bool, current_task_id: str | None = None
    ) -> None:
        response = self.client.post(
            f"{self.base_url}/api/v1/client/heartbeat",
            json={
                "client_id": client_id,
                "is_busy": is_busy,
                "current_task_id": current_task_id,
            },
        )
        response.raise_for_status()

    def poll_next_task(self, client_id: str) -> TaskRecord | None:
        response = self.client.get(
            f"{self.base_url}/api/v1/client/next-task",
            params={"client_id": client_id},
        )
        response.raise_for_status()
        payload = response.json()
        if payload is None:
            return None
        return TaskRecord.model_validate(payload)

    def send_event(
        self,
        task_id: str,
        event_type: str,
        message: str = "",
        image_base64: str | None = None,
    ) -> None:
        response = self.client.post(
            f"{self.base_url}/api/v1/client/tasks/{task_id}/events",
            json={
                "event_type": event_type,
                "message": message,
                "image_base64": image_base64,
            },
        )
        response.raise_for_status()

    def consume_interrupts(self, task_id: str) -> list[str]:
        response = self.client.get(
            f"{self.base_url}/api/v1/client/tasks/{task_id}/interrupts"
        )
        response.raise_for_status()
        return response.json()["interrupts"]

    def complete_task(self, task_id: str, status: str, result_text: str) -> None:
        response = self.client.post(
            f"{self.base_url}/api/v1/client/tasks/{task_id}/complete",
            json={"status": status, "result_text": result_text},
        )
        response.raise_for_status()
