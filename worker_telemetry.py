"""Bridge telemetry: POST streamed LLM deltas to agenc-api for SSE fan-out."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Read lazily: workers load repo-root .env *after* importing this module, so
# import-time os.environ would miss WORKER_TELEMETRY_SECRET.
def _telemetry_url() -> str:
    return os.environ.get(
        "WORKER_TELEMETRY_BRIDGE_URL",
        "http://127.0.0.1:8000/api/worker/telemetry",
    ).strip()


def _telemetry_secret() -> str:
    return os.environ.get("WORKER_TELEMETRY_SECRET", "").strip()


_TELEMETRY_BRIDGE_FAILURE_LOGGED = False


def log_worker_telemetry_startup(logger: logging.Logger) -> None:
    """Call once at worker process start if dashboard streaming matters."""
    if not _telemetry_secret():
        logger.warning(
            "WORKER_TELEMETRY_SECRET is unset — dashboard live stream disabled. "
            "Set it to match BRIDGE_TELEMETRY_SECRET in repo-root .env and restart agenc-api."
        )


def telemetry_emit(
    node_key: str,
    stream_id: str,
    phase: str,
    bounty_id: str | None,
    delta: str,
    done: bool,
) -> None:
    """Fire-and-forget POST; never raises."""
    secret = _telemetry_secret()
    if not secret:
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
        r = requests.post(
            _telemetry_url(),
            headers={
                "X-Telemetry-Secret": secret,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=4,
        )
        if r.status_code >= 400:
            _log_first_telemetry_bridge_issue(r.status_code, r.text[:400])
    except Exception as e:
        _log_first_telemetry_bridge_issue(None, str(e))


def _log_first_telemetry_bridge_issue(code: int | None, detail: str) -> None:
    global _TELEMETRY_BRIDGE_FAILURE_LOGGED
    if _TELEMETRY_BRIDGE_FAILURE_LOGGED:
        return
    _TELEMETRY_BRIDGE_FAILURE_LOGGED = True
    if code == 503:
        hint = "Bridge has BRIDGE_TELEMETRY_SECRET unset — set it in .env and restart agenc-api."
    elif code == 403:
        hint = "Secret mismatch — WORKER_TELEMETRY_SECRET must equal BRIDGE_TELEMETRY_SECRET."
    elif code is not None:
        hint = "Check agenc-api logs and /api/telemetry/status."
    else:
        hint = "Check WORKER_TELEMETRY_BRIDGE_URL (default http://127.0.0.1:8000) and that agenc-api is running."
    logger.warning(
        "Bridge telemetry POST failed%s: %s — %s",
        f" (HTTP {code})" if code is not None else "",
        detail[:200],
        hint,
    )


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
