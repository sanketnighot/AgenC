import json
import time

import requests

EMITTER_API = "http://127.0.0.1:8001"
WORKER_KEYS = [
    "7f735488b692e04fbb3071c4ad6a2774bd0ec3bb7b5508e09a0d00a31af0e5f4",
    "68ed6920e3d1b7b8ceaf8519006ab614f76cb23738ebf06f364426b8000fe8c0",
]

# 1. Just raw JSON bytes, no Base64!
bounty_payload = json.dumps(
    {
        "type": "NEW_BOUNTY",
        "task": "Analyze ETH prices vs Inflation",
        "reward": "50 USDC",
    }
).encode("utf-8")

for key in WORKER_KEYS:
    print(f"Broadcasting bounty to {key[:8]}...")
    try:
        # Pass the payload directly to the 'data' parameter
        res = requests.post(
            f"{EMITTER_API}/send",
            headers={"X-Destination-Peer-Id": key},
            data=bounty_payload,
        )
        print(f"Node response: {res.status_code}")
    except Exception as e:
        print(f"Failed to send: {e}")

# NOTE: Do NOT run the polling loop below when agenc-api (the bridge) is running.
# Both scripts poll the same /recv endpoint and AXL delivers each message only once —
# whichever process polls first steals the message from the other.
# This file is a standalone test script only; use the frontend + agenc-api instead.
print("Bounties broadcast. (Polling loop disabled — use agenc-api bridge instead.)")
