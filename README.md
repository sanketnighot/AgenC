# AgenC

**AgenC** is a decentralized peer-to-peer **agent bounty network**: emitters broadcast tasks, workers claim and execute them, and results flow back **without requiring a central coordinator**—transport and identity use **[Gensyn AXL](https://www.gensyn.ai/axl)** (Yggdrasil + gVisor, ed25519 peers, local HTTP bridge to your apps).

Full product narrative, architecture, JSON message schema, and roadmap: **[`docs/agenc.md`](docs/agenc.md)**.

---

## What’s in this repository

| Piece | Purpose |
|-------|---------|
| **Go `node`** (`cmd/node/`, `api/`, `internal/`) | AXL-compatible mesh node: local **`/topology`**, **`/send`**, **`/recv`**, optional **`/mcp/`**, **`/a2a/`** |
| **`agenc-frontend/`** | Next.js dashboard (GStack UI) for bounties and activity |
| **FastAPI bridge** (outside or alongside this repo in your deployment) | Connects the UI to the local AXL node |

AI/coding assistants: **`AGENTS.md`** (implementation details) · **`CLAUDE.md`** (points to both).

---

## AXL node quick start

Requirements: Go 1.25.5+ (`GOTOOLCHAIN=go1.25.5` may be pinned by the build).

```bash
make build
openssl genpkey -algorithm ed25519 -out private.pem   # optional persistent identity
./node -config node-config.json
```

Default local API: **`http://127.0.0.1:9002`**. Applications never dial remote peers directly; they use this HTTP bridge.

See **[Configuration](docs/configuration.md)** for CLI flags and `node-config.json`.

### Public bootstrap node (hub)

Expose a listener and point other nodes at it via **`Peers`** in `node-config.json`. Example hub:

```json
{
  "PrivateKeyPath": "private.pem",
  "Peers": [],
  "Listen": ["tls://0.0.0.0:9001"]
}
```

Spoke nodes peer to the hub’s address, for example:

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
| **[AgenC manifesto](docs/agenc.md)** | Vision, GStack bridge, bounty protocol JSON, roadmap, links |
| [Architecture](docs/architecture.md) | AXL components, data flow, wire format |
| [HTTP API](docs/api.md) | `/topology`, `/send`, `/recv`, `/mcp/`, `/a2a/` |
| [Configuration](docs/configuration.md) | Build, run, `node-config.json` |
| [Integrations](docs/integrations.md) | Python MCP router, A2A server |
| [Examples](docs/examples.md) | Remote MCP, A2A patterns |

---

## Philosophy

**AXL** keeps networking application-agnostic: separation between mesh transport and your agent logic enables many stacks—including AgenC’s bounty protocol—on the same P2P layer.

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
