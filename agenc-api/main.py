import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from arbiter import normalize_fit_score, resolve_winner
from config import (
    ARBITER_SKIP_WHEN_UNANIMOUS,
    BOUNTY_PENDING_MAX_SEC,
    CLAIM_WINDOW_SEC,
    COLLAB_TIMEOUT_SEC,
    NO_CLAIM_AFTER_BROADCAST_SEC,
)

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AXL node addresses ────────────────────────────────────────────────────────
EMITTER_API = "http://127.0.0.1:8001"

WORKER_NODES = {
    "worker_1": {
        "peer_id": "7f735488b692e04fbb3071c4ad6a2774bd0ec3bb7b5508e09a0d00a31af0e5f4",
        "specialty": "Data Analyst",
        "api": "http://127.0.0.1:8002",
    },
    "worker_2": {
        "peer_id": "68ed6920e3d1b7b8ceaf8519006ab614f76cb23738ebf06f364426b8000fe8c0",
        "specialty": "Creative Strategist",
        "api": "http://127.0.0.1:8003",
    },
}

# ── In-memory state ───────────────────────────────────────────────────────────
bounties: dict = {}

# Initialise node_states dynamically from WORKER_NODES so N workers work without hardcoding
node_states: dict = {
    "emitter": {"status": "idle", "label": "Emitter"},
    **{
        nk: {"status": "idle", "label": f"Worker {i + 1}", "specialty": wv["specialty"]}
        for i, (nk, wv) in enumerate(WORKER_NODES.items())
    },
}

for _w in WORKER_NODES.values():
    _w["peer_id"] = _w["peer_id"].strip().lower()

PEER_ID_TO_NODE = {
    v["peer_id"][:8]: k for k, v in WORKER_NODES.items()
}
PEER_ID_FULL_TO_NODE = {
    v["peer_id"]: k for k, v in WORKER_NODES.items()
}

bounty_locks: dict[str, asyncio.Lock] = {}


def _lock(bounty_id: str) -> asyncio.Lock:
    if bounty_id not in bounty_locks:
        bounty_locks[bounty_id] = asyncio.Lock()
    return bounty_locks[bounty_id]


def resolve_node_key(peer_id: str) -> str:
    p = peer_id.strip().lower()
    return PEER_ID_FULL_TO_NODE.get(p) or PEER_ID_TO_NODE.get(p[:8], "")


sse_clients: list[asyncio.Queue] = []


async def broadcast(event: str, data: dict) -> None:
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for q in list(sse_clients):  # copy to avoid race on concurrent disconnect
        await q.put(msg)


def _axl_send(peer_id: str, payload: dict) -> bool:
    try:
        res = requests.post(
            f"{EMITTER_API}/send",
            headers={"X-Destination-Peer-Id": peer_id},
            data=json.dumps(payload).encode("utf-8"),
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


def _axl_recv() -> tuple[str | None, dict | None]:
    try:
        res = requests.get(f"{EMITTER_API}/recv", timeout=5)
        if res.status_code == 200 and res.text.strip():
            from_peer = res.headers.get("X-From-Peer-Id", "").strip().lower()
            return from_peer, res.json()
    except Exception:
        pass
    return None, None


def build_mesh_state() -> dict:
    topo: dict = {}
    try:
        res = requests.get(f"{EMITTER_API}/topology", timeout=3)
        if res.status_code != 200:
            raise RuntimeError("topology unavailable")
        raw = res.json()
        if isinstance(raw, dict):
            topo = raw
    except Exception:
        topo = {}

    peer_list = topo.get("peers")
    if peer_list is None or not isinstance(peer_list, list):
        peer_list = []

    peer_map = {}
    for p in peer_list:
        if not isinstance(p, dict):
            continue
        pk = p.get("public_key")
        if not pk or not isinstance(pk, str):
            continue
        peer_map[pk.strip().lower()] = p

    workers: list[dict] = []
    for nk in sorted(WORKER_NODES.keys()):
        w = WORKER_NODES[nk]
        pid = w["peer_id"]
        match = peer_map.get(pid)
        up = bool(match and match.get("up"))
        workers.append(
            {
                "node_key": nk,
                "label": node_states[nk]["label"],
                "specialty": w["specialty"],
                "peer_id": pid,
                "short_id": pid[:8],
                "mesh_connected": up,
            }
        )
    emitter_pk = topo.get("our_public_key") if isinstance(topo, dict) else ""
    if not isinstance(emitter_pk, str):
        emitter_pk = ""
    return {
        "emitter_public_key": emitter_pk,
        "workers": workers,
    }


async def recv_loop() -> None:
    """Drain ALL buffered AXL messages every poll cycle instead of one-per-tick."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            while True:
                from_peer, payload = await loop.run_in_executor(None, _axl_recv)
                if not payload:
                    break
                await handle_inbound(from_peer, payload)
        except Exception as e:
            logger.warning("recv_loop error: %s", e)
        await asyncio.sleep(0.3)


async def _force_unclaimed(bounty_id: str) -> None:
    async with _lock(bounty_id):
        b = bounties.get(bounty_id)
        if not b or b["status"] != "PENDING":
            return
        # Don't race with resolve_bounty mid-arbitration
        if b.get("claim_phase") == "resolving":
            return
        b["status"] = "UNCLAIMED"
        b["claim_phase"] = None
    node_states["emitter"]["status"] = "idle"
    await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
    await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})


async def _force_collab_timeout(bounty_id: str) -> None:
    """Force a stalled COLLABORATING bounty to UNCLAIMED and idle all nodes."""
    async with _lock(bounty_id):
        b = bounties.get(bounty_id)
        if not b or b["status"] != "COLLABORATING":
            return
        collaborators = list(b.get("collaborators") or [])
        b["status"] = "UNCLAIMED"

    for nk in collaborators:
        if nk in node_states:
            node_states[nk]["status"] = "idle"
            await broadcast("node_status", {"node_id": nk, "status": "idle"})
    node_states["emitter"]["status"] = "idle"
    await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
    await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})
    logger.warning("Collaboration timed out for bounty %s", bounty_id)


async def timeout_watcher() -> None:
    while True:
        now = time.time()
        for bounty_id, b in list(bounties.items()):
            status = b.get("status")

            if status == "PENDING":
                age = now - b["created_at"]
                if age > BOUNTY_PENDING_MAX_SEC:
                    await _force_unclaimed(bounty_id)
                    continue
                if (
                    b.get("claim_phase") == "collecting"
                    and len(b.get("pending_claims") or {}) == 0
                    and age > NO_CLAIM_AFTER_BROADCAST_SEC
                ):
                    await _force_unclaimed(bounty_id)

            elif status == "COLLABORATING":
                started = b.get("collaboration_started_at", b.get("created_at", now))
                if now - started > COLLAB_TIMEOUT_SEC:
                    await _force_collab_timeout(bounty_id)

        await asyncio.sleep(1)


_last_mesh_json: str = ""


async def topology_poll_loop() -> None:
    global _last_mesh_json
    loop = asyncio.get_event_loop()
    while True:
        try:
            state = await loop.run_in_executor(None, build_mesh_state)
            dumped = json.dumps(state, sort_keys=True)
            if dumped != _last_mesh_json:
                _last_mesh_json = dumped
                await broadcast("mesh_state", state)
        except Exception:
            pass
        await asyncio.sleep(2)


async def _delayed_resolve(bounty_id: str, wake_at: float) -> None:
    delay = max(0.0, wake_at - time.time())
    await asyncio.sleep(delay)
    await resolve_bounty(bounty_id)


async def resolve_bounty(bounty_id: str) -> None:
    loop = asyncio.get_event_loop()

    async with _lock(bounty_id):
        b = bounties.get(bounty_id)
        if not b or b["status"] != "PENDING":
            return
        if b.get("claim_phase") != "collecting":
            return
        b["claim_phase"] = "resolving"

    await broadcast("bounty_resolving", {"bounty_id": bounty_id})

    async with _lock(bounty_id):
        b = bounties.get(bounty_id)
        if not b or b["status"] != "PENDING":
            return
        raw = dict(b.get("pending_claims") or {})
        claims_list = list(raw.values())
        task_t = b["task"]
        reward_t = b["reward"]

    if not claims_list:
        async with _lock(bounty_id):
            bb = bounties.get(bounty_id)
            if bb and bb["status"] == "PENDING":
                bb["status"] = "UNCLAIMED"
                bb["claim_phase"] = None
        node_states["emitter"]["status"] = "idle"
        await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
        await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})
        return

    try:
        outcome = await loop.run_in_executor(
            None,
            lambda: resolve_winner(
                task_t,
                reward_t,
                claims_list,
                skip_llm_when_unanimous=ARBITER_SKIP_WHEN_UNANIMOUS,
            ),
        )
    except Exception as e:
        logger.warning("resolve_winner failed: %s", e)
        async with _lock(bounty_id):
            bb = bounties.get(bounty_id)
            if bb and bb["status"] == "PENDING":
                bb["status"] = "UNCLAIMED"
                bb["claim_phase"] = None
        node_states["emitter"]["status"] = "idle"
        await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
        await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})
        return

    await broadcast(
        "arbiter_result",
        {
            "bounty_id": bounty_id,
            "winner_node_key": outcome.winner_node_key,
            "mode": outcome.mode,
            "reason": outcome.reason,
            "source": outcome.source,
        },
    )

    # ── Collaboration mode ────────────────────────────────────────────────────
    if outcome.mode == "collaborate" and len(outcome.collaborator_node_keys) > 1:
        await _dispatch_collaboration(bounty_id, outcome, claims_list, task_t)
        return

    # ── Winner-take-all mode ──────────────────────────────────────────────────
    winner_key = outcome.winner_node_key
    if winner_key not in WORKER_NODES:
        logger.warning("Outcome winner %r not in WORKER_NODES", winner_key)
        async with _lock(bounty_id):
            bb = bounties.get(bounty_id)
            if bb and bb["status"] == "PENDING":
                bb["status"] = "UNCLAIMED"
                bb["claim_phase"] = None
        node_states["emitter"]["status"] = "idle"
        await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
        await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})
        return

    win_claim = next(
        (c for c in claims_list if c.get("node_key") == winner_key),
        claims_list[0],
    )
    from_peer = win_claim.get("from_peer") or WORKER_NODES[winner_key]["peer_id"]
    specialty = win_claim.get("specialty") or WORKER_NODES[winner_key]["specialty"]
    short_id = str(from_peer)[:8]
    claim_peer_keys = list(raw.keys())

    async with _lock(bounty_id):
        bb = bounties.get(bounty_id)
        if not bb or bb["status"] != "PENDING":
            return
        bb["status"] = "CLAIMED"
        bb["winner_id"] = from_peer
        bb["winner_specialty"] = specialty
        bb["claims"] = claim_peer_keys
        bb["claim_phase"] = None

    if winner_key:
        node_states[winner_key]["status"] = "working"
        await broadcast("node_status", {"node_id": winner_key, "status": "working"})

    award_payload = {"type": "AWARD", "bounty_id": bounty_id, "task": task_t}
    ok = await loop.run_in_executor(
        None, _axl_send, WORKER_NODES[winner_key]["peer_id"], award_payload,
    )
    if not ok:
        logger.warning("AWARD send failed for bounty %s → worker %s", bounty_id, winner_key)

    await broadcast(
        "worker_awarded",
        {
            "bounty_id": bounty_id,
            "worker_id": short_id,
            "specialty": specialty,
            "node_key": winner_key,
        },
    )

    for wk, wv in WORKER_NODES.items():
        if wk == winner_key:
            continue
        reject_payload = {"type": "REJECTED", "bounty_id": bounty_id}
        await loop.run_in_executor(None, _axl_send, wv["peer_id"], reject_payload)
        await broadcast(
            "worker_rejected",
            {
                "bounty_id": bounty_id,
                "worker_id": wv["peer_id"][:8],
                "specialty": wv["specialty"],
                "node_key": wk,
            },
        )
        node_states[wk]["status"] = "idle"
        await broadcast("node_status", {"node_id": wk, "status": "idle"})


async def _dispatch_collaboration(
    bounty_id: str,
    outcome,
    claims_list: list,
    task_t: str,
) -> None:
    """Send COLLAB_AWARD to all N collaborators with a full peer_workers list."""
    loop = asyncio.get_event_loop()
    lead_key = outcome.winner_node_key
    collab_keys = [k for k in outcome.collaborator_node_keys if k in WORKER_NODES]

    mesh = await loop.run_in_executor(None, build_mesh_state)
    emitter_peer_id = mesh.get("emitter_public_key", "")
    lead_peer_id = WORKER_NODES[lead_key]["peer_id"]

    # Build enriched worker list for SSE (with is_lead flag)
    collab_workers_sse = []
    for wk in collab_keys:
        claim = next((c for c in claims_list if c.get("node_key") == wk), None)
        specialty = (claim.get("specialty") if claim else None) or WORKER_NODES[wk]["specialty"]
        collab_workers_sse.append({"node_key": wk, "specialty": specialty, "is_lead": wk == lead_key})

    async with _lock(bounty_id):
        bb = bounties.get(bounty_id)
        if not bb or bb["status"] != "PENDING":
            return
        bb["status"] = "COLLABORATING"
        bb["collaboration_mode"] = True
        bb["collaborators"] = collab_keys
        bb["collaboration_started_at"] = time.time()
        bb["winner_id"] = lead_peer_id
        bb["winner_specialty"] = " + ".join(w["specialty"] for w in collab_workers_sse)
        bb["claim_phase"] = None

    for wk in collab_keys:
        if wk in node_states:
            node_states[wk]["status"] = "working"
            await broadcast("node_status", {"node_id": wk, "status": "working"})

    await broadcast("bounty_collaborating", {"bounty_id": bounty_id, "workers": collab_workers_sse})

    # Send COLLAB_AWARD to each worker with all peers except itself
    for wk in collab_keys:
        peer_keys = [k for k in collab_keys if k != wk]
        peer_workers = [
            {
                "peer_id": WORKER_NODES[k]["peer_id"],
                "specialty": next(
                    (w["specialty"] for w in collab_workers_sse if w["node_key"] == k),
                    WORKER_NODES[k]["specialty"],
                ),
                "node_key": k,
            }
            for k in peer_keys
        ]
        collab_award = {
            "type": "COLLAB_AWARD",
            "bounty_id": bounty_id,
            "task": task_t,
            "is_lead": wk == lead_key,
            "lead_node_key": lead_key,
            "lead_peer_id": lead_peer_id,
            "peer_workers": peer_workers,
            "emitter_peer_id": emitter_peer_id,
        }
        ok = await loop.run_in_executor(None, _axl_send, WORKER_NODES[wk]["peer_id"], collab_award)
        if not ok:
            logger.warning("COLLAB_AWARD send failed for bounty %s → worker %s", bounty_id, wk)

    logger.info(
        "Dispatched collaboration for bounty %s: lead=%s, all=%s",
        bounty_id, lead_key, collab_keys,
    )


async def handle_inbound(from_peer: str, payload: dict) -> None:
    loop = asyncio.get_event_loop()
    msg_type = payload.get("type")
    bounty_id = payload.get("bounty_id")

    if msg_type == "CLAIM":
        if not bounty_id or bounty_id not in bounties:
            return

        node_key = resolve_node_key(from_peer)
        specialty = payload.get("specialty", "Unknown")
        short_id = from_peer[:8]

        if not node_key:
            reject_payload = {"type": "REJECTED", "bounty_id": bounty_id}
            await loop.run_in_executor(None, _axl_send, from_peer, reject_payload)
            await broadcast(
                "worker_rejected",
                {"bounty_id": bounty_id, "worker_id": short_id, "specialty": specialty, "node_key": ""},
            )
            return

        rationale = payload.get("claim_rationale") or payload.get("rationale") or ""
        if not isinstance(rationale, str):
            rationale = ""
        rationale = rationale[:300]

        fit_score = normalize_fit_score(payload)

        reject_kind: str | None = None
        should_schedule = False
        wake_at = 0.0

        async with _lock(bounty_id):
            bb = bounties[bounty_id]
            if bb["status"] != "PENDING":
                reject_kind = "not_pending"
            elif bb.get("claim_phase") == "resolving":
                reject_kind = "resolving"

            if reject_kind is None:
                if bb.get("claim_phase") != "collecting":
                    bb["claim_phase"] = "collecting"
                    bb["pending_claims"] = {}

                fp = from_peer.strip().lower()
                bb["pending_claims"][fp] = {
                    "from_peer": fp,
                    "node_key": node_key,
                    "specialty": specialty,
                    "fit_score": fit_score,
                    "claim_rationale": rationale,
                    "received_at": time.time(),
                }

                if bb.get("claim_window_end") is None:
                    bb["claim_window_end"] = time.time() + CLAIM_WINDOW_SEC
                    wake_at = bb["claim_window_end"]
                    should_schedule = True

        if reject_kind:
            reject_payload = {"type": "REJECTED", "bounty_id": bounty_id}
            await loop.run_in_executor(None, _axl_send, from_peer, reject_payload)
            await broadcast(
                "worker_rejected",
                {"bounty_id": bounty_id, "worker_id": short_id, "specialty": specialty, "node_key": node_key},
            )
            return

        if should_schedule:
            asyncio.create_task(_delayed_resolve(bounty_id, wake_at))

        await broadcast(
            "worker_claimed",
            {
                "bounty_id": bounty_id,
                "worker_id": short_id,
                "specialty": specialty,
                "node_key": node_key,
                "fit_score": fit_score,
            },
        )

    elif msg_type == "PEER_MSG_NOTIF":
        await broadcast(
            "worker_direct_message",
            {
                "bounty_id": bounty_id,
                "from_node_key": payload.get("from_node_key", ""),
                "to_node_key": payload.get("to_node_key", ""),
                "msg_type": payload.get("msg_type", "COLLAB_SHARE"),
            },
        )

    elif msg_type == "COMPLETED_BOUNTY":
        if not bounty_id or bounty_id not in bounties:
            return

        result_text = payload.get("result", "")
        collaboration = payload.get("collaboration", False)
        collaborators_payload = payload.get("collaborators", [])
        completing_node_key = resolve_node_key(from_peer)

        async with _lock(bounty_id):
            b = bounties.get(bounty_id)
            if not b or b["status"] in ("COMPLETED", "UNCLAIMED"):
                return
            b["status"] = "COMPLETED"
            b["result"] = result_text
            specialty = payload.get("specialty") or b.get("winner_specialty", "Unknown")
            stored_collaborators = list(b.get("collaborators") or [])

        nodes_to_idle: list[str] = (
            stored_collaborators if (collaboration and stored_collaborators)
            else ([completing_node_key] if completing_node_key else [])
        )

        for nk in nodes_to_idle:
            if nk in node_states:
                node_states[nk]["status"] = "idle"
                await broadcast("node_status", {"node_id": nk, "status": "idle"})

        node_states["emitter"]["status"] = "idle"
        await broadcast("node_status", {"node_id": "emitter", "status": "idle"})

        await broadcast(
            "bounty_completed",
            {
                "bounty_id": bounty_id,
                "result": result_text,
                "specialty": specialty,
                "worker_id": from_peer[:8],
                "node_key": completing_node_key,
                "collaboration": collaboration,
                "collaborators": collaborators_payload,
            },
        )


@app.on_event("startup")
async def start_background_tasks() -> None:
    global _last_mesh_json
    _last_mesh_json = json.dumps(build_mesh_state(), sort_keys=True)
    asyncio.create_task(recv_loop())
    asyncio.create_task(timeout_watcher())
    asyncio.create_task(topology_poll_loop())


@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    sse_clients.append(queue)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            yield f"event: node_snapshot\ndata: {json.dumps(node_states)}\n\n"
            yield f"event: mesh_state\ndata: {json.dumps(build_mesh_state())}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            if queue in sse_clients:
                sse_clients.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class Bounty(BaseModel):
    task: str
    reward: str


@app.post("/api/bounty")
async def broadcast_bounty(bounty: Bounty) -> dict:
    loop = asyncio.get_event_loop()
    bounty_id = str(uuid.uuid4())[:8]

    bounties[bounty_id] = {
        "task": bounty.task,
        "reward": bounty.reward,
        "status": "PENDING",
        "created_at": time.time(),
        "winner_id": None,
        "winner_specialty": None,
        "claims": [],
        "result": None,
        "claim_phase": "collecting",
        "pending_claims": {},
        "claim_window_end": None,
        "collaboration_mode": False,
        "collaborators": [],
    }

    node_states["emitter"]["status"] = "busy"
    await broadcast("node_status", {"node_id": "emitter", "status": "busy"})

    payload = json.dumps(
        {
            "type": "NEW_BOUNTY",
            "bounty_id": bounty_id,
            "task": bounty.task,
            "reward": bounty.reward,
        }
    ).encode("utf-8")

    success_count = 0
    for wv in WORKER_NODES.values():
        try:
            res = await loop.run_in_executor(
                None,
                lambda peer_id=wv["peer_id"]: requests.post(
                    f"{EMITTER_API}/send",
                    headers={"X-Destination-Peer-Id": peer_id},
                    data=payload,
                    timeout=5,
                ),
            )
            if res.status_code == 200:
                success_count += 1
        except Exception:
            pass

    await broadcast(
        "bounty_posted",
        {"bounty_id": bounty_id, "task": bounty.task, "reward": bounty.reward},
    )

    return {"status": "broadcasted", "bounty_id": bounty_id, "sent_to": success_count}


@app.get("/api/nodes")
def get_nodes() -> dict:
    return node_states


@app.get("/api/bounties")
def get_bounties() -> dict:
    return bounties


@app.delete("/api/bounties")
def clear_bounties() -> dict:
    bounties.clear()
    bounty_locks.clear()
    return {"status": "cleared"}
