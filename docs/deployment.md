# AgenC deployment guide

This document describes how to run AgenC on a **server (e.g. Linux VPS)** with **systemd**, including the **MCP sidecars** workers use for `web-search` and `shared-memory`. Paths in the sample unit files under `deploy/` are **examples**; adjust `User`, `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` to match your install (common layouts: `/root/AgenC` or `/home/ubuntu/axl`).

For local development, you typically run processes by hand (see `README.md`). This guide focuses on **production-style** operation.

---

## 1. Architecture (ports)

| Component | Default port | Role |
|-----------|-------------|------|
| **MCP router** | `9003` | HTTP: `POST /route`, `POST /register`, `GET /services`, `GET /health` |
| **MCP web-search** (DuckDuckGo) | `9101` | Registers as service name `web-search` |
| **MCP shared-memory** (scratchpad) | `9102` | Registers as service name `shared-memory` |
| **FastAPI bridge** (`agenc-api`) | `8000` | REST + **SSE** (`/api/events`) for the dashboard |
| **Next.js frontend** | `3000` | Optional; often behind **nginx** (see `deploy/nginx.conf` example) |
| **Emitter AXL `node` HTTP API** | `8001` (typical) | Bridge calls `POST …/send` to reach workers; **not** the default 9002 from docs when using per-node configs |
| **Worker AXL `node` HTTP APIs** | `8002`–`8005` (typical) | One `node` per worker with its own `*-config.json` |
| **Go `node` defaults (single dev node)** | `9002` | See `docs/configuration.md` when you run one node only |

Workers resolve MCP tools through **`MCP_ROUTER_HTTP`** (e.g. `http://127.0.0.1:9003`) so the stack works without mesh-hopping to a peer MCP service.

---

## 2. Repository layout on the server

Expected checkout (example):

```text
/root/AgenC/
  .env                 # secrets + MCP_ROUTER_HTTP + peer overrides (from deploy/env.template)
  agenc-api/           # uvicorn bridge
  agenc-frontend/      # next build + start
  integrations/        # uv sync; MCP router + sidecars run from here
  worker1.py … worker4.py
  emitter-config.json / worker*-config.json   # AXL node configs (paths vary by setup)
```

Install Python deps:

```bash
cd /root/AgenC/integrations && uv sync
cd /root/AgenC/agenc-api && uv sync   # if using uv for the API
```

---

## 3. Environment file

Copy `deploy/env.template` to the repo root as `.env` and fill in:

- **`MCP_ROUTER_HTTP=http://127.0.0.1:9003`** — required for workers using MCP tools via the router.
- **`WORKER1_PEER_ID` … `WORKER4_PEER_ID`** (optional) — 64-char hex public keys from each worker node’s `GET /topology` so the UI **mesh “LIVE”** state matches (`curl -s http://127.0.0.1:8004/topology | jq -r .our_public_key`, etc.).
- **LLM keys**, **The Graph** key (Uniswap), **Gemini** (creative worker), **Base Sepolia** + escrow addresses if using on-chain escrow/reputation.

Systemd units reference **`EnvironmentFile=/root/AgenC/.env`** (change path if needed).

---

## 4. systemd units (`deploy/*.service`)

Shipped examples:

| Unit file | Purpose |
|-----------|---------|
| `mcp-router.service` | `uv run mcp-router --port 9003` from `integrations/` |
| `agenc-mcp-web-search.service` | `uv run agenc-web-search-mcp` on **9101**; `Requires=mcp-router.service` |
| `agenc-mcp-shared-memory.service` | `uv run agenc-shared-memory-mcp` on **9102**; same |
| `agenc-api.service` | `uv run uvicorn main:app` for `agenc-api` |
| `agenc-frontend.service` | `next start` (after `next build`) |
| `worker1.service` … `worker4.service` | `uv run python workerN.py` |
| `axl-worker3.service` / `axl-worker4.service` | Optional separate **`node`** processes for workers 3 & 4 |

**Install:**

```bash
sudo cp /path/to/AgenC/deploy/<unit>.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mcp-router.service
sudo systemctl enable --now agenc-mcp-web-search.service agenc-mcp-shared-memory.service
sudo systemctl enable --now agenc-api.service
# … workers, frontend, etc.
```

**Start order:** bring up **`mcp-router`** before the MCP sidecars (units use `After=` / `Requires=`). Workers list **`After=`** those units where applicable so tools are registered before heavy bounty traffic.

---

## 5. Verifying MCP registration

After sidecars are healthy:

```bash
curl -s http://127.0.0.1:9003/health | jq .
curl -s http://127.0.0.1:9003/services | jq .
```

You should see **`web-search`** and **`shared-memory`** with endpoints `http://127.0.0.1:9101/mcp` and `…9102/mcp`. An empty `{}` usually means sidecars crashed or could not bind (see troubleshooting).

---

## 6. Reverse proxy (optional)

`deploy/nginx.conf` is an **example**: TLS termination, proxy to `127.0.0.1:8000` for the API. For **SSE** (`/api/events`), disable buffering (`proxy_buffering off`, long `proxy_read_timeout`) so the dashboard streams live.

Point **`NEXT_PUBLIC_API_URL`** on the frontend at the public API URL if the browser talks to nginx, not localhost.

---

## 7. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| **`Service not found: shared-memory`** in UI/tools | Router `/services` empty — sidecars down or not registered |
| **`[Errno 98] address already in use`** on 9101/9102 | Another process (manual MCP run, zombie PID) holds the port — stop duplicates; units may use **`ExecStartPre`** with `fuser -k` on that port (see current `deploy/agenc-mcp-*.service`) |
| **`service_count: 0`** but processes “running” | Registration failed (router not ready); sidecars **retry** registration; ensure **`mcp-router`** starts first |
| **Mesh not “LIVE”** | Bridge `WORKERn_PEER_ID` does not match live **`/topology`** keys |

---

## 8. Related docs

| Doc | Contents |
|-----|----------|
| [`deploy/env.template`](../deploy/env.template) | Environment variable checklist |
| [`docs/integrations.md`](integrations.md) | MCP router API, AgenC sidecars |
| [`docs/agenc.md`](agenc.md) | Product protocol and stack overview |
| [`AGENTS.md`](../AGENTS.md) | Repo layout for contributors |
