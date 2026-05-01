"""Call MCP JSON-RPC services via the local AXL node HTTP `/mcp/{peer}/{service}` endpoint."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _mcp_route_endpoint() -> str:
    """
    Optional bypass for local dev: POST directly to the Python MCP router `/route`
    (same payload Go uses). Avoids mesh dial + remote peer hop that can hang until HTTP timeout.

    Env: MCP_ROUTER_HTTP=http://127.0.0.1:9003  (with or without trailing /route)
    """
    raw = os.environ.get("MCP_ROUTER_HTTP", "").strip()
    if not raw:
        return ""
    raw = raw.rstrip("/")
    if raw.endswith("/route"):
        return raw
    return f"{raw}/route"


_ROUTER_START_HINT = (
    "cd integrations && pip install -e . && mcp-router --port 9003 "
    "(then agenc-shared-memory-mcp and agenc-web-search-mcp in other terminals)"
)


def _mcp_via_router_http(
    route_url: str,
    service: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    """POST RouterRequest to integrations MCP router (internal/mcp RouterRequest JSON shape)."""
    jsonrpc = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    payload = {
        "service": service,
        "request": jsonrpc,
        "from_peer_id": os.environ.get("MCP_FROM_PEER_ID", "local"),
    }
    try:
        r = requests.post(route_url, json=payload, timeout=timeout)
        text = r.text[:2000] if r.text else ""
        try:
            wrap = r.json()
        except Exception:
            return {"error": f"HTTP {r.status_code}", "body": text[:500]}
        if r.status_code != 200:
            err = wrap.get("error") if isinstance(wrap, dict) else None
            return {"error": err or f"HTTP {r.status_code}", "body": text[:500]}
        if isinstance(wrap, dict) and wrap.get("error"):
            return {"error": str(wrap["error"])}
        inner = wrap.get("response") if isinstance(wrap, dict) else None
        if inner is None:
            return {"error": "router returned empty response"}
        if isinstance(inner, dict):
            return inner
        return {"result": inner}
    except requests.exceptions.ConnectionError as e:
        logger.warning(
            "mcp_direct_router connection refused or failed (%s). %s",
            e,
            _ROUTER_START_HINT,
        )
        return {
            "error": (
                f"MCP router not reachable at {route_url} (connection refused). "
                f"Start stack: {_ROUTER_START_HINT}"
            )
        }
    except Exception as e:
        logger.warning("mcp_direct_router failed: %s", e)
        return {"error": str(e)}


def mcp_tools_call(
    worker_api_base: str,
    peer_id: str,
    service: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout: float = 28.0,
) -> dict[str, Any]:
    """
    POST JSON-RPC `tools/call` to a registered MCP service.

    Default path: local AXL node ``POST {worker_api_base}/mcp/{peer_id}/{service}``
    (forwards over mesh to the peer that runs the MCP router).

    If ``MCP_ROUTER_HTTP`` is set, calls the Python MCP router ``/route`` directly
    (recommended on one machine when mesh MCP stalls).
    """
    route = _mcp_route_endpoint()
    if route:
        logger.debug("MCP via direct router: %s service=%s", route, service)
        return _mcp_via_router_http(route, service, tool_name, arguments, timeout=timeout)

    peer_id = peer_id.strip().lower()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    url = f"{worker_api_base.rstrip('/')}/mcp/{peer_id}/{service}"
    try:
        r = requests.post(url, json=body, timeout=timeout)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
        return r.json()
    except Exception as e:
        logger.warning("mcp_tools_call failed: %s", e)
        return {"error": str(e)}


def extract_mcp_tool_text(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize MCP tools/call JSON-RPC result into JSON-safe dict for LLM."""
    if "error" in result and result["error"]:
        return {"ok": False, "error": result["error"]}
    res = result.get("result") or result.get("response")
    if isinstance(res, dict):
        content = res.get("content")
        if isinstance(content, list) and content:
            parts = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
                elif isinstance(block, dict) and "type" in block:
                    parts.append(str(block))
            return {"ok": True, "text": "\n".join(parts), "raw": res}
        return {"ok": True, "result": res}
    return {"ok": True, "result": result}
