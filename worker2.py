"""AgenC Worker — Creative Strategist (asyncio, N-worker collaboration)."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
from pathlib import Path
from openai import OpenAI

from worker_telemetry import (
    emit_mock_stream_chunks,
    log_worker_telemetry_startup,
    new_stream_id,
    stream_completion_text,
)
from worker_tools.base import ToolContext
from worker_tools.local_registry import capability_manifest_for, tools_for_creative_strategist
from worker_tools.runtime import run_agent_with_tools

from worker_tools.artifact_store import DEFAULT_STORE, TaskOutput, merge_bounty_images
from worker_core import (
    MessageRouter,
    load_env,
    parse_claim_json,
    axl_send as axl_send_base,
    axl_recv as axl_recv_base,
    run_recv_loop,
)
from collab_protocol import collab_memory_hint, collab_read_hint, get_role

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

router = MessageRouter()

load_env(Path(__file__).parent / ".env")

WORKER_API   = "http://127.0.0.1:8003"
axl_send = functools.partial(axl_send_base, worker_api=WORKER_API)
axl_recv = functools.partial(axl_recv_base, WORKER_API)
OWN_NODE_KEY = "worker_2"
MOCK_MODE    = os.environ.get("MOCK_MODE", "false").lower() in ("1", "true", "yes")
ETH_ADDRESS  = os.environ.get("WORKER2_ETH_ADDRESS", "")
# Whole-task executor budget (image gen + multi-turn tools often exceeds 90s).
_EXECUTOR_TASK_TIMEOUT = float(os.environ.get("WORKER_EXECUTOR_TIMEOUT_SEC", "300"))
# Single chat.completions call inside the tool loop (Gemini image round-trip).
_AGENT_LLM_CALL_TIMEOUT = float(os.environ.get("WORKER_AGENT_LLM_TIMEOUT_SEC", "240"))

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


def _task_output_from_timeout(bounty_id: str | None, message: str) -> TaskOutput:
    ctx = ToolContext(
        node_key=OWN_NODE_KEY,
        bounty_id=bounty_id,
        stream_id=None,
        worker_api_base=WORKER_API,
    )
    return DEFAULT_STORE.from_timeout(ctx, bounty_id, message)


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
        return parse_claim_json(raw)
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
        data = parse_claim_json(raw)
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
        timeout=_AGENT_LLM_CALL_TIMEOUT,
    )
    if not text.strip():
        return TaskOutput(text="AI Execution Error: empty response", images=[])
    return DEFAULT_STORE.finalize(text, ctx, bounty_id)


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

    if is_lead:
        collab_prompt = SYSTEM_PROMPT + (
            f"\nIMPORTANT: You are the LEAD collaborating with {', '.join(peer_specialties)}. "
            f"Focus EXCLUSIVELY on your {SPECIALTY} domain. "
            f"Use your tools to gather data and store key results in shared memory "
            f"(shared_memory_put) using keys such as: {collab_memory_hint('creative')}. "
            f"You may read peer context from: {collab_read_hint('creative')}."
        )
    else:
        collab_prompt = SYSTEM_PROMPT + (
            f"\nIMPORTANT: You are collaborating with {', '.join(peer_specialties)} who is gathering data. "
            f"Your job is to create the visual output for this task. "
            f"First, read the data your collaborator stored using shared_memory_get "
            f"(try keys like {collab_read_hint('creative')}). "
            f"Then call gemini_generate_image with a detailed prompt incorporating that data. "
            f"Do NOT just describe what you will do — actually call the tools now."
        )

    # Non-lead waits for lead to finish gathering data and writing to shared memory
    if not is_lead:
        await asyncio.sleep(get_role("creative").non_lead_delay_sec)

    try:
        my_out = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: process_task_with_prompt(task, collab_prompt, bounty_id),
            ),
            timeout=_EXECUTOR_TASK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        my_out = _task_output_from_timeout(
            bounty_id, f"{SPECIALTY} task execution timed out."
        )
    logger.info("[collab] My result: %s…", my_out.text[:60])

    if is_lead:
        share_queue = router.register_collab_shares(bounty_id)
        peer_results: list[str] = []
        peer_specialties_received: list[str] = []

        peer_image_lists: list[list[dict[str, str]]] = []
        try:
            for pw in peer_workers:
                try:
                    share = await asyncio.wait_for(share_queue.get(), timeout=90.0)
                    if isinstance(share, str):
                        share = {"result": share, "images": []}
                    peer_results.append(share["result"])
                    imgs = share.get("images")
                    peer_image_lists.append(
                        imgs if isinstance(imgs, list) else []
                    )
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
                    timeout=120.0,
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
        merged_imgs = merge_bounty_images(my_out.images, *peer_image_lists)
        if merged_imgs:
            payload_done["images"] = merged_imgs
        ok = await loop.run_in_executor(None, axl_send, emitter_peer_id, payload_done)
        if not ok:
            logger.warning("[send_fail] COMPLETED_BOUNTY for #%s", bounty_id)
        else:
            logger.info("[collab] Merged result sent: %s…", final[:80])
            if not merged_imgs:
                asyncio.create_task(_maybe_send_late_bounty_images(emitter_peer_id, bounty_id))

    else:
        target_peer_id = lead_peer_id or next(
            (pw["peer_id"] for pw in peer_workers if pw.get("node_key") == lead_node_key),
            "",
        )
        if not target_peer_id:
            logger.warning("[collab] No lead peer_id — COLLAB_SHARE cannot be delivered")

        share_payload: dict = {
            "type": "COLLAB_SHARE",
            "bounty_id": bounty_id,
            "result": my_out.text,
            "specialty": SPECIALTY,
        }
        if my_out.images:
            share_payload["images"] = my_out.images
        ok = await loop.run_in_executor(None, axl_send, target_peer_id, share_payload)
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
                "eth_address": ETH_ADDRESS,
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
                    timeout=_EXECUTOR_TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                out = _task_output_from_timeout(bounty_id, "Task execution timed out.")
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
            elif not payload_cb.get("images"):
                asyncio.create_task(_maybe_send_late_bounty_images(from_peer, bounty_id))
            logger.info("[done]   #%s: %s…", bounty_id, out.text[:80])

        elif decision == "COLLAB_AWARD":
            await handle_collaboration(collab_payload, from_peer)

        elif decision == "REJECTED":
            logger.info("[reject] Stood down for #%s.", bounty_id)

    except Exception as e:
        logger.error("[error] handle_new_bounty #%s: %s", bounty_id, e, exc_info=True)


async def _maybe_send_late_bounty_images(emitter_peer: str, bounty_id: str) -> None:
    """Emit a second COMPLETED_BOUNTY with images if files landed after the first send."""
    await asyncio.sleep(12.0)
    ctx = ToolContext(
        node_key=OWN_NODE_KEY,
        bounty_id=bounty_id,
        stream_id=None,
        worker_api_base=WORKER_API,
    )
    DEFAULT_STORE.harvest(ctx, bounty_id)
    imgs = DEFAULT_STORE.embed_with_retry(ctx)
    if not imgs:
        return
    payload = {
        "type": "COMPLETED_BOUNTY",
        "bounty_id": bounty_id,
        "result": "",
        "specialty": SPECIALTY,
        "images": imgs,
    }
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, axl_send, emitter_peer, payload)
    if ok:
        logger.info("[late_images] supplemental COMPLETED_BOUNTY (%s images) #%s", len(imgs), bounty_id)


# ── Recv loop ─────────────────────────────────────────────────────────────────

async def recv_loop() -> None:
    await run_recv_loop(router, WORKER_API, handle_new_bounty, log=logger)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    log_worker_telemetry_startup(logger)
    logger.info(
        "AgenC Worker [%s] online — %s/%s. Listening…",
        SPECIALTY, PROVIDER, MODEL,
    )
    await recv_loop()


if __name__ == "__main__":
    asyncio.run(main())
