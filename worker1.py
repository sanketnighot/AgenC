import json
import os
import time

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# Initialize the AI Client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

WORKER_API = "http://127.0.0.1:8002"
MOCK_MODE = False  # Set to True if API fails during live demo


def process_task(task_description):
    if MOCK_MODE:
        return "MOCK RESULT: The Ethereum price correlation to inflation is 0.85 based on historical data."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast, cheap, and perfect for testing
            messages=[
                {
                    "role": "system",
                    "content": "You are an autonomous agent operating on the AgenC decentralized network. Keep your answers concise, accurate, and under 3 sentences.",
                },
                {"role": "user", "content": f"Execute this bounty: {task_description}"},
            ],
            max_tokens=150,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Execution Error: {str(e)}"


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
                print("[*] Claiming task and querying LLM...")

                # 3. The LLM Brain processes the task
                result = process_task(task)

                # 4. Send the raw result back
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
