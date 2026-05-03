"""AgenC Worker — Yield Scout (asyncio, N-worker collaboration)."""

from __future__ import annotations

import asyncio
import functools
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
from worker_tools.local_registry import capability_manifest_for, tools_for_yield_scout
from worker_tools.runtime import run_agent_with_tools

from worker_core import (
    MessageRouter,
    load_env,
    parse_claim_json,
    axl_send as axl_send_base,
    axl_recv as axl_recv_base,
    run_recv_loop,
)
from collab_protocol import collab_memory_hint, collab_read_hint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

router = MessageRouter()

load_env(Path(__file__).parent / ".env")

WORKER_API   = "http://127.0.0.1:8005"
axl_send = functools.partial(axl_send_base, worker_api=WORKER_API)
axl_recv = functools.partial(axl_recv_base, WORKER_API)
OWN_NODE_KEY = "worker_4"
MOCK_MODE    = os.environ.get("MOCK_MODE", "false").lower() in ("1", "true", "yes")
ETH_ADDRESS  = os.environ.get("WORKER4_ETH_ADDRESS", "")

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

SPECIALTY = "Yield Scout"
CAPABILITIES = capability_manifest_for("yield")
SYSTEM_PROMPT = (
    "You are a Yield Scout agent on the AgenC decentralized network. "
    "You specialize in finding the best yield-generating opportunities across DeFi protocols. "
    "Use your tools to fetch real APY data from DeFiLlama, Aave rates, and protocol TVL rankings — "
    "then deliver actionable recommendations with actual numbers. "
    "Always cite the APY %, protocol name, chain, and TVL. Rank options clearly. "
    "Flag impermanent loss risk for LP positions. Keep it structured and concise."
)
MOCK_RESULT = "MOCK: Top yield — Aave USDC on Ethereum 4.8% APY ($2.1B TVL, zero IL risk). Uniswap ETH/USDC 0.05% pool 12% fee APR ($450M TVL, moderate IL)."

_CLAIM_JSON_INSTRUCTION = (
    f"You are a {SPECIALTY} agent on AgenC. Given a bounty task, reply with JSON only "
    '(no markdown): {{"should_claim": boolean, "fit_score": number from 0 to 1, '
    '"claim_rationale": string at most 120 characters}}. '
    "should_claim TRUE when the task involves yield farming, APY comparison, liquidity provision, "
    "DeFi protocol returns, passive income in crypto, staking rewards, lending rates, "
    "Aave/Compound/Curve/Uniswap LP strategies, or finding the best place to park capital. "
    "For general market or sentiment tasks, set should_claim TRUE with fit_score 0.3-0.4 only if "
    "yield or capital efficiency is part of the answer; otherwise decline.\n"
    f"Your tools (IDs): {CAPABILITIES.get('tool_ids', [])}."
)


def evaluate_claim(task: str, bounty_id: str | None = None) -> dict:
    sid = new_stream_id()
    if MOCK_MODE:
        raw = '{"should_claim": true, "fit_score": 0.88, "claim_rationale": "MOCK: yield and DeFi returns angle."}'
        emit_mock_stream_chunks(raw, node_key=OWN_NODE_KEY, phase="evaluate_claim", bounty_id=bounty_id, stream_id=sid)
        return parse_claim_json(raw)
    try:
        raw = stream_completion_text(
            client, MODEL,
            [{"role": "user", "content": f"{_CLAIM_JSON_INSTRUCTION}\n\nTask:\n{task}"}],
            node_key=OWN_NODE_KEY, phase="evaluate_claim", bounty_id=bounty_id,
            stream_id=sid, max_tokens=180, timeout=28.0,
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


def process_task_with_prompt(task: str, system_prompt: str, bounty_id: str | None = None) -> str:
    sid = new_stream_id()
    if MOCK_MODE:
        emit_mock_stream_chunks(MOCK_RESULT, node_key=OWN_NODE_KEY, phase="execute", bounty_id=bounty_id, stream_id=sid)
        return MOCK_RESULT
    ctx = ToolContext(
        node_key=OWN_NODE_KEY,
        bounty_id=bounty_id,
        stream_id=sid,
        worker_api_base=WORKER_API,
    )
    tools = tools_for_yield_scout(WORKER_API)
    text = run_agent_with_tools(
        client, MODEL, system_prompt, task, tools,
        ctx=ctx, mock_mode=False, max_tokens=1500, timeout=90.0,
    )
    return text.strip() or "AI Execution Error: empty response"


def process_task(task: str, bounty_id: str | None = None) -> str:
    return process_task_with_prompt(task, SYSTEM_PROMPT, bounty_id=bounty_id)


def merge_results(
    task: str, my_result: str, my_specialty: str,
    peer_results: list[str], peer_specialties: list[str],
    bounty_id: str | None = None,
) -> str:
    sid = new_stream_id()
    if MOCK_MODE:
        out = " | ".join([my_result] + peer_results)
        emit_mock_stream_chunks(out, node_key=OWN_NODE_KEY, phase="merge", bounty_id=bounty_id, stream_id=sid)
        return out
    perspectives = f"{my_specialty} perspective:\n{my_result}"
    for result, spec in zip(peer_results, peer_specialties):
        perspectives += f"\n\n{spec} perspective:\n{result}"
    user_msg = (
        f"Task: {task}\n\n{perspectives}\n\n"
        "Synthesize all specialist views into one coherent, complete response. Keep it under 6 sentences."
    )
    text = stream_completion_text(
        client, MODEL, [{"role": "user", "content": user_msg}],
        node_key=OWN_NODE_KEY, phase="merge", bounty_id=bounty_id,
        stream_id=sid, max_tokens=300, timeout=60.0,
    )
    return text.strip() or "\n\n".join([my_result] + peer_results)


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
        peer_workers = [{"peer_id": payload["peer_worker_id"], "specialty": payload.get("peer_specialty", "Unknown"), "node_key": ""}]

    peer_specialties = [pw["specialty"] for pw in peer_workers]
    logger.info("[collab] %s on #%s — peers: %s", "Lead" if is_lead else "Non-lead", bounty_id, peer_specialties)

    if is_lead:
        collab_prompt = SYSTEM_PROMPT + (
            f"\nIMPORTANT: You are the LEAD collaborating with {', '.join(peer_specialties)}. "
            f"Focus EXCLUSIVELY on your {SPECIALTY} domain. "
            f"Use your tools and store key findings in shared memory (shared_memory_put) "
            f"using keys: {collab_memory_hint('yield')}. "
            f"Read peer context from: {collab_read_hint('yield')}."
        )
    else:
        collab_prompt = SYSTEM_PROMPT + (
            f"\nIMPORTANT: You are collaborating with {', '.join(peer_specialties)}. "
            f"Read any data they stored using shared_memory_get (try keys: {collab_read_hint('yield')}). "
            f"Incorporate that context into your yield analysis. "
            f"Use your tools (defi_llama_yields, aave_market_rates, protocol_tvl_ranking) and store "
            f"your findings under keys: {collab_memory_hint('yield')}."
        )

    try:
        my_result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: process_task_with_prompt(task, collab_prompt, bounty_id)),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        my_result = f"{SPECIALTY} task execution timed out."
    logger.info("[collab] My result: %s…", my_result[:60])

    if is_lead:
        share_queue = router.register_collab_shares(bounty_id)
        peer_results: list[str] = []
        peer_specialties_received: list[str] = []
        try:
            for pw in peer_workers:
                try:
                    share = await asyncio.wait_for(share_queue.get(), timeout=150.0)
                    if isinstance(share, str):
                        share = {"result": share, "images": []}
                    peer_results.append(share["result"])
                    peer_specialties_received.append(pw["specialty"])
                    logger.info("[collab] Received share from %s", pw["specialty"])
                except asyncio.TimeoutError:
                    logger.warning("[collab] %s timed out — proceeding without.", pw["specialty"])
        finally:
            router.unregister_collab_shares(bounty_id)

        if peer_results:
            try:
                final = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: merge_results(task, my_result, SPECIALTY, peer_results, peer_specialties_received, bounty_id)),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                final = "\n\n".join([my_result] + peer_results)
        else:
            final = my_result

        all_specialties = [SPECIALTY] + peer_specialties_received
        ok = await loop.run_in_executor(None, axl_send, emitter_peer_id, {
            "type": "COMPLETED_BOUNTY",
            "bounty_id": bounty_id,
            "result": final,
            "specialty": " + ".join(all_specialties),
            "collaboration": True,
            "collaborators": all_specialties,
        })
        if not ok:
            logger.warning("[send_fail] COMPLETED_BOUNTY for #%s", bounty_id)

    else:
        target_peer_id = lead_peer_id or next(
            (pw["peer_id"] for pw in peer_workers if pw.get("node_key") == lead_node_key), "",
        )
        ok = await loop.run_in_executor(None, axl_send, target_peer_id, {
            "type": "COLLAB_SHARE",
            "bounty_id": bounty_id,
            "result": my_result,
            "specialty": SPECIALTY,
        })
        if not ok:
            logger.warning("[send_fail] COLLAB_SHARE for #%s", bounty_id)
        await loop.run_in_executor(None, axl_send, emitter_peer_id, {
            "type": "PEER_MSG_NOTIF",
            "bounty_id": bounty_id,
            "from_node_key": OWN_NODE_KEY,
            "to_node_key": lead_node_key,
            "msg_type": "COLLAB_SHARE",
        })


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
                logger.warning("[send_fail] CLAIM for #%s", bounty_id)
                return
            try:
                decision, collab_payload = await asyncio.wait_for(decision_future, timeout=90.0)
            except asyncio.TimeoutError:
                logger.warning("[timeout] No decision for #%s", bounty_id)
                return
        finally:
            router.unregister_decision(bounty_id)

        if decision == "AWARD":
            logger.info("[award]  #%s awarded! Executing…", bounty_id)
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, process_task, task, bounty_id),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                result = "Task execution timed out."
            ok = await loop.run_in_executor(None, axl_send, from_peer, {
                "type": "COMPLETED_BOUNTY",
                "bounty_id": bounty_id,
                "task": task,
                "result": result,
                "specialty": SPECIALTY,
            })
            if not ok:
                logger.warning("[send_fail] COMPLETED_BOUNTY for #%s", bounty_id)
            logger.info("[done]   #%s: %s…", bounty_id, result[:80])

        elif decision == "COLLAB_AWARD":
            await handle_collaboration(collab_payload, from_peer)

        elif decision == "REJECTED":
            logger.info("[reject] Stood down for #%s.", bounty_id)

    except Exception as e:
        logger.error("[error] handle_new_bounty #%s: %s", bounty_id, e, exc_info=True)


async def recv_loop() -> None:
    await run_recv_loop(router, WORKER_API, handle_new_bounty, log=logger)


async def main() -> None:
    log_worker_telemetry_startup(logger)
    logger.info("AgenC Worker [%s] online — %s/%s. Listening…", SPECIALTY, PROVIDER, MODEL)
    await recv_loop()


if __name__ == "__main__":
    asyncio.run(main())
