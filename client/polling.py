from __future__ import annotations

from collections.abc import Callable


def run_once(api, client_id: str, executor: Callable) -> bool:
    api.heartbeat(client_id=client_id, is_busy=False)
    task = api.poll_next_task(client_id=client_id)
    if task is None:
        return False

    api.heartbeat(client_id=client_id, is_busy=True, current_task_id=task.id)

    def interrupt_fetcher() -> list[str]:
        return api.consume_interrupts(task.id)

    def event_sender(
        event_type: str,
        message: str = "",
        image_base64: str | None = None,
    ) -> None:
        api.send_event(
            task_id=task.id,
            event_type=event_type,
            message=message,
            image_base64=image_base64,
        )

    status, result_text = executor(task, interrupt_fetcher, event_sender)
    api.complete_task(task.id, status, result_text)
    api.heartbeat(client_id=client_id, is_busy=False, current_task_id=None)
    return True
