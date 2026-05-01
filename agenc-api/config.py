"""Bridge timing and arbiter env (see .env.example)."""

import os

CLAIM_WINDOW_SEC = float(os.environ.get("CLAIM_WINDOW_SEC", "4"))

BOUNTY_PENDING_MAX_SEC = float(os.environ.get("BOUNTY_PENDING_MAX_SEC", "120"))

NO_CLAIM_AFTER_BROADCAST_SEC = float(
    os.environ.get("NO_CLAIM_AFTER_BROADCAST_SEC", "90"),
)

ARBITER_SKIP_WHEN_UNANIMOUS = (
    os.environ.get("ARBITER_SKIP_WHEN_UNANIMOUS", "false").lower()
    in ("1", "true", "yes")
)
