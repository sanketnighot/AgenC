"""Bridge timing and arbiter env — loaded from <repo-root>/.env."""

import os
import sys
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        print(
            f"[config] WARNING: .env not found at {path}. "
            "Set BRIDGE_LLM_PROVIDER, GEMINI_API_KEY, etc. manually.",
            file=sys.stderr,
        )
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv(Path(__file__).parent.parent / ".env")

CLAIM_WINDOW_SEC = float(os.environ.get("CLAIM_WINDOW_SEC", "4"))

BOUNTY_PENDING_MAX_SEC = float(os.environ.get("BOUNTY_PENDING_MAX_SEC", "120"))

NO_CLAIM_AFTER_BROADCAST_SEC = float(
    os.environ.get("NO_CLAIM_AFTER_BROADCAST_SEC", "90"),
)

COLLAB_TIMEOUT_SEC = float(os.environ.get("COLLAB_TIMEOUT_SEC", "180"))

ARBITER_SKIP_WHEN_UNANIMOUS = (
    os.environ.get("ARBITER_SKIP_WHEN_UNANIMOUS", "false").lower()
    in ("1", "true", "yes")
)

# When the LLM arbiter fails (invalid JSON, wrong keys), infer collaborate mode if the task
# clearly spans multiple domains and distinct specialists claimed (see arbiter.heuristic_collaboration_outcome).
ARBITER_HEURISTIC_COLLAB = (
    os.environ.get("ARBITER_HEURISTIC_COLLAB", "true").lower()
    in ("1", "true", "yes")
)

# Worker → bridge LLM telemetry (SSE fan-out to dashboard)
BRIDGE_TELEMETRY_SECRET = os.environ.get("BRIDGE_TELEMETRY_SECRET", "").strip()
MAX_TELEMETRY_DELTA_BYTES = int(os.environ.get("MAX_TELEMETRY_DELTA", "8192"))

# Bounty state persistence (shareable URLs survive bridge restart)
BOUNTIES_FILE = os.environ.get(
    "BOUNTIES_FILE",
    str(Path(__file__).parent / "bounties_persist.json"),
)

# Mapping node_key → ETH address for on-chain reputation lookup
WORKER_ETH_ADDRESSES: dict[str, str] = {
    "worker_1": os.environ.get("WORKER1_ETH_ADDRESS", "").strip().lower(),
    "worker_2": os.environ.get("WORKER2_ETH_ADDRESS", "").strip().lower(),
}
