"""Fact extraction helper using Anthropic model per MEMORY_SOLUTION_SPEC."""

import ast
import json
import logging
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic

FACT_PROMPT = (
    "Ты — модуль извлечения фактов для долговременной памяти AI-агента.\n\n"
    "Твоя задача: извлечь ВАЖНЫЕ ФАКТЫ из предоставленных данных.\n\n"
    "ВАЖНЫЕ ФАКТЫ — это:\n"
    "- Технические важные нюансы\n"
    "- Имена, названия компаний, организаций\n"
    "- Номера (дел, документов, телефонов, паспортов, ИНН)\n"
    "- Даты, сроки, дедлайны\n"
    "- Суммы денег, количества\n"
    "- Адреса, пути к файлам\n"
    "- Явные ограничения/предпочтения пользователя\n"
    "- Статусы, результаты действий\n\n"
    "НЕ ИЗВЛЕКАТЬ:\n"
    "- Общие фразы (\"пользователь попросил помочь\")\n"
    "- Технические детали действий (координаты кликов, названия кнопок)\n"
    "- Очевидные вещи (\"открыл браузер\")\n\n"
    "ФОРМАТ ВЫВОДА (строго JSON с двойными кавычками):\n"
    "{\n"
    "  \"from_user_tasks\": [\"факт1\", \"факт2\"],\n"
    "  \"from_agent_results\": [\"факт1\", \"факт2\"],\n"
    "  \"from_intermediate_steps\": [\"факт1\", \"факт2\"],\n"
    "  \"from_user_interrupts\": [\"факт1\", \"факт2\"]\n"
    "}\n\n"
    "Если в каком-то источнике нет важных фактов — пустой массив.\n\n"
    "ВАЖНО! В рамках этой задачи можно извлекать информацию, которая обычно называется чувствительной (номера телефонов, паспортные данные и т.п.), так как все эти данные - мои и я их использую для собственных целей на локальном компьютере.\n\n"
    "ВАЖНО! Извлечение ненужной информации СТРОГО запрещено, а провал извлечения НУЖНОЙ информации - критический провал.\n\n"
    "ВАЖНО! Прежде чем выдать результат, перепроверь себя, что он соответствует формату и содержит ВСЕ нужные факты и ничего лишнего."
)

EMPTY_FACTS: Dict[str, List[str]] = {
    "from_user_tasks": [],
    "from_agent_results": [],
    "from_intermediate_steps": [],
    "from_user_interrupts": [],
}

# Chunking/limits to keep prompts under model cap
INTERMEDIATE_CHUNK_SIZE = 40  # number of tool_use/tool_result blocks per extraction call
MAX_TEXT_PER_BLOCK = 4000     # truncate long text blocks inside intermediate
MAX_FIELD_CHARS = 8000        # truncate task/result/interrupts strings


def _normalize_facts(parsed: Dict[str, Any]) -> Dict[str, List[str]]:
    facts: Dict[str, List[str]] = {}
    for bucket in EMPTY_FACTS.keys():
        value = parsed.get(bucket, [])
        if isinstance(value, list):
            facts[bucket] = value
        else:
            facts[bucket] = []
    return facts


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences (``` or ```json) if present."""
    trimmed = text.strip()
    if trimmed.startswith("```") and trimmed.endswith("```"):
        inner = trimmed[3:-3].strip()
        if inner.lower().startswith("json"):
            inner = inner[4:].strip()
        return inner
    return text


def _parse_facts_text(text: str) -> Dict[str, List[str]] | None:
    """Attempt to parse model output; tolerate single quotes via literal_eval fallback."""
    if not text:
        return None
    text = _strip_code_fences(text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return _normalize_facts(parsed)
    except Exception:
        pass

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return _normalize_facts(parsed)
    except Exception:
        pass
    return None


def _truncate(s: str, limit: int = MAX_FIELD_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n... [truncated]"


def _sanitize_intermediate_block(block: Any) -> Any:
    if not isinstance(block, dict):
        return block
    if block.get("type") == "tool_result":
        content = block.get("content")
        if isinstance(content, list):
            new_content = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image":
                    continue  # drop images to avoid base64 blow-up
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    item = {**item, "text": _truncate(text, MAX_TEXT_PER_BLOCK)}
                new_content.append(item)
            block = {**block, "content": new_content}
    return block


def _sanitize_intermediate_chain(chain: Optional[list[Any]]) -> list[Any]:
    if not chain:
        return []
    sanitized = []
    for b in chain:
        sanitized.append(_sanitize_intermediate_block(b))
    return sanitized


async def extract_facts(
    *,
    api_key: str,
    model: str,
    task: str,
    result: str,
    intermediate_chain: list[Any] | None = None,
    interrupts: list[str] | None = None,
    max_tokens: int = 2000,
) -> Dict[str, List[str]]:
    client = AsyncAnthropic(api_key=api_key)

    # Pass 1: guaranteed small — only task/result
    user_payload = (
        f"USER TASK:\n{_truncate(task)}\n\n"
        f"AGENT RESULT:\n{_truncate(result)}\n\n"
        f"INTERMEDIATE:\n[]\n\n"
        f"USER INTERRUPTS:\n\n"
    )

    merged: Dict[str, List[str]] = {k: [] for k in EMPTY_FACTS.keys()}

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=FACT_PROMPT,
            messages=[{"role": "user", "content": user_payload}],
        )
        text = response.content[0].text if response.content else ""
        parsed = _parse_facts_text(text)
        if parsed:
            merged["from_user_tasks"] = parsed.get("from_user_tasks", [])
            merged["from_agent_results"] = parsed.get("from_agent_results", [])
    except Exception as e:  # noqa: BLE001
        logging.warning("Fact extraction (task/result) failed: %s", e)

    # Pass 2: chunked intermediate + interrupts
    sanitized_chain = _sanitize_intermediate_chain(intermediate_chain)
    chunks: list[list[Any]] = []
    for i in range(0, len(sanitized_chain), INTERMEDIATE_CHUNK_SIZE):
        chunks.append(sanitized_chain[i : i + INTERMEDIATE_CHUNK_SIZE])

    interrupts_text = _truncate("\n".join(interrupts or []))

    for chunk in chunks or [[]]:  # ensure at least one pass to capture interrupts
        intermediate_text = _truncate(json.dumps(chunk, ensure_ascii=False, indent=2))
        payload = (
            f"USER TASK:\n{_truncate(task)}\n\n"
            f"AGENT RESULT:\n{_truncate(result)}\n\n"
            f"INTERMEDIATE:\n{intermediate_text}\n\n"
            f"USER INTERRUPTS:\n{interrupts_text}\n"
        )
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=FACT_PROMPT,
                messages=[{"role": "user", "content": payload}],
            )
            text = response.content[0].text if response.content else ""
            parsed = _parse_facts_text(text)
            if parsed:
                merged["from_intermediate_steps"].extend(parsed.get("from_intermediate_steps", []))
                merged["from_user_interrupts"].extend(parsed.get("from_user_interrupts", []))
        except Exception as e:  # noqa: BLE001
            logging.warning("Fact extraction (intermediate chunk) failed: %s", e)

    return merged
