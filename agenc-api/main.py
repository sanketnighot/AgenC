import asyncio
import json
import time
import uuid
from typing import AsyncGenerator

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
# bounty_id → { task, reward, status, created_at, winner_id, winner_specialty, claims[], result }

node_states: dict = {
    "emitter": {"status": "idle", "label": "Emitter"},
    "worker_1": {"status": "idle", "label": "Worker 1", "specialty": "Data Analyst"},
    "worker_2": {"status": "idle", "label": "Worker 2", "specialty": "Creative Strategist"},
}

# Normalise all stored peer IDs to lowercase so header comparisons never fail
for _w in WORKER_NODES.values():
    _w["peer_id"] = _w["peer_id"].strip().lower()

PEER_ID_TO_NODE = {
    v["peer_id"][:8]: k for k, v in WORKER_NODES.items()
}
PEER_ID_FULL_TO_NODE = {
    v["peer_id"]: k for k, v in WORKER_NODES.items()
}


def resolve_node_key(peer_id: str) -> str:
    """Resolve a peer ID (full 64-char or 8-char prefix) to a WORKER_NODES key."""
    p = peer_id.strip().lower()
    return PEER_ID_FULL_TO_NODE.get(p) or PEER_ID_TO_NODE.get(p[:8], "")

# ── SSE broadcaster ───────────────────────────────────────────────────────────
sse_clients: list[asyncio.Queue] = []


async def broadcast(event: str, data: dict) -> None:
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for q in sse_clients:
        await q.put(msg)


# ── AXL helpers (sync, called via executor) ───────────────────────────────────
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
    """Returns (from_peer_id, payload) or (None, None) if queue empty."""
    try:
        res = requests.get(f"{EMITTER_API}/recv", timeout=5)
        if res.status_code == 200 and res.text.strip():
            from_peer = res.headers.get("X-From-Peer-Id", "").strip().lower()
            return from_peer, res.json()
    except Exception:
        pass
    return None, None


# ── Background tasks ──────────────────────────────────────────────────────────
async def recv_loop() -> None:
    loop = asyncio.get_event_loop()
    while True:
        try:
            from_peer, payload = await loop.run_in_executor(None, _axl_recv)
            if payload:
                await handle_inbound(from_peer, payload)
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def timeout_watcher() -> None:
    while True:
        now = time.time()
        for bounty_id, b in list(bounties.items()):
            if b["status"] == "PENDING" and (now - b["created_at"]) > 15:
                b["status"] = "UNCLAIMED"
                node_states["emitter"]["status"] = "idle"
                await broadcast("node_status", {"node_id": "emitter", "status": "idle"})
                await broadcast("bounty_unclaimed", {"bounty_id": bounty_id})
        await asyncio.sleep(1)


async def handle_inbound(from_peer: str, payload: dict) -> None:
    loop = asyncio.get_event_loop()
    msg_type = payload.get("type")
    bounty_id = payload.get("bounty_id")

    if msg_type == "CLAIM":
        if not bounty_id or bounty_id not in bounties:
            return

        b = bounties[bounty_id]
        node_key = resolve_node_key(from_peer)
        specialty = payload.get("specialty", "Unknown")
        short_id = from_peer[:8]

        await broadcast("worker_claimed", {
            "bounty_id": bounty_id,
            "worker_id": short_id,
            "specialty": specialty,
            "node_key": node_key,
        })

        if b["status"] == "PENDING":
            # First CLAIM — award this worker
            b["status"] = "CLAIMED"
            b["winner_id"] = from_peer
            b["winner_specialty"] = specialty
            b["claims"].append(from_peer)

            if node_key:
                node_states[node_key]["status"] = "working"
                await broadcast("node_status", {"node_id": node_key, "status": "working"})

            award_payload = {"type": "AWARD", "bounty_id": bounty_id, "task": b["task"]}
            await loop.run_in_executor(None, _axl_send, from_peer, award_payload)
            await broadcast("worker_awarded", {
                "bounty_id": bounty_id,
                "worker_id": short_id,
                "specialty": specialty,
                "node_key": node_key,
            })

            # Reject all other workers — compare by node key, not raw peer ID
            for wk, wv in WORKER_NODES.items():
                if wk != node_key:
                    reject_payload = {"type": "REJECTED", "bounty_id": bounty_id}
                    await loop.run_in_executor(None, _axl_send, wv["peer_id"], reject_payload)
                    await broadcast("worker_rejected", {
                        "bounty_id": bounty_id,
                        "worker_id": wv["peer_id"][:8],
                        "specialty": wv["specialty"],
                        "node_key": wk,
                    })
                    node_states[wk]["status"] = "idle"
                    await broadcast("node_status", {"node_id": wk, "status": "idle"})

        else:
            # Late CLAIM — bounty already awarded; reject immediately
            reject_payload = {"type": "REJECTED", "bounty_id": bounty_id}
            await loop.run_in_executor(None, _axl_send, from_peer, reject_payload)
            await broadcast("worker_rejected", {
                "bounty_id": bounty_id,
                "worker_id": short_id,
                "specialty": specialty,
                "node_key": node_key,
            })

    elif msg_type == "COMPLETED_BOUNTY":
        if not bounty_id or bounty_id not in bounties:
            return

        b = bounties[bounty_id]
        b["status"] = "COMPLETED"
        b["result"] = payload.get("result", "")
        specialty = payload.get("specialty", b.get("winner_specialty", "Unknown"))
        short_id = from_peer[:8]

        node_key = resolve_node_key(from_peer)
        if node_key:
            node_states[node_key]["status"] = "idle"
            await broadcast("node_status", {"node_id": node_key, "status": "idle"})

        node_states["emitter"]["status"] = "idle"
        await broadcast("node_status", {"node_id": "emitter", "status": "idle"})

        await broadcast("bounty_completed", {
            "bounty_id": bounty_id,
            "result": b["result"],
            "specialty": specialty,
            "worker_id": short_id,
        })


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def start_background_tasks() -> None:
    asyncio.create_task(recv_loop())
    asyncio.create_task(timeout_watcher())


# ── SSE endpoint ──────────────────────────────────────────────────────────────
@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    sse_clients.append(queue)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial node state snapshot so the client syncs on connect
            yield f"event: node_snapshot\ndata: {json.dumps(node_states)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # keep connection alive
        finally:
            sse_clients.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── REST endpoints ────────────────────────────────────────────────────────────
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
    }

    node_states["emitter"]["status"] = "busy"
    await broadcast("node_status", {"node_id": "emitter", "status": "busy"})

    payload = json.dumps({
        "type": "NEW_BOUNTY",
        "bounty_id": bounty_id,
        "task": bounty.task,
        "reward": bounty.reward,
    }).encode("utf-8")

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

    await broadcast("bounty_posted", {
        "bounty_id": bounty_id,
        "task": bounty.task,
        "reward": bounty.reward,
    })

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
    return {"status": "cleared"}
