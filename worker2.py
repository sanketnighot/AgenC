"""AgenC Worker — Creative Strategist (asyncio, N-worker collaboration)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI

from worker_telemetry import (
    emit_mock_stream_chunks,
    new_stream_id,
    stream_completion_text,
)
from worker_tools.base import ToolContext
from worker_tools.local_registry import capability_manifest_for, tools_for_creative_strategist
from worker_tools.runtime import run_agent_with_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class TaskOutput:
    """Final worker text plus optional inline images for the bridge UI."""

    text: str
    images: list[dict[str, str]] = field(default_factory=list)


def _images_from_artifact_paths(
    paths: list[str],
    *,
    max_images: int = 4,
    max_total_bytes: int = 4_500_000,
) -> list[dict[str, str]]:
    """Embed PNG/JPEG from disk for COMPLETED_BOUNTY (same host as worker)."""
    out: list[dict[str, str]] = []
    total = 0
    seen: set[str] = set()
    for p in paths:
        if len(out) >= max_images:
            break
        if p in seen:
            continue
        seen.add(p)
        path = Path(p)
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if total + len(raw) > max_total_bytes:
            logger.warning(
                "Skipping image %s: would exceed bounty image budget (%s bytes)",
                path.name,
                max_total_bytes,
            )
            break
        total += len(raw)
        suffix = path.suffix.lower()
        mime = "image/png"
        if suffix in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif suffix == ".webp":
            mime = "image/webp"
        elif suffix == ".gif":
            mime = "image/gif"
        out.append(
            {"mime": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
        )
    return out


# ── Config ────────────────────────────────────────────────────────────────────

def _load_env(path: Path) -> None:
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


_load_env(Path(__file__).parent / ".env")

WORKER_API   = "http://127.0.0.1:8003"
OWN_NODE_KEY = "worker_2"
MOCK_MODE    = os.environ.get("MOCK_MODE", "false").lower() in ("1", "true", "yes")

# ── LLM provider ──────────────────────────────────────────────────────────────

PROVIDERS = {
    "openai": {
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "openai/gpt-4o-mini",
    },
}

PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
if PROVIDER not in PROVIDERS:
    raise ValueError(f"Unknown LLM_PROVIDER {PROVIDER!r}. Choose: {list(PROVIDERS)}")

_cfg = PROVIDERS[PROVIDER]
MODEL = os.environ.get("LLM_MODEL", _cfg["model"])
client = OpenAI(
    base_url=_cfg["base_url"],
    api_key=os.environ.get(_cfg["api_key_env"]),
)

# ── Personality ───────────────────────────────────────────────────────────────

SPECIALTY = "Creative Strategist"
CAPABILITIES = capability_manifest_for("creative")
SYSTEM_PROMPT = (
    "You are a Creative Strategist agent on the AgenC decentralized network. "
    "You specialize in narrative framing, creative ideas, and strategic positioning. "
    "You have tools for web search, shared scratchpad memory, and Gemini image generation — "
    "use them when the bounty needs visuals or external references. "
    "Be bold and inspiring; keep prose concise unless the bounty requires depth."
)
MOCK_RESULT = "MOCK: Position ETH as 'digital gold 2.0' — inflation-resistant, programmable, and battle-tested."

# ── AXL helpers ───────────────────────────────────────────────────────────────

def axl_send(peer_id: str, payload: dict) -> bool:
    try:
        res = requests.post(
            f"{WORKER_API}/send",
            headers={"X-Destination-Peer-Id": peer_id},
            data=json.dumps(payload).encode("utf-8"),
            timeout=5,
        )
        return res.status_code == 200
    except Exception as e:
        logger.debug("axl_send failed: %s", e)
        return False


def axl_recv() -> tuple[Optional[str], Optional[dict]]:
    try:
        res = requests.get(f"{WORKER_API}/recv", timeout=5)
        if res.status_code == 200 and res.text.strip():
            return res.headers.get("X-From-Peer-Id", ""), res.json()
    except Exception:
        pass
    return None, None


# ── LLM calls (blocking — run in executor) ────────────────────────────────────

_CLAIM_JSON_INSTRUCTION_CR = (
    f"You are a {SPECIALTY} agent on AgenC. Given a bounty task, reply with JSON only "
    '(no markdown): {{"should_claim": boolean, "fit_score": number from 0 to 1, '
    '"claim_rationale": string at most 120 characters}}. '
    "should_claim TRUE when the task involves messaging, narrative, positioning, branding, "
    "marketing, UX copy, storytelling, creative angles, campaigns, OR when a technical/analytic "
    "deliverable should be framed for executives or the public. "
    "For purely quantitative tasks (volatility, statistics, raw numbers), still set "
    "should_claim TRUE with a lower fit_score (0.35–0.55) if you can add positioning or "
    "executive-summary value; only decline when there is zero creative or communication angle.\n"
    f"Your tools (IDs): {CAPABILITIES.get('tool_ids', [])}."
)


def _parse_claim_json(text: str) -> dict:
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


def evaluate_claim(task: str, bounty_id: str | None = None) -> dict:
    """Returns should_claim, fit_score (0–1), claim_rationale for the bridge arbiter."""
    sid = new_stream_id()
    if MOCK_MODE:
        raw = (
            '{"should_claim": true, "fit_score": 0.72, '
            '"claim_rationale": "MOCK: narrative and positioning angle."}'
        )
        emit_mock_stream_chunks(
            raw,
            node_key=OWN_NODE_KEY,
            phase="evaluate_claim",
            bounty_id=bounty_id,
            stream_id=sid,
        )
        return _parse_claim_json(raw)
    try:
        raw = stream_completion_text(
            client,
            MODEL,
            [
                {
                    "role": "user",
                    "content": f"{_CLAIM_JSON_INSTRUCTION_CR}\n\nTask:\n{task}",
                },
            ],
            node_key=OWN_NODE_KEY,
            phase="evaluate_claim",
            bounty_id=bounty_id,
            stream_id=sid,
            max_tokens=180,
            timeout=28.0,
        )
        data = _parse_claim_json(raw)
        sc = bool(data.get("should_claim", False))
        try:
            fs = float(data.get("fit_score", 0.0))
        except (TypeError, ValueError):
            fs = 0.0
        fs = max(0.0, min(1.0, fs))
        rat = str(data.get("claim_rationale", ""))[:300]
        return {"should_claim": sc, "fit_score": fs, "claim_rationale": rat}
    except Exception as e:
        logger.warning("evaluate_claim error: %s", e)
        return {"should_claim": False, "fit_score": 0.0, "claim_rationale": ""}


def process_task_with_prompt(
    task: str, system_prompt: str, bounty_id: str | None = None
) -> TaskOutput:
    sid = new_stream_id()
    if MOCK_MODE:
        emit_mock_stream_chunks(
            MOCK_RESULT,
            node_key=OWN_NODE_KEY,
            phase="execute",
            bounty_id=bounty_id,
            stream_id=sid,
        )
        return TaskOutput(text=MOCK_RESULT, images=[])
    ctx = ToolContext(
        node_key=OWN_NODE_KEY,
        bounty_id=bounty_id,
        stream_id=sid,
        worker_api_base=WORKER_API,
    )
    tools = tools_for_creative_strategist(WORKER_API)
    text = run_agent_with_tools(
        client,
        MODEL,
        system_prompt,
        task,
        tools,
        ctx=ctx,
        mock_mode=False,
        max_tokens=1500,
        timeout=120.0,
    )
    if not text.strip():
        return TaskOutput(text="AI Execution Error: empty response", images=[])
    imgs = _images_from_artifact_paths(ctx.artifact_paths)
    return TaskOutput(text=text, images=imgs)


def process_task(task: str, bounty_id: str | None = None) -> TaskOutput:
    return process_task_with_prompt(task, SYSTEM_PROMPT, bounty_id=bounty_id)


def merge_results(
    task: str,
    my_result: str,
    my_specialty: str,
    peer_results: list[str],
    peer_specialties: list[str],
    bounty_id: str | None = None,
) -> str:
    """Merge my result with N peer results into one coherent response."""
    sid = new_stream_id()
    if MOCK_MODE:
        out = " | ".join([my_result] + peer_results)
        emit_mock_stream_chunks(
            out,
            node_key=OWN_NODE_KEY,
            phase="merge",
            bounty_id=bounty_id,
            stream_id=sid,
        )
        return out
    perspectives = f"{my_specialty} perspective:\n{my_result}"
    for result, spec in zip(peer_results, peer_specialties):
        perspectives += f"\n\n{spec} perspective:\n{result}"
    user_msg = (
        f"Task: {task}\n\n"
        f"{perspectives}\n\n"
        "Synthesize all specialist views into one coherent, complete response. "
        "Keep it under 6 sentences."
    )
    text = stream_completion_text(
        client,
        MODEL,
        [{"role": "user", "content": user_msg}],
        node_key=OWN_NODE_KEY,
        phase="merge",
        bounty_id=bounty_id,
        stream_id=sid,
        max_tokens=300,
        timeout=60.0,
    )
    if text.strip():
        return text
    return "\n\n".join([my_result] + peer_results)


# ── Message router ────────────────────────────────────────────────────────────

class MessageRouter:
    """Routes inbound AXL messages to coroutines waiting on them by bounty_id.

    - AWARD / COLLAB_AWARD / REJECTED → asyncio.Future (one response per bounty)
    - COLLAB_SHARE → asyncio.Queue (N-1 responses for N-worker collaboration)
    """

    def __init__(self) -> None:
        self._decisions: dict[str, asyncio.Future] = {}
        self._collab_shares: dict[str, asyncio.Queue] = {}
        # Buffer shares that arrive before the lead registers its queue
        self._share_buffer: dict[str, list[str]] = {}

    def register_decision(self, bounty_id: str) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._decisions[bounty_id] = fut
        return fut

    def unregister_decision(self, bounty_id: str) -> None:
        self._decisions.pop(bounty_id, None)

    def register_collab_shares(self, bounty_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for buffered in self._share_buffer.pop(bounty_id, []):
            q.put_nowait(buffered)
        self._collab_shares[bounty_id] = q
        return q

    def unregister_collab_shares(self, bounty_id: str) -> None:
        self._collab_shares.pop(bounty_id, None)
        self._share_buffer.pop(bounty_id, None)

    def dispatch(self, msg_type: str, bounty_id: str, payload: dict) -> bool:
        """Route message to a waiting coroutine. Returns True if consumed."""
        if msg_type in ("AWARD", "COLLAB_AWARD", "REJECTED"):
            fut = self._decisions.get(bounty_id)
            if fut and not fut.done():
                fut.set_result((msg_type, payload))
                return True

        elif msg_type == "COLLAB_SHARE":
            q = self._collab_shares.get(bounty_id)
            if q is not None:
                q.put_nowait(payload.get("result", ""))
            else:
                self._share_buffer.setdefault(bounty_id, []).append(
                    payload.get("result", "")
                )
            return True

        return False


router = MessageRouter()


# ── Task handlers ─────────────────────────────────────────────────────────────

async def handle_collaboration(payload: dict, fallback_emitter_peer_id: str) -> None:
    loop = asyncio.get_event_loop()
    bounty_id       = payload["bounty_id"]
    task            = payload["task"]
    is_lead         = payload.get("is_lead", False)
    lead_node_key   = payload.get("lead_node_key", "")
    lead_peer_id    = payload.get("lead_peer_id", "")
    emitter_peer_id = payload.get("emitter_peer_id") or fallback_emitter_peer_id

    peer_workers = payload.get("peer_workers", [])
    if not peer_workers and payload.get("peer_worker_id"):
        peer_workers = [{
            "peer_id": payload["peer_worker_id"],
            "specialty": payload.get("peer_specialty", "Unknown"),
            "node_key": "",
        }]

    peer_specialties = [pw["specialty"] for pw in peer_workers]
    logger.info(
        "[collab] %s on #%s — peers: %s",
        "Lead" if is_lead else "Non-lead", bounty_id, peer_specialties,
    )

    collab_prompt = SYSTEM_PROMPT + (
        f"\nIMPORTANT: Other specialists ({', '.join(peer_specialties)}) are also handling "
        f"this task. Focus EXCLUSIVELY on your {SPECIALTY} domain."
    )

    try:
        my_out = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: process_task_with_prompt(task, collab_prompt, bounty_id),
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        my_out = TaskOutput(text=f"{SPECIALTY} task execution timed out.", images=[])
    logger.info("[collab] My result: %s…", my_out.text[:60])

    if is_lead:
        share_queue = router.register_collab_shares(bounty_id)
        peer_results: list[str] = []
        peer_specialties_received: list[str] = []

        try:
            for pw in peer_workers:
                try:
                    result = await asyncio.wait_for(share_queue.get(), timeout=90.0)
                    peer_results.append(result)
                    peer_specialties_received.append(pw["specialty"])
                    logger.info("[collab] Received share from %s", pw["specialty"])
                except asyncio.TimeoutError:
                    logger.warning("[collab] %s timed out — proceeding without.", pw["specialty"])
        finally:
            router.unregister_collab_shares(bounty_id)

        if peer_results:
            try:
                final = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: merge_results(
                            task,
                            my_out.text,
                            SPECIALTY,
                            peer_results,
                            peer_specialties_received,
                            bounty_id,
                        ),
                    ),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                final = "\n\n".join([my_out.text] + peer_results)
        else:
            final = my_out.text

        all_specialties = [SPECIALTY] + peer_specialties_received
        payload_done = {
            "type": "COMPLETED_BOUNTY",
            "bounty_id": bounty_id,
            "result": final,
            "specialty": " + ".join(all_specialties),
            "collaboration": True,
            "collaborators": all_specialties,
        }
        if my_out.images:
            payload_done["images"] = my_out.images
        ok = await loop.run_in_executor(None, axl_send, emitter_peer_id, payload_done)
        if not ok:
            logger.warning("[send_fail] COMPLETED_BOUNTY for #%s", bounty_id)
        else:
            logger.info("[collab] Merged result sent: %s…", final[:80])

    else:
        target_peer_id = lead_peer_id or next(
            (pw["peer_id"] for pw in peer_workers if pw.get("node_key") == lead_node_key),
            "",
        )
        if not target_peer_id:
            logger.warning("[collab] No lead peer_id — COLLAB_SHARE cannot be delivered")

        ok = await loop.run_in_executor(None, axl_send, target_peer_id, {
            "type": "COLLAB_SHARE",
            "bounty_id": bounty_id,
            "result": my_out.text,
            "specialty": SPECIALTY,
        })
        if not ok:
            logger.warning("[send_fail] COLLAB_SHARE to lead for #%s", bounty_id)
        else:
            logger.info("[collab] COLLAB_SHARE sent to lead (P2P)")

        ok = await loop.run_in_executor(None, axl_send, emitter_peer_id, {
            "type": "PEER_MSG_NOTIF",
            "bounty_id": bounty_id,
            "from_node_key": OWN_NODE_KEY,
            "to_node_key": lead_node_key,
            "msg_type": "COLLAB_SHARE",
        })
        if not ok:
            logger.warning("[send_fail] PEER_MSG_NOTIF for #%s", bounty_id)


async def handle_new_bounty(from_peer: str, payload: dict) -> None:
    loop = asyncio.get_event_loop()
    task      = payload["task"]
    bounty_id = payload.get("bounty_id", "unknown")

    try:
        logger.info("[bounty] #%s: %s…", bounty_id, task[:60])

        try:
            ev = await asyncio.wait_for(
                loop.run_in_executor(None, evaluate_claim, task, bounty_id),
                timeout=35.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[timeout] evaluate_claim timed out for #%s", bounty_id)
            return

        if not ev.get("should_claim"):
            logger.info("[pass]   No %s angle — standing down.", SPECIALTY)
            return

        logger.info("[bid]    Claiming #%s…", bounty_id)

        decision_future = router.register_decision(bounty_id)
        try:
            ok = await loop.run_in_executor(None, axl_send, from_peer, {
                "type": "CLAIM",
                "bounty_id": bounty_id,
                "specialty": SPECIALTY,
                "fit_score": ev["fit_score"],
                "claim_rationale": ev["claim_rationale"],
                "confidence": "high",
                "capabilities": CAPABILITIES,
            })
            if not ok:
                logger.warning("[send_fail] CLAIM not delivered for #%s", bounty_id)
                return

            try:
                decision, collab_payload = await asyncio.wait_for(
                    decision_future, timeout=90.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[timeout] No decision for #%s", bounty_id)
                return
        finally:
            router.unregister_decision(bounty_id)

        if decision == "AWARD":
            logger.info("[award]  #%s awarded! Executing…", bounty_id)
            try:
                out = await asyncio.wait_for(
                    loop.run_in_executor(None, process_task, task, bounty_id),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                out = TaskOutput(text="Task execution timed out.", images=[])
            payload_cb = {
                "type": "COMPLETED_BOUNTY",
                "bounty_id": bounty_id,
                "task": task,
                "result": out.text,
                "specialty": SPECIALTY,
            }
            if out.images:
                payload_cb["images"] = out.images
            ok = await loop.run_in_executor(None, axl_send, from_peer, payload_cb)
            if not ok:
                logger.warning("[send_fail] COMPLETED_BOUNTY for #%s", bounty_id)
            logger.info("[done]   #%s: %s…", bounty_id, out.text[:80])

        elif decision == "COLLAB_AWARD":
            await handle_collaboration(collab_payload, from_peer)

        elif decision == "REJECTED":
            logger.info("[reject] Stood down for #%s.", bounty_id)

    except Exception as e:
        logger.error("[error] handle_new_bounty #%s: %s", bounty_id, e, exc_info=True)


# ── Recv loop ─────────────────────────────────────────────────────────────────

async def recv_loop() -> None:
    loop = asyncio.get_event_loop()
    while True:
        try:
            from_peer, payload = await loop.run_in_executor(None, axl_recv)
            if payload:
                msg_type  = payload.get("type", "")
                bounty_id = payload.get("bounty_id", "")

                if not router.dispatch(msg_type, bounty_id, payload):
                    if msg_type == "NEW_BOUNTY":
                        asyncio.create_task(handle_new_bounty(from_peer, payload))
                    else:
                        logger.debug("Unrouted msg type=%s bounty=%s", msg_type, bounty_id)
        except Exception as e:
            logger.warning("recv_loop error: %s", e)
        await asyncio.sleep(0.2)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info(
        "AgenC Worker [%s] online — %s/%s. Listening…",
        SPECIALTY, PROVIDER, MODEL,
    )
    await recv_loop()


if __name__ == "__main__":
    asyncio.run(main())
