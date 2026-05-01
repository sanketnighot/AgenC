---
name: AgenC Project Overview
description: What AgenC is, the core concept, current build status, and Phase 4 goals
type: project
---

AgenC is a **decentralized gig economy for AI agents** — users post research tasks as "bounties" that are broadcast over a P2P mesh (Gensyn AXL), picked up by idle worker agents, processed via OpenAI, and results returned directly to the emitter with no central broker.

**Core concept:** A user posts a massive prompt (e.g., "Analyze 5 years of ETH price vs inflation"). Instead of timing out on one LLM, it's broadcast as a `NEW_BOUNTY` across the AXL mesh. Multiple agents claim chunks, compute independently, and return `COMPLETED_BOUNTY` results.

**Virality angle:** "I just hired an army of decentralized bots to do my research for free."

**Build phases:**
| Phase | Status |
|-------|--------|
| Phase 1 — P2P mesh (3 local AXL nodes) | Complete |
| Phase 2 — OpenAI workers; real results over mesh | Complete |
| Phase 3 — GStack UI; post bounties from web dashboard | Complete |
| Phase 4 — Competitive bidding; visual node status for demo | **NEXT** |

**Why:** Submission to ETHGlobal Open Agents hackathon — judges reward integration depth, utility, and live P2P demo.

**How to apply:** Phase 4 is the active development focus. Competitive bidding means multiple workers race to claim + complete; visual node status means showing live node/mesh activity on the frontend.
