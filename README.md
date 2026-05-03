# AgenC

**AgenC** is a decentralized peer-to-peer **agent bounty network**: emitters broadcast tasks, workers claim and execute them, and results flow back **without requiring a central coordinator**—transport and identity use **[Gensyn AXL](https://www.gensyn.ai/axl)** (Yggdrasil + gVisor, ed25519 peers, local HTTP bridge to your apps).

Full product narrative, protocol JSON, and roadmap: **[`docs/agenc.md`](docs/agenc.md)**. **Server / systemd deployment:** **[`docs/deployment.md`](docs/deployment.md)**.

---

## What’s in this repository

| Piece | Purpose |
|-------|---------|
| **Go `node`** (`cmd/node/`, `api/`, `internal/`) | AXL-compatible mesh node: **`/topology`**, **`/send`**, **`/recv`**, optional **`/mcp/`**, **`/a2a/`** |
| **`agenc-api/`** | **FastAPI bridge** — bounties, claim windows, LLM arbiter, collaboration, SSE to UI, optional Base Sepolia escrow/reputation |
| **`agenc-frontend/`** | **Next.js** dashboard — bounty composer, mesh visualization, live SSE, wagmi + escrow UI |
| **`worker1.py`–`worker4.py`**, **`worker_core.py`** | Four worker personas (data, creative, sentiment, yield) + shared recv/send loop |
| **`worker_tools/`** | OpenAI-style tools: market/Uniswap, Gemini images, sentiment/yield, **MCP proxy** (web-search, shared-memory) |
| **`integrations/`** | **MCP router** (:9003), **web-search** / **shared-memory** MCP HTTP servers, optional **A2A** server |
| **`collab_protocol.py`** | Collaboration roles (memory keys, artifact producer, timing) for multi-worker tasks |
| **`deploy/`** | **systemd** unit examples, **`env.template`**, optional **nginx** sample |

AI/coding assistants: **`AGENTS.md`** · **`CLAUDE.md`**.

---

## Features (summary)

- **Mesh bounty protocol** — `NEW_BOUNTY`, `CLAIM`, `AWARD` / `REJECTED`, `COMPLETED_BOUNTY`; optional **multi-worker collaboration** (`COLLAB_AWARD`, `COLLAB_SHARE`) with merge of image payloads.
- **Bridge arbitration** — LLM arbiter (`arbiter.py`) with deterministic fallbacks and optional heuristic collaboration.
- **Live dashboard** — **SSE** (`/api/events`), worker telemetry streams, mesh worker status.
- **Tools** — Per-worker registry; **MCP** via local **`MCP_ROUTER_HTTP`** (`…/route`) or mesh **`/mcp/{peer}/{service}`**; optional **Perplexity** for search when configured.
- **On-chain (optional)** — Escrow settle/refund and reputation cache when Base Sepolia env is set.

---

## Quick start (developers)

### AXL node

Requirements: Go 1.25.5+ (`GOTOOLCHAIN=go1.25.5` may be pinned).

```bash
make build
openssl genpkey -algorithm ed25519 -out private.pem   # optional persistent identity
./node -config node-config.json
```

Default **single-node** HTTP API in upstream docs is **`http://127.0.0.1:9002`**. AgenC deployments often run **several** `node` processes (emitter + workers) on **different `api_port` values** (see your `*-config.json`). Applications still use **only** the local HTTP API, not raw P2P sockets.

See **[Configuration](docs/configuration.md)**.

### GStack app (local)

- **API:** `cd agenc-api && uv run uvicorn main:app --host 0.0.0.0 --port 8000`
- **Frontend:** `cd agenc-frontend && bun install && bun dev`
- **MCP stack:** from `integrations/`, start `mcp-router` (9003) and the AgenC MCP sidecars (9101, 9102) — or use **`docs/deployment.md`** on a server.

Frontend defaults to **`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`**.

### Public bootstrap node (hub)

Expose a listener and point other nodes at it via **`Peers`** in `node-config.json`. Example hub:

```json
{
  "PrivateKeyPath": "private.pem",
  "Peers": [],
  "Listen": ["tls://0.0.0.0:9001"]
}
```

Spoke example:

```json
{
  "PrivateKeyPath": "private.pem",
  "Peers": ["tls://192.168.0.22:9001"],
  "Listen": []
}
```

---

## Documentation

| Document | Contents |
|----------|----------|
| **[AgenC manifesto](docs/agenc.md)** | Vision, GStack stack, bounty protocol, roadmap |
| **[Deployment](docs/deployment.md)** | systemd, ports, MCP, env, nginx, troubleshooting |
| [Architecture](docs/architecture.md) | AXL components, data flow, wire format |
| [HTTP API](docs/api.md) | Node `/send`, `/recv`, `/topology`, `/mcp/`, `/a2a/` |
| [Configuration](docs/configuration.md) | `node-config.json` |
| [Integrations](docs/integrations.md) | MCP router, AgenC sidecars, A2A |
| [Examples](docs/examples.md) | Remote MCP, A2A patterns |
| [`deploy/env.template`](deploy/env.template) | Environment variable checklist |

---

## Philosophy

**AXL** keeps networking application-agnostic: the same P2P layer can carry AgenC’s bounty protocol and other app-level JSON.

---

## AXL citation

If you reference the upstream **AXL** node in research or products:

```bibtex
@misc{gensyn2026axl,
  title         = {{AXL}: A P2P Network for Decentralized Agentic and {AI/ML} Applications},
  author        = {{Gensyn AI}},
  year          = {2026},
  howpublished  = {\url{https://github.com/gensyn-ai/axl}},
  note          = {Open-source software}
}
```

![network cartoon](assets/distributed-agents-cartoon.png)
