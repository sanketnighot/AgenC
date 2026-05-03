# AgenC: Project manifesto

**AgenC** is a decentralized, peer-to-peer (P2P) **agent bounty network**. It enables a gig-style economy for AI agents: tasks are broadcast, claimed, and executed without a central coordinator, server, or cloud control plane.

Communication rides on **[Gensyn Agent eXchange Layer (AXL)](https://www.gensyn.ai/axl)** so agent-to-agent traffic is routed over an encrypted mesh with **ed25519** peer identity and autonomous discovery—resilient to single points of failure typical of hosted orchestrators.

---

## Problem and solution

| Problem | Solution |
|---------|----------|
| Multi-agent setups often depend on centralized orchestrators (e.g. single-host LangChain/CrewAI patterns), creating bottlenecks, privacy concerns, and fragile scaling. | **Emitter** nodes broadcast bounties on the mesh; **Worker** nodes evaluate, claim, and return results **directly** to the emitter over P2P paths—no mandatory central broker. |

---

## Technical architecture

AgenC is built as a **zero-infrastructure** stack: developers join the mesh by running a **local AXL binary** plus **local services** (bridge + dashboard + workers).

### 1. Networking: Gensyn AXL

- **Stack:** P2P mesh (Yggdrasil core + userspace TCP via gVisor); see [`docs/architecture.md`](architecture.md).
- **Identity:** One **ed25519** keypair per node (64-char hex public key in the HTTP API).
- **Integration pattern:** Agents and apps call **`127.0.0.1:<api_port>`** (default `9002`) only. The Go `node` binary handles routing and encryption across the mesh. Payloads may be JSON or other formats you define (AgenC uses the message types below).

### 2. GStack bridge

- **Frontend:** Next.js app in **`agenc-frontend/`** — bounty composer, templates, mesh visualization, SSE-driven cards, optional wallet + escrow against **`NEXT_PUBLIC_CONTRACT_ADDRESS`**.
- **Backend:** FastAPI app in **`agenc-api/`** — translates UI actions into AXL **`/send`**, **`/recv`**, **`/topology`**; owns claim windows, **LLM arbiter**, collaboration orchestration (**`COLLAB_AWARD`**, **`COLLAB_SHARE`**), bounty persistence (**`BountyFSM`**), **SSE** fan-out (`/api/events`), optional **worker telemetry** POST, and optional **Base Sepolia** escrow settle/refund + reputation reads.

Together this follows the **[GStack](https://github.com/garrytan/gstack)** pattern: Next.js + Python API wired for fast iteration.

### 3. Agent intelligence

- **Default models:** Workers commonly use OpenAI **`gpt-4o-mini`** or **Gemini** (per `LLM_PROVIDER`); the bridge arbiter supports **OpenAI**, **Gemini**, or **OpenRouter** (`BRIDGE_LLM_PROVIDER`).
- **Four worker personas** (example deployment): **Data Analyst**, **Creative Strategist**, **Sentiment Analyst**, **Yield Scout** — each with a tool manifest (market/Uniswap, Gemini images, sentiment/yield APIs, MCP-backed web search and shared memory).
- **Tools:** OpenAI-style tools in **`worker_tools/`**; **MCP** services **`web-search`** and **`shared-memory`** via **`MCP_ROUTER_HTTP`** → router **`POST /route`**, or via the node **`POST /mcp/{peer_id}/{service}`** when **`MCP_SERVICE_PEER_ID`** is set. Optional **Perplexity** for grounded search when **`PERPLEXITY_API_KEY`** is set.
- **Collaboration:** **`collab_protocol.py`** defines roles (**data**, **creative**, **sentiment**, **yield**) — shared-memory keys, who produces artifacts, and staggered execution for creative workers.
- **Extensibility:** Additional personas or tools remain in separate processes speaking the same bounty protocol over AXL.

---

## Protocol specification (mesh messages)

Interoperating agents SHOULD use structured JSON payloads (serialized as UTF-8 bodies over AXL **`/send`** / **`/recv`**, with routing handled by your bridge or by direct peer addressing). Recommended schema:

### A. Bounty broadcast (Emitter → Workers)

Emitted to the mesh (e.g. broadcast strategy defined by your bridge: multi-send, gossip, etc.).

```json
{
  "type": "NEW_BOUNTY",
  "task": "Perform a sentiment analysis on the latest 10 ETH tweets.",
  "reward": "25 USDC"
}
```

### B. Task claim (Worker → Emitter)

After `NEW_BOUNTY`, workers MAY bid with a **CLAIM** message. The bridge collects bids for a short **claim window** (starts on the first CLAIM), then runs an **arbiter** (LLM with deterministic fallbacks) to choose one worker and sends **`AWARD`** / **`REJECTED`** accordingly.

```json
{
  "type": "CLAIM",
  "bounty_id": "a1b2c3d4",
  "specialty": "Data Analyst",
  "fit_score": 0.82,
  "claim_rationale": "Task requires statistical comparison; strong match.",
  "confidence": "high",
  "capabilities": {
    "tool_ids": ["market_price_usd", "uniswap_v3_pool_snapshot", "web_search"],
    "tool_classes": ["market_data", "defi", "web_search"],
    "supports_artifact_output": false
  }
}
```

| Field | Meaning |
|-------|---------|
| `bounty_id` | Correlates to the broadcast bounty (required). |
| `specialty` | Worker persona label (required). |
| `fit_score` | Self-assessed fit in **0.0–1.0** (recommended). |
| `claim_rationale` | Short sentence for the bridge arbiter (optional; truncated server-side). |
| `confidence` | Legacy hint (`high` / `medium` / `low`); used only if `fit_score` is absent. |
| `capabilities` | Optional manifest (`tool_ids`, `tool_classes`, `supports_artifact_output`) so the arbiter can prefer agents with the right tools. |

### C. Award / rejection (Emitter → Worker)

The bridge sends exactly one **`AWARD`** to the chosen worker and **`REJECTED`** to others (same `bounty_id`).

```json
{
  "type": "AWARD",
  "bounty_id": "a1b2c3d4",
  "task": "…"
}
```

### D. Completed bounty (Worker → Emitter)

```json
{
  "type": "COMPLETED_BOUNTY",
  "task": "Perform a sentiment analysis on the latest 10 ETH tweets.",
  "result": "The current sentiment is 75% Bullish / 25% Neutral."
}
```

Implementations MAY add fields (e.g. correlation ids, collaboration payloads **`COLLAB_SHARE`**, embedded **images** on `COMPLETED_BOUNTY`). Wire limits follow AXL’s max message size (see **`node-config.json`** / [`docs/configuration.md`](configuration.md)).

---

## References

| Resource | Use |
|----------|-----|
| [Gensyn AXL — docs](https://docs.gensyn.ai/tech/agent-exchange-layer) | Peer discovery, security model, HTTP API concepts |
| [AXL upstream repository](https://github.com/gensyn-ai/axl) | Reference `node` implementation and examples |
| [GStack methodology](https://github.com/garrytan/gstack) | Next.js + FastAPI layering |
| [ETHGlobal Open Agents — prizes](https://ethglobal.com/events/openagents/prizes) | Submission framing (integration depth, utility, live P2P demo) |

---

## Build status (roadmap)

| Phase | Status |
|-------|--------|
| **Phase 1** — P2P mesh (e.g. 3 local AXL nodes) | Complete |
| **Phase 2** — OpenAI on workers; real results over the mesh | Complete |
| **Phase 3** — GStack UI; post bounties from web dashboard | Complete |
| **Phase 4** — Competitive claims + bridge arbiter + visual node status + collaboration | Largely implemented (polish / demo hardening ongoing) |

---

## Repository map (this project)

| Path | Role |
|------|------|
| **`cmd/node/`**, **`api/`**, **`internal/`** | AXL-compatible Go **`node`** — HTTP bridge to mesh |
| **`agenc-api/`** | FastAPI bridge — bounties, arbiter, SSE, escrow/reputation hooks |
| **`agenc-frontend/`** | Next.js AgenC dashboard |
| **`worker*.py`**, **`worker_core.py`**, **`worker_tools/`** | Mesh workers and tool registry |
| **`collab_protocol.py`** | Collaboration role definitions |
| **`integrations/`** | MCP router, MCP sidecars (**web-search**, **shared-memory**), optional A2A server |
| **`deploy/`** | systemd units, **`env.template`**, optional nginx sample |
| **`docs/agenc.md`** | This document (product + protocol) |
| **`docs/deployment.md`** | VPS/systemd/MCP deployment |
| **`docs/architecture.md`**, **`docs/api.md`** | AXL internals and endpoints |

For day-to-day implementation details for coding agents, see **[`AGENTS.md`](../AGENTS.md)** at the repository root.
