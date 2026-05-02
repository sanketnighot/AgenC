# AgenC domain vocabulary

Canonical terms for architecture discussions and code seams. See [`docs/agenc.md`](docs/agenc.md) for protocol JSON and product intent.

## Concepts

| Term | Meaning |
|------|---------|
| **Bounty** | A task broadcast over the mesh by an **Emitter**, with lifecycle states (see below). |
| **Emitter** | The bridge process that broadcasts bounties, arbitrates claims, and streams UI events (SSE). |
| **Worker** | An autonomous agent process that evaluates bounties, sends **Claim** messages, executes when awarded, and returns results. |
| **Claim** | A Worker bid on a Bounty (specialty, fit score, capabilities, rationale). |
| **Award** | The Emitter’s selection after the claim window; the winning Worker enters **EXECUTING** (single-winner) or workers enter **COLLABORATING**. |
| **Collaboration** | Multi-worker execution: lead aggregates peer **COLLAB_SHARE** payloads before completion. |
| **TaskOutput** | Structured Worker result: text plus optional embedded images (`data_base64` / MIME). |
| **ArtifactStore** | On-disk layout under `artifacts/images/<bounty_id>/` for PNG (and future) artifacts produced by tools; Worker embeds them into TaskOutput. |

## Bounty status (bridge authoritative)

1. **PENDING** — collecting or resolving claims (`claim_phase`: `collecting` \| `resolving`).
2. **EXECUTING** — exactly one Worker holds **Award** and is running the task (replaces legacy `CLAIMED` in persisted state and API responses).
3. **COLLABORATING** — multiple Workers active under **COLLAB_AWARD**.
4. **COMPLETED** — result (and optional images) recorded; settlement may follow.
5. **UNCLAIMED** — expired or unresolved; refund path when escrow applies.

Client UI may map **EXECUTING** to labels like “Working”; the stored/API status string is **EXECUTING**.

## Related docs

- [`AGENTS.md`](AGENTS.md) — repo layout, AXL HTTP API.
- [`docs/agenc.md`](docs/agenc.md) — bounty protocol JSON, roadmap.
