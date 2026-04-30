import json

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow Next.js frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EMITTER_API = "http://127.0.0.1:8001"
WORKER_KEYS = [
    "7f735488b692e04fbb3071c4ad6a2774bd0ec3bb7b5508e09a0d00a31af0e5f4",
    "68ed6920e3d1b7b8ceaf8519006ab614f76cb23738ebf06f364426b8000fe8c0",
]


class Bounty(BaseModel):
    task: str
    reward: str


@app.post("/api/bounty")
def broadcast_bounty(bounty: Bounty):
    # Raw JSON bytes, matching our successful Phase 1 test
    payload = json.dumps(
        {"type": "NEW_BOUNTY", "task": bounty.task, "reward": bounty.reward}
    ).encode("utf-8")

    success_count = 0
    for key in WORKER_KEYS:
        try:
            res = requests.post(
                f"{EMITTER_API}/send",
                headers={"X-Destination-Peer-Id": key},
                data=payload,
            )
            if res.status_code == 200:
                success_count += 1
        except Exception as e:
            pass

    return {"status": f"Broadcasted to {success_count} nodes"}


@app.get("/api/network-logs")
def poll_network():
    try:
        req = requests.get(f"{EMITTER_API}/recv")
        if req.status_code == 200 and req.text.strip():
            sender = req.headers.get("X-From-Peer-Id", "Unknown")[:8]
            payload = req.json()
            return {"new_event": True, "sender": sender, "payload": payload}
    except Exception:
        pass
    return {"new_event": False}
