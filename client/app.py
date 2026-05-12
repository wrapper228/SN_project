from __future__ import annotations

import asyncio
import os
import time

from client.agent import (
    add_task_result,
    build_context,
    extract_facts,
    extract_final_text,
    extract_tool_trace,
    load_memory,
    merge_facts,
    sampling_loop,
    save_memory,
)
from client.agent.tools import ToolResult
from client.backend_api import ClientBackendApi
from client.polling import run_once


def execute_task(task, interrupt_fetcher, event_sender):
    memory = load_memory()
    messages = build_context(memory, task.text)
    start_index = len(messages)
    collected_interrupts: list[str] = []

    def output_callback(block):
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text.strip():
                event_sender("text", text)
        elif isinstance(block, dict) and block.get("type") == "internal_event":
            event_sender("internal_event", block.get("name", "internal_event"))

    def tool_output_callback(result: ToolResult, tool_id: str):
        if result.output:
            event_sender("tool_output", result.output)
        if result.error:
            event_sender("tool_error", result.error)
        if result.base64_image:
            event_sender(
                "screenshot",
                f"Screenshot from {tool_id}",
                image_base64=result.base64_image,
            )

    def interrupt_callback():
        items = interrupt_fetcher()
        if not items:
            return None
        collected_interrupts.extend(items)
        return " ".join(items)

    async def runner():
        updated_messages = await sampling_loop(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            messages=messages,
            output_callback=output_callback,
            tool_output_callback=tool_output_callback,
            api_response_callback=lambda request, response, error: None,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            max_tokens=4096,
            only_n_most_recent_images=1,
            interrupt_callback=interrupt_callback,
        )
        result_text = extract_final_text(updated_messages)
        tool_trace = extract_tool_trace(updated_messages, start_index)
        facts = await extract_facts(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            task=task.text,
            result=result_text,
            intermediate_chain=tool_trace,
            interrupts=collected_interrupts,
        )
        updated_memory = add_task_result(memory, task.text, result_text)
        updated_memory = merge_facts(updated_memory, facts)
        save_memory(updated_memory)
        return "done", result_text

    try:
        return asyncio.run(runner())
    except Exception as exc:  # pragma: no cover - runtime safety
        return "failed", f"{type(exc).__name__}: {exc}"


def main() -> None:
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    client_id = os.getenv("CLIENT_ID", "desktop-main")
    api = ClientBackendApi(base_url=backend_url)

    while True:
        worked = run_once(api=api, client_id=client_id, executor=execute_task)
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
