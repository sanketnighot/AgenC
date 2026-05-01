---
name: Gensyn AXL Layer
description: Technical details of Gensyn AXL: P2P mesh, ed25519 identity, HTTP API, wire format, constraints
type: reference
---

## What AXL Is

Gensyn AXL (Agent eXchange Layer) is a decentralized P2P mesh for agent-to-agent communication. No central broker. Built on Yggdrasil (DHT routing) + gVisor (userspace TCP — no root/TUN needed).

Docs: https://docs.gensyn.ai/tech/agent-exchange-layer

## Identity

- **1 ed25519 keypair per node** → 64-char hex public key = peer ID
- Yggdrasil derives a unique IPv6 in `200::/7` from the public key
- Keys persist via PEM file (`PrivateKeyPath` config)

## HTTP API (local only, default 127.0.0.1:9002)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/send` | POST | Fire-and-forget to remote peer. Header: `X-Destination-Peer-Id`. Body: raw bytes. Response: 200 + `X-Sent-Bytes` |
| `/recv` | GET | Dequeue one message. 204=empty, 200=raw body + `X-From-Peer-Id` header |
| `/topology` | GET | JSON: `our_ipv6`, `our_public_key`, `peers[]`, `tree[]` |
| `/mcp/{peer_id}/{service}` | POST | JSON-RPC → remote MCP service (30s timeout) |
| `/a2a/{peer_id}` | POST | JSON-RPC → remote A2A server (30s timeout) |

## Wire Format

```
[4-byte big-endian uint32 length][payload bytes]
```

Multiplexer routing on inbound:
- `{"service":"...","request":{...}}` → MCP Router (port 9003)
- `{"a2a":true,"request":{...}}` → A2A Server (port 9004)
- Anything else → `/recv` queue (in-memory, capped at 100)

## Key Constraints

1. **No direct P2P sockets from apps** — only the local HTTP API
2. **`/send` is fire-and-forget** — no response from remote; use `/mcp/` or app-level `/recv` correlation for replies
3. **`/recv` is in-memory** — drain it or messages accumulate; capacity=100 in Go code
4. **No store-and-forward** — remote peer must be reachable or dial fails
5. **Peer = hex public key** — not hostname/IP

## Config Fields

| Field | Default | Meaning |
|-------|---------|---------|
| `PrivateKeyPath` | none | PEM key file for persistent identity |
| `Peers` | [] | Yggdrasil bootstrap peer URIs |
| `Listen` | [] | TLS listen addresses (e.g. `tls://127.0.0.1:9001`) |
| `api_port` | 9002 | Local HTTP API port |
| `tcp_port` | 7000 | gVisor TCP listen port |
| `max_message_size` | 16777216 | 16 MB max per message |

## Topology

Yggdrasil uses DHT — once connected to a bootstrap peer, it discovers others automatically. No central directory.
