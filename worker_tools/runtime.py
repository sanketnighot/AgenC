"""Multi-turn LLM loop with OpenAI-style tools + telemetry."""

from __future__ import annotations

import json
import logging
from typing import Any

from worker_tools.base import ToolContext, ToolResult, ToolSpec
from worker_telemetry import stream_completion_text, telemetry_emit

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ITERATIONS = 8


def _omit_json_nulls(obj: Any) -> Any:
    """Gemini OpenAI-compat rejects explicit JSON null where a struct is expected (e.g. extra_content)."""
    if isinstance(obj, dict):
        return {
            k: _omit_json_nulls(v)
            for k, v in obj.items()
            if v is not None
        }
    if isinstance(obj, list):
        return [_omit_json_nulls(x) for x in obj]
    return obj


def _assistant_message_for_history(msg: Any) -> dict[str, Any]:
    """
    Serialize the assistant message for the next chat completion request.

    Gemini 3+ (OpenAI compat) attaches thought signatures under each tool call's
    extra_content; rebuilding tool_calls manually drops them and causes 400 errors.
    """
    if hasattr(msg, "model_dump"):
        return _omit_json_nulls(msg.model_dump(mode="json", exclude_none=False))
    tool_calls = getattr(msg, "tool_calls", None) or []
    serialized = []
    for tc in tool_calls:
        if hasattr(tc, "model_dump"):
            serialized.append(tc.model_dump(mode="json", exclude_none=False))
        else:
            entry: dict[str, Any] = {
                "id": tc.id,
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            extra = getattr(tc, "extra_content", None)
            if extra is not None:
                entry["extra_content"] = extra
            serialized.append(entry)
    return _omit_json_nulls(
        {
            "role": "assistant",
            "content": getattr(msg, "content", None),
            "tool_calls": serialized,
        }
    )


def _summarize_for_telemetry(text: str, limit: int = 512) -> str:
    t = text.strip().replace("\n", " ")
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "…"


def run_agent_with_tools(
    client: Any,
    model: str,
    system_prompt: str,
    user_task: str,
    tools: list[ToolSpec],
    *,
    ctx: ToolContext,
    mock_mode: bool,
    max_tokens: int = 1500,
    timeout: float = 90.0,
    max_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    phase_llm: str = "execute",
) -> str:
    """
    If `tools` is empty or `mock_mode`, delegates to streaming completion (legacy behavior).
    Otherwise runs a bounded tool-calling loop using Chat Completions (non-streaming rounds).
    """
    if mock_mode or not tools:
        return stream_completion_text(
            client,
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Execute this bounty: {user_task}"},
            ],
            node_key=ctx.node_key,
            phase=phase_llm,
            bounty_id=ctx.bounty_id,
            stream_id=ctx.stream_id or "",
            max_tokens=max_tokens,
            timeout=timeout,
        )

    by_name = {t.name: t for t in tools}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Execute this bounty: {user_task}"},
    ]
    openai_tools = [t.openai_tool_dict() for t in tools]

    for _ in range(max_iterations):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            logger.warning(
                "tool-enabled completion failed (%s); falling back to plain completion",
                e,
            )
            return stream_completion_text(
                client,
                model,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Execute this bounty: {user_task}"},
                ],
                node_key=ctx.node_key,
                phase=phase_llm,
                bounty_id=ctx.bounty_id,
                stream_id=ctx.stream_id or "",
                max_tokens=max_tokens,
                timeout=timeout,
            )

        choice = resp.choices[0]
        msg = choice.message
        finish = getattr(choice, "finish_reason", None) or ""

        if msg.tool_calls:
            messages.append(_assistant_message_for_history(msg))

            for tc in msg.tool_calls:
                fname = tc.function.name
                raw_args = tc.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                _emit_tool_telemetry(
                    ctx,
                    f"[tool] {fname}({ _summarize_for_telemetry(json.dumps(args), 200) })\n",
                )
                spec = by_name.get(fname)
                if spec is None:
                    result = ToolResult(False, error=f"unknown tool {fname!r}")
                else:
                    try:
                        result = spec.handler(args, ctx)
                    except Exception as ex:
                        logger.warning("tool %s raised: %s", fname, ex)
                        result = ToolResult(False, error=str(ex))
                _emit_tool_telemetry(
                    ctx,
                    f"[tool_result] {fname}: {_summarize_for_telemetry(result.as_json_text())}\n",
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.as_json_text(),
                    }
                )
            continue

        text = (msg.content or "").strip()
        if text:
            _stream_final_answer(ctx, phase_llm, text)
            return text

        if finish == "length":
            return "AI Execution Error: model hit length limit without a final answer."

    return "AI Execution Error: tool loop exceeded maximum iterations."


def _emit_tool_telemetry(ctx: ToolContext, delta: str) -> None:
    if not ctx.stream_id:
        return
    telemetry_emit(
        ctx.node_key,
        ctx.stream_id,
        "tool",
        ctx.bounty_id,
        delta,
        False,
    )


def _stream_final_answer(ctx: ToolContext, phase: str, text: str) -> None:
    """Emit final answer as streaming deltas (dashboard parity with plain completion)."""
    if not ctx.stream_id:
        return
    chunk_size = 24
    for i in range(0, len(text), chunk_size):
        telemetry_emit(
            ctx.node_key,
            ctx.stream_id,
            phase,
            ctx.bounty_id,
            text[i : i + chunk_size],
            False,
        )
    telemetry_emit(ctx.node_key, ctx.stream_id, phase, ctx.bounty_id, "", True)
