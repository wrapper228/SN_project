"""Memory storage and context building per MEMORY_SOLUTION_SPEC."""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List


def _as_text_blocks(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]

MEMORY_FILE = Path("data/agent_memory.json")
MAX_TASK_RESULTS = 50
MAX_FACTS_PER_BUCKET = 100

EMPTY_MEMORY: Dict[str, Any] = {
    "task_results": [],
    "facts": {
        "from_user_tasks": [],
        "from_agent_results": [],
        "from_intermediate_steps": [],
        "from_user_interrupts": [],
    },
}


def load_memory() -> Dict[str, Any]:
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if not isinstance(data, dict):
                    return deepcopy(EMPTY_MEMORY)
                # Ensure all expected keys exist
                data.setdefault("task_results", [])
                data.setdefault("facts", {})
                for key in EMPTY_MEMORY["facts"].keys():
                    data["facts"].setdefault(key, [])
                return data
            except Exception:
                return deepcopy(EMPTY_MEMORY)
    return deepcopy(EMPTY_MEMORY)


def save_memory(memory: Dict[str, Any]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def _trim_list(items: List[Any], max_len: int) -> List[Any]:
    if len(items) <= max_len:
        return items
    # FIFO: drop oldest entries
    return items[-max_len:]


def enforce_limits(memory: Dict[str, Any]) -> Dict[str, Any]:
    memory["task_results"] = _trim_list(memory.get("task_results", []), MAX_TASK_RESULTS)
    facts = memory.get("facts", {})
    for key in EMPTY_MEMORY["facts"].keys():
        facts[key] = _trim_list(facts.get(key, []), MAX_FACTS_PER_BUCKET)
    memory["facts"] = facts
    return memory


def add_task_result(memory: Dict[str, Any], task: str, result: str) -> Dict[str, Any]:
    memory.setdefault("task_results", [])
    memory["task_results"].append({"task": task, "result": result})
    return enforce_limits(memory)


def merge_facts(memory: Dict[str, Any], new_facts: Dict[str, List[str]]) -> Dict[str, Any]:
    facts = memory.setdefault("facts", {})
    for bucket in EMPTY_MEMORY["facts"].keys():
        current = facts.get(bucket, [])
        additions = new_facts.get(bucket, []) if isinstance(new_facts, dict) else []
        if additions:
            current.extend(additions)
        facts[bucket] = current
    memory["facts"] = facts
    return enforce_limits(memory)


def build_context(memory: Dict[str, Any], current_task: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    # 1. Add all task_results
    if memory.get("task_results"):
        history_text = "[ИСТОРИЯ ВЫПОЛНЕННЫХ ЗАДАЧ]\n\n"
        for i, tr in enumerate(memory["task_results"], 1):
            history_text += f"Задача {i}: {tr.get('task', '')}\n"
            history_text += f"Результат: {tr.get('result', '')}\n\n"
        messages.append({"role": "user", "content": _as_text_blocks(history_text)})
        messages.append({"role": "assistant", "content": _as_text_blocks("Понял, учту эту историю.")})

    # 2. Add all facts
    facts = memory.get("facts", {})
    if any(facts.get(k) for k in EMPTY_MEMORY["facts"].keys()):
        facts_text = "[ИЗВЕСТНЫЕ ФАКТЫ]\n\n"

        if facts.get("from_user_tasks"):
            facts_text += "Из постановок задач:\n"
            for f in facts["from_user_tasks"]:
                facts_text += f"• {f}\n"
            facts_text += "\n"

        if facts.get("from_agent_results"):
            facts_text += "Из результатов выполнения:\n"
            for f in facts["from_agent_results"]:
                facts_text += f"• {f}\n"
            facts_text += "\n"

        if facts.get("from_intermediate_steps"):
            facts_text += "Обнаружено в процессе работы:\n"
            for f in facts["from_intermediate_steps"]:
                facts_text += f"• {f}\n"
            facts_text += "\n"

        if facts.get("from_user_interrupts"):
            facts_text += "Указания пользователя:\n"
            for f in facts["from_user_interrupts"]:
                facts_text += f"• {f}\n"

        messages.append({"role": "user", "content": _as_text_blocks(facts_text)})
        messages.append({"role": "assistant", "content": _as_text_blocks("Принял к сведению все факты.")})

    # 3. Add current task
    messages.append({"role": "user", "content": _as_text_blocks(current_task)})

    return messages


def extract_tool_trace(messages: list[Any], start_index: int) -> list[Any]:
    """Collect intermediate blocks from messages[start_index:].

    Includes:
    - assistant `text` blocks (intermediate reasoning / observations)
    - `tool_use` and `tool_result` blocks

    Excludes:
    - the final assistant message's text blocks (the final answer is passed separately as `result`)
    """

    trace: list[Any] = []

    last_assistant_index: int | None = None
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant_index = i

    for i in range(start_index, len(messages)):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type")
            if block_type in {"tool_use", "tool_result"}:
                trace.append(block)
                continue

            if (
                block_type == "text"
                and role == "assistant"
                and last_assistant_index is not None
                and i != last_assistant_index
            ):
                trace.append(block)

    return trace


def extract_final_text(messages: list[Any]) -> str:
    """Return concatenated text from the last assistant message."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, list):
                texts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
                if texts:
                    return "\n".join(texts).strip()
            elif isinstance(content, str):
                return content.strip()
    return ""
