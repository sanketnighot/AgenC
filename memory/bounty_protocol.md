---
name: AgenC Bounty Protocol
description: JSON message schema for NEW_BOUNTY, CLAIM, AWARD, COMPLETED_BOUNTY and arbitration flow
type: project
---

## Message Types

### NEW_BOUNTY (Emitter → Workers)

```json
{
  "type": "NEW_BOUNTY",
  "bounty_id": "a1b2c3d4",
  "task": "Analyze the last 5 years of ETH price vs global inflation",
  "reward": "50 USDC"
}
```

### CLAIM (Worker → Emitter)

Collect window opens on **first** CLAIM per bounty; after `CLAIM_WINDOW_SEC`, bridge resolves via LLM arbiter + fallbacks.

```json
{
  "type": "CLAIM",
  "bounty_id": "a1b2c3d4",
  "specialty": "Creative Strategist",
  "fit_score": 0.91,
  "claim_rationale": "Marketing narrative aligns with creative positioning.",
  "confidence": "high"
}
```

### AWARD / REJECTED (Emitter → Worker)

Chosen worker receives `AWARD`; others receive `REJECTED` with same `bounty_id`.

### COMPLETED_BOUNTY (Worker → Emitter)

```json
{
  "type": "COMPLETED_BOUNTY",
  "bounty_id": "a1b2c3d4",
  "task": "Analyze...",
  "result": "The correlation is 0.72 based on historical data..."
}
```

## Bridge arbitration

- Separate credentials: `BRIDGE_*` env (see `agenc-api/.env.example`).
- Fallback if LLM fails: highest `fit_score`, then earliest claim.

## Extension Points

- Tune `CLAIM_WINDOW_SEC`, `BOUNTY_PENDING_MAX_SEC`, `NO_CLAIM_AFTER_BROADCAST_SEC`.
- `ARBITER_SKIP_WHEN_UNANIMOUS=true` skips bridge LLM when only one worker claimed.
