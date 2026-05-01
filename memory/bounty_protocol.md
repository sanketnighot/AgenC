---
name: AgenC Bounty Protocol
description: JSON message schema for NEW_BOUNTY, CLAIM, COMPLETED_BOUNTY and the full flow
type: project
---

## Message Types

### NEW_BOUNTY (Emitter → Workers)
```json
{
  "type": "NEW_BOUNTY",
  "task": "Analyze the last 5 years of ETH price vs global inflation",
  "reward": "50 USDC"
}
```

### CLAIM (Worker → Emitter)
```json
{
  "type": "CLAIM",
  "status": "accepting_task"
}
```

### COMPLETED_BOUNTY (Worker → Emitter)
```json
{
  "type": "COMPLETED_BOUNTY",
  "task": "Analyze...",
  "result": "The correlation is 0.72 based on historical data..."
}
```

## Current Flow

1. User submits task in Next.js UI → POST `/api/bounty` → FastAPI bridge
2. Bridge sends `NEW_BOUNTY` via `/send` to both worker public keys
3. Workers poll `/recv` every 2s; on `NEW_BOUNTY` → call OpenAI gpt-4o-mini
4. Worker sends `COMPLETED_BOUNTY` back to emitter peer ID (from `X-From-Peer-Id` header)
5. Frontend polls `/api/network-logs` every 2s → bridge polls emitter's `/recv` → shows in Mesh Network Logs

## Current Limitation

Workers currently receive the **full task** — no chunking/decomposition yet. Phase 4 goal is competitive bidding where workers race to claim specific sub-tasks.

## Correlation

No correlation ID in current protocol. Workers use `X-From-Peer-Id` header to know where to reply. The bridge hardcodes worker public keys.

## Extension Points (Phase 4)

- Add `bounty_id` field for correlation across multi-chunk tasks
- Add `chunk_index` and `total_chunks` for task decomposition
- Add `bid_amount` or `estimated_time` for competitive bidding
- Add `status` field on CLAIM: `accepted` vs `rejected` (if already claimed)
