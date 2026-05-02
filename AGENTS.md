# AGENTS.md

Read this first for **repository structure**, **AXL HTTP API**, and **build constraints**. For **AgenC product goals**, the **bounty protocol JSON**, **GStack bridge**, and **roadmap**, see **[`docs/agenc.md`](docs/agenc.md)**.

---

## What this repository is

1. **`AgenC`** — A P2P **agent bounty mesh** (emitters broadcast tasks; workers claim and return results) built on **[Gensyn AXL](https://www.gensyn.ai/axl)**. See [`docs/agenc.md`](docs/agenc.md).

2. **AXL Go `node`** — The **`node`** binary handles peering, encryption, routing, and exposes a **local HTTP API** (default `127.0.0.1:9002`). Apps and bridges talk only to this API, not to remote sockets.

The node payload layer is **application-agnostic** (raw bytes, JSON, etc.). AgenC uses a **convention** for JSON message `type`s (`NEW_BOUNTY`, `CLAIM`, `COMPLETED_BOUNTY`); implementations live in **FastAPI bridge + worker processes** and the **`agenc-frontend/`** dashboard, not enforced inside Go.

---

## Project layout

```
cmd/node/                 # Go entrypoint and ApiConfig overrides
api/                     # HTTP: send, recv, topology, mcp, a2a
internal/
  tcp/listen/            # Inbound TCP, multiplexer, Stream interface
  tcp/dial/              # Outbound peer dialing
  mcp/                   # MCP stream
  a2a/                   # A2A stream
integrations/            # Python: MCP router, A2A server
examples/python-client/  # Minimal send/recv example
agenc-frontend/          # Next.js AgenC UI (polls backend; see frontend README)
docs/                    # architecture, api, configuration, integrations, agenc.md
```

Expected **GStack bridge**: **FastAPI** (or equivalent) translating UI ↔ **`/send`**, **`/recv`**, **`/topology`**. The frontend in-repo currently calls **`http://127.0.0.1:8000/api/...`** — implement those routes on the bridge to match.

---

## How to interact with the AXL node

### Send data to a remote peer

```
POST http://127.0.0.1:9002/send
Header: X-Destination-Peer-Id: <64-char-hex-public-key>
Body: raw bytes (any format)
Response: 200 OK, X-Sent-Bytes header
```

Fire-and-forget: no response body from the remote peer on this endpoint.

### Receive data from remote peers

```
GET http://127.0.0.1:9002/recv
Response: 204 (empty) or 200 with raw body + X-From-Peer-Id header
```

Poll in a loop; each call **dequeues** one message.

### Discover peers

```
GET http://127.0.0.1:9002/topology
Response: JSON with our_ipv6, our_public_key, peers[], tree[]
```

### Protocol-specific endpoints (optional sidecars)

```
POST http://127.0.0.1:9002/mcp/{peer_id}/{service}   # JSON-RPC → remote MCP service
POST http://127.0.0.1:9002/a2a/{peer_id}              # JSON-RPC → remote A2A server
```

Request/response with ~30s timeout; requires `router_addr` / `a2a_addr` in config and Python processes in `integrations/`.

---

## Building on the node

### Minimal pattern: send/recv

1. Run `./node -config node-config.json`
2. `GET /topology` → share `our_public_key`
3. `POST /send` with peer id + payload
4. Poll `GET /recv`

Example: `examples/python-client/client.py`.

### Adding a new protocol/stream

Implement `Stream` in `internal/tcp/listen/stream.go`, register in `internal/tcp/listen/listener.go`, add HTTP in `api/` if needed. MCP/A2A use JSON discriminators (`service`, `a2a`). Unmatched messages go to **`/recv`**.

### Wire format

TCP payloads are length-prefixed: 4-byte big-endian **`uint32` length** + payload. Max size: `max_message_size` in `node-config.json` (helpers in `api/tcp_helpers.go`).

---

## Build and test

### Go

```bash
go build -o node ./cmd/node/
go test ./...
```

### Python integrations

```bash
cd integrations
pip install -e ".[test]"
pytest
```

### Frontend

```bash
cd agenc-frontend && bun install && bun dev
```

---

## Configuration (high level)

| Field | Default | Meaning |
|-------|---------|---------|
| `Peers` | `[]` | Yggdrasil peer URIs |
| `PrivateKeyPath` | _(none)_ | Persistent ed25519 key |
| `api_port` | `9002` | Local HTTP API |
| `tcp_port` | `7000` | gVisor listen port for inbound mesh TCP |
| `router_addr` / `a2a_addr` | empty | MCP / A2A sidecar hosts |
| `max_message_size` | `16777216` | Max bytes per message |

Full reference: `docs/configuration.md`.

---

## Key constraints

- **No direct P2P sockets from apps** — use the local HTTP API only.
- **Peer id = hex ed25519 public key** — not hostname/IP for API addressing.
- **`/send` is fire-and-forget** — use `/mcp/`, `/a2a/`, or app-level **`/recv`** correlation for replies.
- **`/recv` is an in-memory queue** — drain it or messages accumulate.
- **No offline store-and-forward** — remote peer must be reachable or dial fails.

---

## Canonical docs

| Topic | File |
|-------|------|
| AgenC bounty protocol, roadmap, FastAPI/UI stack | **`docs/agenc.md`** |
| AXL internals | `docs/architecture.md`, `docs/api.md` |

**Claude / other assistants:** **`CLAUDE.md`** at repo root defers here and to **`docs/agenc.md`**.
