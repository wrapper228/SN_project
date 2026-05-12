from enum import Enum

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
    id: str = Field(min_length=1)
    chat_id: int
    text: str
    status: TaskStatus = TaskStatus.PENDING
    result_text: str = ""


class TaskEventCreate(BaseModel):
    task_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    message: str = ""
    image_base64: str | None = None


class InterruptRecord(BaseModel):
    task_id: str = Field(min_length=1)
    text: str
    consumed: bool = False


class ClientHeartbeat(BaseModel):
    client_id: str = Field(min_length=1)
    is_busy: bool
    current_task_id: str | None = None
