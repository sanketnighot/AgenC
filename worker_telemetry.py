"""Bridge telemetry: POST streamed LLM deltas to agenc-api for SSE fan-out."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)

TELEMETRY_URL = os.environ.get(
    "WORKER_TELEMETRY_BRIDGE_URL",
    "http://127.0.0.1:8000/api/worker/telemetry",
).strip()
TELEMETRY_SECRET = os.environ.get("WORKER_TELEMETRY_SECRET", "").strip()


def telemetry_emit(
    node_key: str,
    stream_id: str,
    phase: str,
    bounty_id: str | None,
    delta: str,
    done: bool,
) -> None:
    """Fire-and-forget POST; never raises."""
    if not TELEMETRY_SECRET:
        return
    body: dict[str, Any] = {
        "node_key": node_key,
        "stream_id": stream_id,
        "phase": phase,
        "bounty_id": bounty_id,
        "delta": delta,
        "done": done,
    }
    try:
        requests.post(
            TELEMETRY_URL,
            headers={
                "X-Telemetry-Secret": TELEMETRY_SECRET,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=4,
        )
    except Exception as e:
        logger.debug("telemetry_emit skipped: %s", e)


def emit_mock_stream_chunks(
    full_text: str,
    *,
    node_key: str,
    phase: str,
    bounty_id: str | None,
    stream_id: str,
    chunk_size: int = 14,
) -> None:
    """Slice MOCK output into fake token deltas for demo dashboards."""
    if not full_text:
        telemetry_emit(node_key, stream_id, phase, bounty_id, "", True)
        return
    for i in range(0, len(full_text), chunk_size):
        telemetry_emit(
            node_key,
            stream_id,
            phase,
            bounty_id,
            full_text[i : i + chunk_size],
            False,
        )
    telemetry_emit(node_key, stream_id, phase, bounty_id, "", True)


def stream_completion_text(
    client: Any,
    model: str,
    messages: list,
    *,
    node_key: str,
    phase: str,
    bounty_id: str | None,
    stream_id: str,
    max_tokens: int,
    timeout: float,
) -> str:
    """
    Stream chat completion; POST token deltas to bridge.
    Falls back to non-streaming if the provider errors on stream=True.
    """
    parts: list[str] = []

    def emit(delta: str, done: bool) -> None:
        telemetry_emit(node_key, stream_id, phase, bounty_id, delta, done)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            ch = chunk.choices[0].delta.content
            if ch:
                parts.append(ch)
                emit(ch, False)
        emit("", True)
        return "".join(parts)
    except Exception as e:
        logger.warning("streaming LLM unavailable (%s); non-stream fallback", e)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            text = resp.choices[0].message.content or ""
            if text:
                emit(text, False)
            emit("", True)
            return text
        except Exception as e2:
            logger.warning("non-stream LLM failed: %s", e2)
            emit("", True)
            return ""


def new_stream_id() -> str:
    return str(uuid.uuid4())
