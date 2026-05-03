"""Minimal MCP HTTP server: web search via DuckDuckGo instant answer API."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from typing import Any

import requests
from aiohttp import web

from mcp_services.registration import deregister_service, register_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def duckduckgo_search(query: str) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "empty query"}
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=12,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def format_search_result(j: dict[str, Any]) -> str:
    if j.get("error"):
        return f"Search error: {j['error']}"
    lines = []
    if j.get("Heading"):
        lines.append(j["Heading"])
    if j.get("AbstractText"):
        lines.append(j["AbstractText"])
    if j.get("AbstractURL"):
        lines.append(f"URL: {j['AbstractURL']}")
    for rt in (j.get("RelatedTopics") or [])[:5]:
        if isinstance(rt, dict) and "Text" in rt:
            lines.append(f"- {rt['Text']}")
    if not lines:
        lines.append("(no instant answer — try a more specific query)")
    return "\n".join(lines)


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
                    "serverInfo": {"name": "web-search", "version": "0.1.0"},
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
                            "name": "web_search",
                            "description": "Search the public web (DuckDuckGo instant answers + related topics).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Search query"},
                                },
                                "required": ["query"],
                            },
                        }
                    ]
                },
            }
        )

    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name != "web_search":
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"Unknown tool {name!r}"},
                }
            )
        query = arguments.get("query", "")
        raw = duckduckgo_search(str(query))
        text = format_search_result(raw)
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
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
    app["_mcp_registered"] = False
    app.router.add_post("/mcp", handle_mcp)

    async def cleanup(_app: web.Application) -> None:
        if _app.get("_mcp_registered"):
            deregister_service("web-search", args.router)

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

    if not register_service("web-search", endpoint, args.router):
        logger.error("failed to register web-search with MCP router at %s", args.router)
        await runner.cleanup()
        raise SystemExit(1)

    app["_mcp_registered"] = True

    logger.info("web-search MCP listening on %s", endpoint)

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
    parser.add_argument("--port", type=int, default=int(os.environ.get("WEB_SEARCH_MCP_PORT", "9101")))
    parser.add_argument("--router", default=os.environ.get("MCP_ROUTER_URL", "http://127.0.0.1:9003"))
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
