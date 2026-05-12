from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.schemas import (
    ClientHeartbeat,
    InterruptRecord,
    TaskCreateRequest,
    TaskEventCreate,
    TaskRecord,
    TaskStatus,
)


def test_task_create_request_accepts_chat_id_and_text():
    request = TaskCreateRequest(chat_id=123, text="do something")

    assert request.chat_id == 123
    assert request.text == "do something"


def test_task_record_defaults_to_pending():
    record = TaskRecord(id="task-1", chat_id=123, text="do something")

    assert record.status is TaskStatus.PENDING
    assert record.result_text == ""


def test_task_event_create_can_hold_screenshot_metadata():
    event = TaskEventCreate(
        task_id="task-1",
        event_type="screenshot",
        message="captured current screen",
        image_base64="data:image/png;base64,abc123",
    )

    assert event.task_id == "task-1"
    assert event.event_type == "screenshot"
    assert event.message == "captured current screen"
    assert event.image_base64 == "data:image/png;base64,abc123"


def test_interrupt_record_defaults_to_unconsumed():
    interrupt = InterruptRecord(task_id="task-1", text="stop now")

    assert interrupt.consumed is False


def test_client_heartbeat_requires_client_id():
    with pytest.raises(ValidationError):
        ClientHeartbeat(is_busy=False)
