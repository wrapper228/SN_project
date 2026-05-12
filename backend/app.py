from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backend.config import DEFAULT_DB_PATH
from backend.service import BackendService
from shared.schemas import ClientHeartbeat, TaskCreateRequest, TaskEventCreate, TaskStatus


class TaskEventPayload(BaseModel):
    event_type: str = Field(min_length=1)
    message: str = ""
    image_base64: str | None = None


class TaskCompleteRequest(BaseModel):
    status: TaskStatus
    result_text: str = ""


class InterruptRequest(BaseModel):
    text: str = Field(min_length=1)


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    service = BackendService(db_path=db_path)
    app = FastAPI(title="SN Project Backend")

    @app.post("/api/v1/frontend/messages")
    def create_task(request: TaskCreateRequest):
        return service.create_task(request)

    @app.get("/api/v1/client/next-task")
    def next_task(client_id: str):
        return service.assign_next_task(client_id)

    @app.post("/api/v1/client/heartbeat")
    def heartbeat(payload: ClientHeartbeat):
        return service.record_heartbeat(payload)

    @app.post("/api/v1/client/tasks/{task_id}/events")
    def add_event(task_id: str, payload: TaskEventPayload):
        service.add_event(
            TaskEventCreate(
                task_id=task_id,
                event_type=payload.event_type,
                message=payload.message,
                image_base64=payload.image_base64,
            )
        )
        return {"ok": True}

    @app.post("/api/v1/client/tasks/{task_id}/complete")
    def complete_task(task_id: str, payload: TaskCompleteRequest):
        return service.complete_task(task_id, payload.status, payload.result_text)

    @app.post("/api/v1/frontend/tasks/{task_id}/interrupt")
    def interrupt_task(task_id: str, payload: InterruptRequest):
        service.add_interrupt(task_id, payload.text)
        return {"ok": True}

    @app.get("/api/v1/client/tasks/{task_id}/interrupts")
    def consume_interrupts(task_id: str):
        return {"interrupts": service.consume_interrupts(task_id)}

    return app


app = create_app()
