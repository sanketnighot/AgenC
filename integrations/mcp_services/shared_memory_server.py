"""Minimal MCP HTTP server: scoped key/value scratchpad shared between agents."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import threading
import time
from typing import Any

from aiohttp import web

from mcp_services.registration import deregister_service, register_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# key -> (expires_unix, value_str)
_STORE: dict[str, tuple[float, str]] = {}

DEFAULT_TTL_SEC = float(os.environ.get("SHARED_MEMORY_TTL_SEC", "86400"))


def _purge_locked(now: float) -> None:
    dead = [k for k, (exp, _) in _STORE.items() if exp < now]
    for k in dead:
        _STORE.pop(k, None)


def memory_put(scope: str, key: str, value: str, ttl_sec: float | None = None) -> dict[str, Any]:
    ttl = float(ttl_sec if ttl_sec is not None else DEFAULT_TTL_SEC)
    sk = f"{scope.strip()}::{key.strip()}"
    with _LOCK:
        _purge_locked(time.time())
        _STORE[sk] = (time.time() + max(60.0, ttl), value[:200_000])
    return {"ok": True, "key": sk, "ttl_sec": ttl}


def memory_get(scope: str, key: str) -> dict[str, Any]:
    sk = f"{scope.strip()}::{key.strip()}"
    with _LOCK:
        _purge_locked(time.time())
        row = _STORE.get(sk)
        if not row:
            return {"ok": False, "error": "not found"}
        exp, val = row
        if exp < time.time():
            _STORE.pop(sk, None)
            return {"ok": False, "error": "expired"}
        return {"ok": True, "value": val}


def memory_list(scope: str) -> dict[str, Any]:
    prefix = f"{scope.strip()}::"
    with _LOCK:
        _purge_locked(time.time())
        keys = [k.split("::", 1)[1] for k in _STORE if k.startswith(prefix)]
    return {"ok": True, "keys": sorted(keys)[:200]}


async def handle_mcp(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status=400,
        )

    rpc_id = body.get("id")
    method = body.get("method")

    if method == "initialize":
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "shared-memory", "version": "0.1.0"},
                },
            }
        )

    if method == "notifications/initialized":
        return web.Response(status=204)

    if method == "tools/list":
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "tools": [
                        {
                            "name": "memory_put",
                            "description": "Store text under a scope (e.g. bounty id) and key.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "scope": {"type": "string"},
                                    "key": {"type": "string"},
                                    "value": {"type": "string"},
                                    "ttl_sec": {"type": "number"},
                                },
                                "required": ["scope", "key", "value"],
                            },
                        },
                        {
                            "name": "memory_get",
                            "description": "Retrieve text by scope and key.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "scope": {"type": "string"},
                                    "key": {"type": "string"},
                                },
                                "required": ["scope", "key"],
                            },
                        },
                        {
                            "name": "memory_list",
                            "description": "List keys for a scope.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"scope": {"type": "string"}},
                                "required": ["scope"],
                            },
                        },
                    ]
                },
            }
        )

    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        text_out = ""
        if name == "memory_put":
            out = memory_put(
                str(arguments.get("scope", "")),
                str(arguments.get("key", "")),
                str(arguments.get("value", "")),
                arguments.get("ttl_sec"),
            )
            text_out = json.dumps(out, ensure_ascii=False)
        elif name == "memory_get":
            out = memory_get(str(arguments.get("scope", "")), str(arguments.get("key", "")))
            text_out = json.dumps(out, ensure_ascii=False)
        elif name == "memory_list":
            out = memory_list(str(arguments.get("scope", "")))
            text_out = json.dumps(out, ensure_ascii=False)
        else:
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"Unknown tool {name!r}"},
                }
            )
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": text_out}],
                    "isError": False,
                },
            }
        )

    return web.json_response(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    )


async def _run(args: argparse.Namespace) -> None:
    """Bind first, then register with router — avoids empty registry when bind fails."""
    endpoint = f"http://{args.host}:{args.port}/mcp"
    app = web.Application()
    app.router.add_post("/mcp", handle_mcp)

    async def cleanup(_app: web.Application) -> None:
        deregister_service("shared-memory", args.router)

    app.on_cleanup.append(cleanup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    try:
        await site.start()
    except OSError as exc:
        logger.error("bind failed on %s:%s: %s", args.host, args.port, exc)
        await runner.cleanup()
        raise SystemExit(1) from exc

    if not register_service("shared-memory", endpoint, args.router):
        logger.error("failed to register shared-memory with MCP router at %s", args.router)
        await runner.cleanup()
        raise SystemExit(1)

    logger.info("shared-memory MCP listening on %s", endpoint)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    use_signals = True
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, RuntimeError, ValueError):
        use_signals = False

    try:
        if use_signals:
            await stop.wait()
        else:
            while True:
                await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SHARED_MEMORY_MCP_PORT", "9102")))
    parser.add_argument("--router", default=os.environ.get("MCP_ROUTER_URL", "http://127.0.0.1:9003"))
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
