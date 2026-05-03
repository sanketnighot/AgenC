# Integrations (Python)

The `integrations/` directory contains Python services that run alongside the Go node. The node handles network transport; these services handle application-level protocols.

```
integrations/
  mcp_routing/
    mcp_router.py           # MCP HTTP router (:9003)
  mcp_services/
    web_search_server.py    # agenc-web-search-mcp (:9101)
    shared_memory_server.py # agenc-shared-memory-mcp (:9102)
    registration.py         # POST /register with retries (router startup races)
  a2a_serving/
    a2a_server.py           # A2A protocol server (:9004)
  pyproject.toml
```

## Install

```bash
cd integrations
uv sync    # or: pip install -e .
```

## MCP Router

The router is a lightweight HTTP gateway that sits between the Yggdrasil P2P bridge and your MCP servers. It allows a single node to host any number of independent services: the bridge forwards every incoming MCP request to the router, which dispatches it to the correct backend by name. Apart from the registration and deregistration calls described below, the router is completely transparent to your server — it never changes request or response payloads.

Start the router before launching any MCP server:

```bash
uv run mcp-router --port 9003
# or: python -m mcp_routing.mcp_router --port 9003
```

Sidecar servers (**bind first**, then register) retry **`POST /register`** if the router is still starting (connection errors / 5xx). On shutdown they deregister only if registration succeeded.

Install **`psmisc`** on Linux if you use systemd **`fuser`** in `ExecStartPre` (see **`docs/deployment.md`**).

| Endpoint | Description |
|----------|-------------|
| `POST /route` | Forward a request to a registered service (called by the bridge) |
| `POST /register` | Register a service (`{"service": "...", "endpoint": "..."}`) |
| `DELETE /register/{service}` | Remove a service |
| `GET /services` | List registered services |
| `GET /health` | Router health check |

### Writing Your Own MCP Server

To make your server reachable over the Yggdrasil network you must:

1. **Start the router first.** The router must already be running when your server starts, because registration happens at server startup via an HTTP call.

2. **Register on startup.** Call `POST /register` with your service name and the full URL of your server's MCP endpoint:

   ```http
   POST http://127.0.0.1:9003/register
   Content-Type: application/json

   {
     "service": "my-service",
     "endpoint": "http://127.0.0.1:7100/mcp"
   }
   ```

   Until this call succeeds, the router has no record of your server and any incoming requests for it will return a 404.

3. **Deregister on shutdown.** When your server exits it should call `DELETE /register/{service}` to remove itself from the router's table cleanly:

   ```http
   DELETE http://127.0.0.1:9003/register/my-service
   ```

   This prevents the router from routing requests to a dead endpoint.

**Minimal Python example** (using `aiohttp`):

```python
import asyncio
from aiohttp import ClientSession, ClientTimeout

ROUTER_URL = "http://127.0.0.1:9003"
SERVICE_NAME = "my-service"
SERVICE_ENDPOINT = "http://127.0.0.1:7100/mcp"
_timeout = ClientTimeout(total=5)

async def register():
    async with ClientSession(timeout=_timeout) as s:
        async with s.post(
            f"{ROUTER_URL}/register",
            json={"service": SERVICE_NAME, "endpoint": SERVICE_ENDPOINT},
        ) as resp:
            resp.raise_for_status()

async def deregister():
    async with ClientSession(timeout=_timeout) as s:
        await s.delete(f"{ROUTER_URL}/register/{SERVICE_NAME}")

# In your startup/shutdown flow:
# asyncio.run(register())   # before accepting traffic
# ...
# asyncio.run(deregister()) # in a finally block on exit
```

## A2A Server

Exposes registered MCP services as [A2A](https://github.com/google/A2A) skills. Auto-discovers services from the router and advertises them at `/.well-known/agent-card.json`.

```bash
python -m a2a_serving.a2a_server --port 9004 --router http://127.0.0.1:9003
```

The a2a server may be reached across the Gensyn network using the peerId of the node running the server.  A `Get` will return the `/.well-known/agent-card.json` file, and a `POST` will route the request to the appropriate MCP service.
```HTTP
GET /a2a/<peerId>
```

```HTTP
POST /a2a/<peerId>
```

## A2A Test Client

Located at `examples/python-client/a2a_client.py`. Routes requests through the local Gensyn node to a remote peer's A2A server:

```bash
python examples/python-client/a2a_client.py \
  --peer-id <64-char-hex-public-key> \
  --service weather --method tools/list
```

## AgenC MCP sidecars (web search + shared memory)

For hackathon demos, you can run additional **MCP HTTP services** that register with the same **`mcp_router`** used by the Go node:

| Script (after `uv sync` or `pip install -e .` in `integrations/`) | Port (default) | Service name (for `POST /route` or `/mcp/{peer}/{service}`) |
|-------------------------------------------------------------------|----------------|---------------------------------------------------------------|
| `agenc-web-search-mcp` | 9101 | `web-search` |
| `agenc-shared-memory-mcp` | 9102 | `shared-memory` |

1. Start **`mcp-router`** on **9003** (see [MCP Router](#mcp-router) above).
2. Start the sidecars — they listen on **9101** / **9102**, then register.
3. Set **`MCP_ROUTER_HTTP=http://127.0.0.1:9003`** in the repo **`.env`** so workers use **`POST …/route`** (simplest for single-host / VPS).

   **Mesh path (optional):** set **`MCP_SERVICE_PEER_ID`** to the **64-char hex** public key of the node that should receive MCP traffic, and call via the local worker node: `POST http://127.0.0.1:<api_port>/mcp/{MCP_SERVICE_PEER_ID}/web-search`.

---

## Tests

```bash
cd integrations
pip install -e ".[test]"
pytest
```
