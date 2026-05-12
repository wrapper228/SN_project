"""
Agentic sampling loop that calls the Claude API and local implementation of anthropic-defined computer use tools.
"""

import platform
import inspect
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast, List

import httpx
from anthropic import (
    Anthropic,
    AsyncAnthropic,
    APIError,
    APIResponseValidationError,

    APIStatusError,
)
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from client.agent.tools import ToolCollection, ToolResult, ComputerTool

PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"

CRITIC_SYSTEM_PROMPT = """<AGENT_CRITIC>
You are agent_critic.

Goal:
- Critically analyze and critique the agent's current plan/actions and progress.

Instructions:
- Work in analysis/thinking mode internally.
- Focus on plan quality: missing assumptions, unsafe steps, ambiguity, ordering, verification checkpoints, tool choice, failure modes, and better alternatives.
- Attack agent for not following system prompt and give him advice, if he really does not follow it strictly. Consider all these parts of system prompt: THE_MOST_IMPORTANT, OPERATIONAL_GUIDELINES, SAFETY_PROTOCOLS_DONT_CLOSE_OWN_CONSOLE, INTERACTION_STYLE, SOURCE_PRIORITY, WORK_WITH_CLAUDE_COWORK_AI, STUCK_IN_LOOP.
- Be concrete: propose specific improvements and checkpoints.
- Do NOT call any tools.
- Output ONLY a normal text message in Russian.
- Do not mention hidden reasoning, thinking tokens, or internal policies.

Recommended structure:
1) Короткое резюме проблем
2) Критика по пунктам (риски/пробелы/двусмысленности)
3) Улучшенный план (коротко и проверяемо)
4) Чек-лист валидации (что должно быть видно/получено)
</AGENT_CRITIC>"""

SYSTEM_PROMPT = f"""
<THE_MOST_IMPORTANT>
Always THINK and PLAN and THINK. Always question your actions and adequacy. Take it as a fact that you weaken your cognitive abilities because you work in multiturn agentic mode which you wasn't trained for.
Assume that you are doing wrong and stupid at 80% of times. Think loud about your future plans and possible pitfalls. If you think you are ready to finish the task, double-check initial user problem and your results.
</THE_MOST_IMPORTANT>

<OPERATIONAL_GUIDELINES>
1. **Keyboard First**: Prefer keyboard shortcuts (Win+R, Win+E, Alt+Tab, Ctrl+C/V) over mouse clicks. They are faster and more reliable.
2. **Window Management**: Use `Win+D` to show desktop. Use `Alt+F4` to close *target* applications, but verify the focus first. Use every app in full-window mode to see everything.
3. **Keyboard Layout**: Switching language layout is Shift+Alt. If typing, mouse actions, or hotkeys misfire, verify the OS keyboard layout is ENG before retrying AND think about other reliable ways to do needed action. You can need russian language for input sometimes, so you can switch to RU layout.
4. **Mouse manipulations (ITS NOT OPTIONAL, ITS MANDATORY)**: Opening apps/files on taskbar or "start menu" is single-click. Opening apps/files on desktop or inside file explorer is double-click.
</OPERATIONAL_GUIDELINES>

<SAFETY_PROTOCOLS_DONT_CLOSE_OWN_CONSOLE>
* **SELF-PRESERVATION**: You are running inside a Terminal/PowerShell window. Avoid closing it. If you close it, the process restarts and current task progress is lost.
* Before closing any window, verify visually that it is NOT your own console window.
</SAFETY_PROTOCOLS_DONT_CLOSE_OWN_CONSOLE>

<INTERACTION_STYLE>
* Skip intro words like "Отлично" or "Great" and speak to the point. 
* Be concise.
* If the user asks for a task, verify the state with a screenshot first (unless you just took one).
* If an action fails, try a different approach (e.g., if clicking an icon fails, try searching via Start Menu).
</INTERACTION_STYLE>

<SOURCE_PRIORITY>
## OSF (HARD): Official Sources First

Scope: any steps/procedures/requirements/prices/limits.

OS=official domain+subdomains (e.g., *.alfabank.ru) incl. official docs/help/dev; PDFs hosted there; official announcements/blog there.
3P=forums/reddit/github/issues/blogs/media/aggregators/SEO.

PRECONDITION (before any 3P): do BOTH and cite:
(1) ≥1 `site:OFFICIAL_DOMAIN` query (+ doc subdomains if separate)
(2) official-site internal search/nav check of relevant section.
No “OS missing” claim without (1)&(2).

3P allowed ONLY if ≥1:
F1 OS blocked/down/paywalled OR required detail absent on OS.
F2 OS contradicts itself OR is clearly outdated.
F3 inherently unofficial (workaround/bug/community tool) AND OS doesn’t cover.
If 3P used: cross-check vs any OS; label “unofficial/may be outdated”; 3P never primary for critical steps.

NAV (hard): if OS exists for the entity → aggregators/info portals forbidden.
HARD SKIP (don’t open) likely SEO/aggregators unless F1–F3 already met:
url/domain has: wiki|info|review|otzyv|banki|sravni|brobank|credits|guide|howto|help- (non-official)
OR page = generic how-to + no primary/issuer citations.

SEARCH ORDER (must): 1) OS only 2) other PRIMARY (regulators/standards/app stores/vendor docs) 3) 3P (gap-fill only).

OUTPUT (must): steps only if backed by OS/PRIMARY (cite). Else: “Not confirmed by official documentation” + stop (no guessing).
Conflicts: prefer OS; if still unclear → state ambiguity + stop.

Violation = critical failure.
</SOURCE_PRIORITY>

<WORK_WITH_CLAUDE_COWORK_AI>
USING CLAUDE COWORK IS MANDATORY FOR EXAMINING AND EDITING DOCUMENTS EVEN IF THEY ARE IN BROWSER.
If you need to work with documents, which are possible to inspect/edit locally (even if they are in browser):
1. You MUST use "Claude" application.
2. Create a working directory named `local_computer_use_<YYYY-MM-DD-HH-MM>` inside Documents folder.
3. Open this directory in Claude, then open "Cowork" tab, then work in created working directory.
4. Delegate ALL file manipulations and analysis to the Claude built-in AI Assistant. If you don't see blinking text cursor after clicking in chat window, don't worry, try typing. Type your request to it and press Enter.
5. Wait for the AI Assistant to finish:
   - Perform `sleep(60)` to give it time.
   - Check status with a screenshot.
   - If still working, `sleep(60)` again.
6. DO NOT edit files manually if Claude Cowork AI can do it. It is trained to handle documents correctly. Before touching a document, ask yourself: “Can this be handled locally via Claude Cowork?” If yes, do so.
7. Even if you just need to examine file (pdf, docx, etc. other downloadble documents), open it in Claude Cowork and ask the AI Assistant to help you analyze it. You always explore files via asking Claude. When examining a file, you should always ask Claude Cowork for all important information inside the file. When you need to edit a file - examine first via asking Claude Cowork.
USING CLAUDE IS MANDATORY FOR EXAMINING AND EDITING DOCUMENTS EVEN IF THEY ARE IN BROWSER.
</WORK_WITH_CLAUDE_COWORK_AI>

<STUCK_IN_LOOP>
Detect loops: same/equivalent action repeated ≥3 times OR ≥3 iterations with no new info/progress OR bouncing between same 2–3 states/windows.

On detection, you MUST stop immediately and output:
"СТОП. ОБНАРУЖЕН ЦИКЛ. ПРОГРЕССА НЕТ."

Then for THIS iteration: do NOT click/type/scroll/run commands—write only.
1) Diagnose: what repeated, intended result, why failed (likely causes), what success signal would confirm fix.
2) Breakout plan: propose 2–4 alternative strategies (what/why/risk). Pick ONE and justify.
3) Anti-relapse constraint for next 2 iterations (choose ≥1):
- Don’t repeat last action/sequence.
- Switch method/tool (kbd vs mouse, different menu path/query/command).
- Add a verification checkpoint before retry.
- Reduce scope: isolate minimal reproducible subtask.
If still stuck after 2 breakout attempts: ask for missing info (screenshot/error text/path/permissions) OR report blockage + safe exit route.
</STUCK_IN_LOOP>
"""


async def sampling_loop(
    *,
    model: str,
    messages: list[BetaMessageParam],
    output_callback: Callable[[BetaContentBlockParam], Any],
    tool_output_callback: Callable[[ToolResult, str], Any],
    api_response_callback: Callable[
        [httpx.Request, httpx.Response | object | None, Exception | None], None
    ],
    api_key: str,
    only_n_most_recent_images: int | None = None,
    max_tokens: int = 4096,
    stats_callback: Callable[[dict], Any] | None = None,
    interrupt_callback: Callable[[], str | None] | None = None,
):
    """
    Agentic sampling loop for the assistant/tool interaction of computer use.
    """
    # Initialize our Local Windows Computer Tool
    computer_tool = ComputerTool()
    tool_collection = ToolCollection(computer_tool)
    total_llm_calls = 0
    thinking_llm_calls = 0
    
    system = BetaTextBlockParam(
        type="text",
        text=SYSTEM_PROMPT,
    )

    client = AsyncAnthropic(api_key=api_key, max_retries=4)
    
    # Determine beta flag based on model
    # >=4.6 models use 2025-11-24, all others use 2025-01-24
    if "4-6" in model:
         computer_use_beta = "computer-use-2025-11-24"
         computer_tool.api_type = "computer_20251124"
    else:
         computer_use_beta = "computer-use-2025-01-24"
         computer_tool.api_type = "computer_20250124"

    betas = [computer_use_beta, PROMPT_CACHING_BETA_FLAG]

    # Tool-use loop detection (coordinate-based):
    # If the agent repeats the same tool/action 3 times with almost the same coordinates,
    # inject a self-reflection instruction AFTER tool_result is appended.
    last_coord_key: str | None = None
    last_coord: tuple[int, int] | None = None
    coord_repeat_count = 0
    coord_streak: list[tuple[int, int]] = []

    def _extract_xy(tool_input: dict[str, Any]) -> tuple[int, int] | None:
        coord = tool_input.get("coordinate")
        if isinstance(coord, (list, tuple)) and len(coord) == 2:
            try:
                return int(coord[0]), int(coord[1])
            except Exception:
                return None
        if isinstance(coord, dict) and "x" in coord and "y" in coord:
            try:
                return int(coord["x"]), int(coord["y"])
            except Exception:
                return None
        return None

    async def _emit_thinking_block(block_obj: Any):
        thinking_text = getattr(block_obj, "thinking", None)
        if thinking_text is None:
            thinking_text = getattr(block_obj, "text", "")
        if isinstance(block_obj, dict) and not thinking_text:
            thinking_text = block_obj.get("text") or block_obj.get("thinking") or ""
        thinking_event: dict[str, Any] = {
            "type": "thinking",
            "text": thinking_text or "",
        }
        if inspect.iscoroutinefunction(output_callback):
            await output_callback(thinking_event)
        else:
            output_callback(thinking_event)

    async def _run_agent_critic(step_to_critic: int):
        nonlocal total_llm_calls, thinking_llm_calls
        call_id = f"s{step_to_critic}-{datetime.utcnow().isoformat(timespec='milliseconds')}Z-{secrets.token_hex(4)}"

        critic_start_event: dict[str, Any] = {
            "type": "internal_event",
            "name": "agent_critic_start",
            "call_id": call_id,
            "step": step_to_critic,
        }
        if inspect.iscoroutinefunction(output_callback):
            await output_callback(critic_start_event)
        else:
            output_callback(critic_start_event)

        # Build critic_messages: original messages + CRITIC_SYSTEM_PROMPT as a user message.
        # The prompt message is ephemeral — it goes to the API but NOT into the real `messages`.
        critic_messages = list(messages) + [{
            "role": "user",
            "content": [{"type": "text", "text": CRITIC_SYSTEM_PROMPT}],
        }]

        try:
            raw_critic = await client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=critic_messages,
                model=model,
                system=[system],
                tools=tool_collection.to_params(),
                betas=betas,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            )
        except (APIStatusError, APIResponseValidationError) as e:
            api_response_callback(e.request, e.response, e)
            return
        except APIError as e:
            api_response_callback(e.request, e.body, e)
            return

        api_response_callback(
            raw_critic.http_response.request, raw_critic.http_response, None
        )

        critic_response = raw_critic.parse()
        total_llm_calls += 1
        critic_had_thinking = False
        if stats_callback and critic_response.usage:
            stats_callback(critic_response.usage.model_dump())

        text_parts: list[str] = []
        for block in critic_response.content:
            if isinstance(block, BetaTextBlock):
                if block.text.strip():
                    text_parts.append(block.text)
                continue

            block_type = getattr(block, "type", None)
            if block_type in ("thinking", "redacted_thinking"):
                critic_had_thinking = True
                await _emit_thinking_block(block)
                continue
            # Ignore tool use and any other non-text blocks in critic mode.

        critic_text = "\n".join(text_parts).strip()

        if critic_had_thinking:
            thinking_llm_calls += 1

        if critic_text:
            critic_block = BetaTextBlockParam(type="text", text=f"[🔍 КРИТИК АГЕНТА — ШАГ {step_to_critic}]\n{critic_text}\n[/КРИТИК]")
            messages.append({"role": "user", "content": [critic_block]})

            if inspect.iscoroutinefunction(output_callback):
                await output_callback(critic_block)
            else:
                output_callback(critic_block)

        critic_end_event: dict[str, Any] = {
            "type": "internal_event",
            "name": "agent_critic_end",
            "call_id": call_id,
            "step": step_to_critic,
        }
        if inspect.iscoroutinefunction(output_callback):
            await output_callback(critic_end_event)
        else:
            output_callback(critic_end_event)
    
    step = 0
    while step < 200:
        # Check for interruption at the start of each thought cycle (Level 1 Check)
        if interrupt_callback:
            interruption_text = interrupt_callback()
            if interruption_text:
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"[🔴 ПОЛЬЗОВАТЕЛЬ ПРЕРВАЛ ВЫПОЛНЕНИЕ И ИЗМЕНИЛ ИНСТРУКЦИИ]\n{interruption_text}\n[Пожалуйста, учти это НЕМЕДЛЕННО и скорректируй текущий план действий.]",
                        }
                    ],
                })
                # We continue the loop so the API sees this new message immediately
                
        enable_prompt_caching = True
        image_truncation_threshold = only_n_most_recent_images or 0

        # IMPORTANT: trim images first to avoid mutating a cache-checkpointed prefix later.
        if only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(
                messages,
                only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )

        if enable_prompt_caching:
            _inject_prompt_caching(messages)
            # only_n_most_recent_images = 0  <-- We must keep truncation enabled to avoid 413 errors!
            system["cache_control"] = {"type": "ephemeral"}  # type: ignore

        # Debug: print tool params to see what's wrong if error occurs
        # print(f"DEBUG: sending tools: {tool_collection.to_params()}")

        try:
            raw_response = await client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=[system],
                tools=tool_collection.to_params(),
                betas=betas,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            )
        except (APIStatusError, APIResponseValidationError) as e:
            api_response_callback(e.request, e.response, e)
            return messages
        except APIError as e:
            api_response_callback(e.request, e.body, e)
            return messages

        api_response_callback(
            raw_response.http_response.request, raw_response.http_response, None
        )

        response = raw_response.parse()
        total_llm_calls += 1
        response_had_thinking = False
        
        if stats_callback and response.usage:
             stats_callback(response.usage.model_dump())

        # Check for interruption BEFORE processing the response
        # This allows the user to change the agent's trajectory in real-time
        interruption_text = None
        if interrupt_callback:
            interruption_text = interrupt_callback()
        
        if interruption_text:
            # User interrupted! Don't execute planned tools.
            # Instead, inject the interruption as a new user message and restart the loop.
            # This forces the agent to re-evaluate the plan with the new context.
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"[🔴 ПОЛЬЗОВАТЕЛЬ ПРЕРВАЛ ВЫПОЛНЕНИЕ И ИЗМЕНИЛ ИНСТРУКЦИИ]\n\n{interruption_text}\n\n[Пожалуйста, учти это НЕМЕДЛЕННО и скорректируй текущий план действий.]",
                    }
                ],
            })
            # Skip the current response and go to next iteration
            continue

        # We need to reconstruct response params carefully to avoid "Extra inputs" error
        # when sending history back to API.
        response_params: list[BetaContentBlockParam] = []
        for block in response.content:
            if isinstance(block, BetaTextBlock):
                response_params.append(BetaTextBlockParam(type="text", text=block.text))
            else:
                # if it's a thinking/redacted_thinking block, preserve it for continuity
                block_type = getattr(block, "type", None)
                if block_type == "thinking":
                    response_had_thinking = True
                    await _emit_thinking_block(block)
                    thinking_payload: dict[str, Any] = {
                        "type": "thinking",
                        "thinking": getattr(block, "thinking", ""),
                    }
                    signature = getattr(block, "signature", None)
                    if signature:
                        thinking_payload["signature"] = signature
                    response_params.append(cast(BetaContentBlockParam, thinking_payload))
                    continue

                if block_type == "redacted_thinking":
                    response_had_thinking = True
                    await _emit_thinking_block(block)
                    redacted_payload: dict[str, Any] = {"type": "redacted_thinking"}
                    data_field = getattr(block, "data", None)
                    if data_field:
                        redacted_payload["data"] = data_field
                    signature = getattr(block, "signature", None)
                    if signature:
                        redacted_payload["signature"] = signature
                    response_params.append(cast(BetaContentBlockParam, redacted_payload))
                    continue
                # It's a ToolUseBlock
                # We must ONLY include known fields. model_dump() might include extra internal fields
                # or defaults that API doesn't like in input history.
                tool_use_param = cast(BetaToolUseBlockParam, {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
                response_params.append(tool_use_param)

        messages.append(
            {
                "role": "assistant",
                "content": response_params,
            }
        )

        if response_had_thinking:
            thinking_llm_calls += 1

        tool_result_content: list[BetaToolResultBlockParam] = []
        coord_loop_triggers: list[dict[str, Any]] = []
        for content_block in response_params:
            # Check for interruption BEFORE showing output or executing tools
            # This gives user a chance to stop execution after seeing the plan
            if isinstance(content_block, dict) and content_block.get("type") == "tool_use":
                interruption_text = None
                if interrupt_callback:
                    interruption_text = interrupt_callback()
                
                if interruption_text:
                    # User interrupted! Notify via output_callback and abort tool execution
                    if inspect.iscoroutinefunction(output_callback):
                        await output_callback(content_block)
                    else:
                        output_callback(content_block)
                    
                    tool_use_block = cast(BetaToolUseBlockParam, content_block)
                    result = ToolResult(
                        output=f"[🔴 ДЕЙСТВИЕ ПРЕРВАНО ПОЛЬЗОВАТЕЛЕМ]\n\nНовая инструкция: {interruption_text}\n\nПожалуйста, прекрати текущее действие и учти новые указания.",
                        is_error=True
                    )
                    tool_result_content.append(
                        _make_api_tool_result(result, tool_use_block["id"])
                    )
                    if inspect.iscoroutinefunction(tool_output_callback):
                        await tool_output_callback(result, tool_use_block["id"])
                    elif tool_output_callback:
                        tool_output_callback(result, tool_use_block["id"])
                    continue  # Skip to next block without executing the tool
            
            # Show output for all blocks (text or tool_use)
            if inspect.iscoroutinefunction(output_callback):
                await output_callback(content_block)
            else:
                output_callback(content_block)

            if (
                isinstance(content_block, dict)
                and content_block.get("type") == "tool_use"
            ):
                tool_use_block = cast(BetaToolUseBlockParam, content_block)

                # Coordinate loop detection (only if tool_input contains coordinate)
                tool_input_dict = cast(dict[str, Any], tool_use_block.get("input", {}))
                xy = _extract_xy(tool_input_dict)
                action = tool_input_dict.get("action")
                coord_key = f"{tool_use_block.get('name')}|{action}" if action is not None else f"{tool_use_block.get('name')}"
                if xy is not None:
                    if (
                        last_coord_key == coord_key
                        and last_coord is not None
                        and abs(xy[0] - last_coord[0]) < 10
                        and abs(xy[1] - last_coord[1]) < 10
                    ):
                        coord_repeat_count += 1
                        coord_streak.append(xy)
                    else:
                        last_coord_key = coord_key
                        last_coord = xy
                        coord_repeat_count = 1
                        coord_streak = [xy]

                    # Trigger only once when reaching 3.
                    if coord_repeat_count == 3:
                        coord_loop_triggers.append(
                            {
                                "tool_name": tool_use_block.get("name"),
                                "action": action,
                                "tool_id": tool_use_block.get("id"),
                                "coords": coord_streak[-3:],
                            }
                        )
                else:
                    # If the current tool_use doesn't have coordinates, don't treat it as part
                    # of a coordinate loop.
                    pass
                
                # Run the tool normally (interruption already handled above)
                result = await tool_collection.run(
                    name=tool_use_block["name"],
                    tool_input=tool_input_dict,
                )
                
                tool_result_content.append(
                    _make_api_tool_result(result, tool_use_block["id"])
                )
                if inspect.iscoroutinefunction(tool_output_callback):
                    await tool_output_callback(result, tool_use_block["id"])
                else:
                    tool_output_callback(result, tool_use_block["id"])

        if not tool_result_content:
            return messages

        messages.append({"content": tool_result_content, "role": "user"})

        # If we detected a coordinate loop, inject a self-reflection instruction AFTER tool_result.
        if coord_loop_triggers:
            lines: list[str] = [
                "[ЦИКЛ ПО КООРДИНАТАМ] 3 раза подряд почти одинаковые coordinate (|Δx|<10, |Δy|<10).",
                "СТОП и саморефлексия перед следующими действиями:",
                "- Цель попытки + ожидаемый сигнал успеха",
                "- Почему не сработало (2–3 гипотезы)",
                "- 2 альтернативы (что сделаешь иначе)",
                "- Выбери 1 и сформулируй проверяемый следующий шаг",
                "Детали повторов:",
            ]
            for t in coord_loop_triggers:
                action_str = f" action={t.get('action')}" if t.get("action") is not None else ""
                coords_str = ", ".join([f"({x},{y})" for x, y in t.get("coords", [])])
                lines.append(
                    f"- tool={t.get('tool_name')}{action_str} tool_id={t.get('tool_id')} coords={coords_str}"
                )

            alarm_text = "\n".join(lines).strip()
            messages.append({"role": "user", "content": [{"type": "text", "text": alarm_text}]})

            # Visible marker for Telegram/console (not sent to API).
            alarm_event: dict[str, Any] = {
                "type": "internal_event",
                "name": "tool_use_coordinate_loop",
                "step": step,
                "count": 3,
                "details": [
                    {
                        "tool": t.get("tool_name"),
                        "action": t.get("action"),
                        "tool_id": t.get("tool_id"),
                        "coords": t.get("coords"),
                    }
                    for t in coord_loop_triggers
                ],
            }
            if inspect.iscoroutinefunction(output_callback):
                await output_callback(alarm_event)
            else:
                output_callback(alarm_event)

        # Insert critique after each XX1 step.
        if step % 10 == 1:
            interruption_text = None
            if interrupt_callback:
                interruption_text = interrupt_callback()
            if interruption_text:
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"[🔴 ПОЛЬЗОВАТЕЛЬ ПРЕРВАЛ ВЫПОЛНЕНИЕ И ИЗМЕНИЛ ИНСТРУКЦИИ]\n\n{interruption_text}\n\n[Пожалуйста, учти это НЕМЕДЛЕННО и скорректируй текущий план действий.]",
                        }
                    ],
                })
            else:
                await _run_agent_critic(step)

        step += 1

        if step % 10 == 0 and total_llm_calls > 0:
            summary_block = {"type": "thinking_stats", "text": f"thinking count: {thinking_llm_calls}/{total_llm_calls}"}
            if inspect.iscoroutinefunction(output_callback):
                await output_callback(summary_block)
            else:
                output_callback(summary_block)
    
    return messages


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int,
):
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[BetaToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and item.get("type") == "tool_result"
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and content.get("type") == "image"
    )

    images_to_remove = total_images - images_to_keep
    # Removed cache chunk logic to aggressively remove images to save space
    # images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and content.get("type") == "image":
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content


def _response_to_params(
    response: BetaMessage,
) -> list[BetaContentBlockParam]:
    res: list[BetaContentBlockParam] = []
    for block in response.content:
        if isinstance(block, BetaTextBlock):
            res.append(BetaTextBlockParam(type="text", text=block.text))
        else:
            # Reconstruct tool use block explicitly
            res.append(cast(BetaToolUseBlockParam, {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input
            }))
    return res


def _inject_prompt_caching(
    messages: list[BetaMessageParam],
):
    # Enforce exactly ONE rolling checkpoint.
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    del block["cache_control"]

    # Place the checkpoint on the most recent safe block.
    # Prefer a text block. If the most recent user message is tool_result-only,
    # allow a tool_result block ONLY if it contains no images (post-trim).
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue

        for block in reversed(content):
            if not isinstance(block, dict):
                continue

            if block.get("type") == "text":
                block["cache_control"] = BetaCacheControlEphemeralParam(  # type: ignore
                    {"type": "ephemeral"}
                )
                return

            if block.get("type") == "tool_result":
                inner = block.get("content")
                has_image = False
                if isinstance(inner, list):
                    has_image = any(
                        isinstance(inner_block, dict)
                        and inner_block.get("type") == "image"
                        for inner_block in inner
                    )
                # If inner is str, it can't contain images.
                if not has_image:
                    block["cache_control"] = BetaCacheControlEphemeralParam(  # type: ignore
                        {"type": "ephemeral"}
                    )
                    return


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
    is_error = False
    if result.error:
        is_error = True
        tool_result_content = _maybe_prepend_system_tool_result(result, result.error)
    else:
        if result.output:
            tool_result_content.append(
                {
                    "type": "text",
                    "text": _maybe_prepend_system_tool_result(result, result.output),
                }
            )
        if result.base64_image:
            tool_result_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": result.image_media_type or "image/png",
                        "data": result.base64_image,
                    },
                }
            )
    return {
        "type": "tool_result",
        "content": tool_result_content,
        "tool_use_id": tool_use_id,
        "is_error": is_error,
    }


def _maybe_prepend_system_tool_result(result: ToolResult, result_text: str):
    if result.system:
        result_text = f"<system>{result.system}</system>\n{result_text}"
    return result_text
