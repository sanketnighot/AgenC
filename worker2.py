import json
import os
import time

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

WORKER_API = "http://127.0.0.1:8003"
MOCK_MODE = False

DECISION_TIMEOUT_SEC = int(os.environ.get("WORKER_DECISION_TIMEOUT_SEC", "60"))


# ── LLM provider config ───────────────────────────────────────────────────────
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
    raise ValueError(f"Unknown LLM_PROVIDER '{PROVIDER}'. Choose: {list(PROVIDERS)}")

_cfg = PROVIDERS[PROVIDER]
MODEL = os.environ.get("LLM_MODEL", _cfg["model"])
client = OpenAI(
    base_url=_cfg["base_url"],
    api_key=os.environ.get(_cfg["api_key_env"]),
)

# ── Personality ───────────────────────────────────────────────────────────────
SPECIALTY = "Creative Strategist"
SYSTEM_PROMPT = (
    "You are a Creative Strategist agent on the AgenC decentralized network. "
    "You specialize in narrative framing, creative ideas, and strategic positioning. "
    "Be bold, original, and inspiring. Keep answers under 4 sentences."
)


# ── LLM self-selection ────────────────────────────────────────────────────────
def evaluate_claim(task: str) -> tuple[bool, float, str]:
    """LLM: whether to bid, 0–1 fit score, short rationale for bridge arbiter."""
    if MOCK_MODE:
        return True, 0.85, "MOCK: specialty-aligned bid."
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a {SPECIALTY} agent. Reply with JSON only, no markdown: "
                        '{"should_claim":true|false,"fit_score":0.0,"claim_rationale":"one short sentence"}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"Task to evaluate:\n{task[:6000]}",
                },
            ],
            max_tokens=120,
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]
        data = json.loads(raw)
        should = bool(data.get("should_claim"))
        try:
            fs = float(data.get("fit_score", 0.0))
        except (TypeError, ValueError):
            fs = 0.0
        fs = max(0.0, min(1.0, fs))
        rationale = str(data.get("claim_rationale") or "").strip()[:300]
        return should, fs, rationale
    except Exception as e:
        print(f"[evaluate_claim error] {e}")
        return False, 0.0, ""


def process_task(task: str) -> str:
    if MOCK_MODE:
        return "MOCK: Position ETH as 'digital gold 2.0' — inflation-resistant, programmable, and battle-tested."
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Execute this bounty: {task}"},
            ],
            max_tokens=150,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI Execution Error: {e}"


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
    except Exception:
        return False


def axl_recv() -> tuple[str | None, dict | None]:
    try:
        res = requests.get(f"{WORKER_API}/recv", timeout=5)
        if res.status_code == 200 and res.text.strip():
            return res.headers.get("X-From-Peer-Id", ""), res.json()
    except Exception:
        pass
    return None, None


# ── Wait for AWARD or REJECTED (correlate by bounty_id) ──────────────────────
def wait_for_decision(bounty_id: str, timeout: int = 10) -> str:
    """Returns 'AWARD', 'REJECTED', or 'TIMEOUT'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, payload = axl_recv()
        if payload:
            msg_type = payload.get("type")
            if payload.get("bounty_id") == bounty_id:
                if msg_type == "AWARD":
                    return "AWARD"
                if msg_type == "REJECTED":
                    return "REJECTED"
            else:
                print(f"[warn] Discarding message for bounty {payload.get('bounty_id')}")
        time.sleep(0.3)
    return "TIMEOUT"


# ── Main loop ─────────────────────────────────────────────────────────────────
print(f"AgenC Worker [{SPECIALTY}] online — provider: {PROVIDER}/{MODEL}. Monitoring AXL mesh for bounties...")

while True:
    try:
        sender_id, payload = axl_recv()

        if payload and payload.get("type") == "NEW_BOUNTY":
            task = payload["task"]
            bounty_id = payload.get("bounty_id", "unknown")
            print(f"\n[bounty] #{bounty_id} received: {task[:60]}")

            print(f"[think]  Evaluating task against {SPECIALTY} specialty...")
            ok, fit_score, rationale = evaluate_claim(task)
            if not ok:
                print(f"[pass]   Task outside {SPECIALTY} specialty — standing down.")
            else:
                print(f"[bid]    Claiming bounty #{bounty_id} (fit={fit_score:.2f})...")
                axl_send(sender_id, {
                    "type": "CLAIM",
                    "bounty_id": bounty_id,
                    "specialty": SPECIALTY,
                    "fit_score": fit_score,
                    "claim_rationale": rationale,
                })

                decision = wait_for_decision(bounty_id, timeout=DECISION_TIMEOUT_SEC)

                if decision == "AWARD":
                    print(f"[award]  Bounty #{bounty_id} awarded! Executing task...")
                    result = process_task(task)
                    axl_send(sender_id, {
                        "type": "COMPLETED_BOUNTY",
                        "bounty_id": bounty_id,
                        "task": task,
                        "result": result,
                        "specialty": SPECIALTY,
                    })
                    print(f"[done]   Result sent: {result[:80]}")

                elif decision == "REJECTED":
                    print(f"[reject] Stood down for bounty #{bounty_id}.")

                else:
                    print(f"[timeout] No decision received for bounty #{bounty_id}.")

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[error] {e}")

    time.sleep(0.5)
