"""Shared worker utilities: env bootstrap, collaboration payload shape, message routing."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import requests

logger = logging.getLogger(__name__)


def load_env(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ when missing."""
    if not path.exists():
        logger.warning(".env not found at %s — set LLM_PROVIDER etc. manually.", path)
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def parse_claim_json(text: str) -> dict[str, Any]:
    """Extract JSON object from LLM claim evaluation output."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def axl_send(peer_id: str, payload: dict[str, Any], worker_api: str) -> bool:
    """POST JSON to local node's /send (fire-and-forget style)."""
    try:
        res = requests.post(
            f"{worker_api}/send",
            headers={"X-Destination-Peer-Id": peer_id},
            data=json.dumps(payload).encode("utf-8"),
            timeout=5,
        )
        return res.status_code == 200
    except Exception as e:
        logger.debug("axl_send failed: %s", e)
        return False


def axl_recv(worker_api: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Poll local node's /recv; returns (from_peer_hex_or_empty, json_body)."""
    try:
        res = requests.get(f"{worker_api}/recv", timeout=5)
        if res.status_code == 200 and res.text.strip():
            return res.headers.get("X-From-Peer-Id", ""), res.json()
    except Exception:
        pass
    return None, None


async def run_recv_loop(
    router: MessageRouter,
    worker_api: str,
    handle_new_bounty: Callable[[Optional[str], dict[str, Any]], Awaitable[None]],
    *,
    poll_sec: float = 0.2,
    log: Optional[logging.Logger] = None,
) -> None:
    """Poll AXL HTTP recv; dispatch router; spawn ``handle_new_bounty`` for NEW_BOUNTY."""
    loop = asyncio.get_event_loop()
    lg = log or logger
    while True:
        try:
            from_peer, payload = await loop.run_in_executor(
                None,
                lambda: axl_recv(worker_api),
            )
            if payload:
                msg_type = payload.get("type", "")
                bounty_id = payload.get("bounty_id", "")
                if not router.dispatch(str(msg_type), str(bounty_id), payload):
                    if msg_type == "NEW_BOUNTY":
                        asyncio.create_task(handle_new_bounty(from_peer, payload))
                    else:
                        lg.debug("Unrouted msg type=%s bounty=%s", msg_type, bounty_id)
        except Exception as e:
            lg.warning("recv_loop error: %s", e)
        await asyncio.sleep(poll_sec)


def collab_share_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize COLLAB_SHARE body (text + optional embedded images)."""
    r = payload.get("result", "")
    if not isinstance(r, str):
        r = str(r) if r is not None else ""
    imgs = payload.get("images")
    if not isinstance(imgs, list):
        imgs = []
    return {"result": r, "images": imgs}


class MessageRouter:
    """Routes inbound AXL messages to coroutines waiting on them by bounty_id.

    - AWARD / COLLAB_AWARD / REJECTED → asyncio.Future (one response per bounty)
    - COLLAB_SHARE → asyncio.Queue (N-1 responses for N-worker collaboration)
    """

    def __init__(self) -> None:
        self._decisions: dict[str, asyncio.Future] = {}
        self._collab_shares: dict[str, asyncio.Queue] = {}
        self._share_buffer: dict[str, list[Any]] = {}

    def register_decision(self, bounty_id: str) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._decisions[bounty_id] = fut
        return fut

    def unregister_decision(self, bounty_id: str) -> None:
        self._decisions.pop(bounty_id, None)

    def register_collab_shares(self, bounty_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for buffered in self._share_buffer.pop(bounty_id, []):
            if isinstance(buffered, str):
                buffered = {"result": buffered, "images": []}
            q.put_nowait(buffered)
        self._collab_shares[bounty_id] = q
        return q

    def unregister_collab_shares(self, bounty_id: str) -> None:
        self._collab_shares.pop(bounty_id, None)
        self._share_buffer.pop(bounty_id, None)

    def dispatch(self, msg_type: str, bounty_id: str, payload: dict[str, Any]) -> bool:
        if msg_type in ("AWARD", "COLLAB_AWARD", "REJECTED"):
            fut = self._decisions.get(bounty_id)
            if fut and not fut.done():
                fut.set_result((msg_type, payload))
                return True

        if msg_type == "COLLAB_SHARE":
            share = collab_share_from_payload(payload)
            q = self._collab_shares.get(bounty_id)
            if q is not None:
                q.put_nowait(share)
            else:
                self._share_buffer.setdefault(bounty_id, []).append(share)
            return True

        return False
