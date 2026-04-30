import json
import time

import requests

WORKER_API = "http://127.0.0.1:8002"


def process_task(task_description):
    return "MOCK RESULT: Ethereum price correlation to inflation is 0.85"


print("AgenC Worker Node online. Monitoring AXL mesh for bounties...")

while True:
    try:
        req = requests.get(f"{WORKER_API}/recv")
        if req.status_code == 200 and req.text.strip():
            # 1. Grab the sender ID from the header
            sender_id = req.headers.get("X-From-Peer-Id")

            # 2. Parse the raw JSON body
            payload = req.json()

            if payload.get("type") == "NEW_BOUNTY":
                task = payload["task"]
                print(f"\n[!] Bounty detected: {task}")
                print("[*] Claiming task...")

                result = process_task(task)

                # 3. Send the raw result back!
                completion_payload = json.dumps(
                    {"type": "COMPLETED_BOUNTY", "task": task, "result": result}
                ).encode("utf-8")

                res = requests.post(
                    f"{WORKER_API}/send",
                    headers={"X-Destination-Peer-Id": sender_id},
                    data=completion_payload,
                )
                print(f"[+] Completed task sent back! Node status: {res.status_code}")

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"Mesh polling error: {e}")
    time.sleep(2)
