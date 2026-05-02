"""Assemble ToolSpec lists per worker persona (local + MCP proxy tools)."""

from __future__ import annotations

import json
import logging
import os

from worker_tools.base import ToolContext, ToolResult, ToolSpec
from worker_tools.gemini_image import CREATIVE_LOCAL_TOOLS
from worker_tools.mcp_proxy import _mcp_route_endpoint, mcp_tools_call
from worker_tools.uniswap import DATA_ANALYST_LOCAL_TOOLS

logger = logging.getLogger(__name__)


def _mcp_peer() -> str:
    return os.environ.get("MCP_SERVICE_PEER_ID", "").strip()


def _mcp_tools_enabled() -> bool:
    """MCP web-search / shared-memory when peer is set (mesh) or direct router URL is set."""
    return bool(_mcp_route_endpoint() or _mcp_peer())


def _mcp_can_invoke(ctx: ToolContext) -> bool:
    if _mcp_route_endpoint():
        return True
    return bool(_mcp_peer() and ctx.worker_api_base)


def _parse_mcp_response(data: dict) -> ToolResult:
    """Parse JSON-RPC body returned by local node `/mcp/{peer}/{service}`."""
    if not isinstance(data, dict):
        return ToolResult(False, error="invalid MCP response")
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            return ToolResult(False, error=err.get("message", str(err)))
        return ToolResult(False, error=str(err))
    res = data.get("result")
    if isinstance(res, dict):
        parts = res.get("content")
        if isinstance(parts, list):
            texts = []
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "text" and "text" in p:
                    texts.append(str(p["text"]))
            if texts:
                return ToolResult(True, data={"text": "\n".join(texts)})
        # Fallback: return whole result object
        return ToolResult(True, data={"result": res})
    return ToolResult(True, data={"raw": data})


def _handle_perplexity_web_search(args: dict, _ctx: ToolContext) -> ToolResult:
    """Search via Perplexity Sonar (grounded, synthesized results)."""
    import requests as _requests
    q = (args.get("query") or "").strip()
    if not q:
        return ToolResult(False, error="query is required")
    api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        return ToolResult(False, error="PERPLEXITY_API_KEY not set")
    try:
        r = _requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "sonar", "messages": [{"role": "user", "content": q}]},
            timeout=30,
        )
        if r.status_code != 200:
            return ToolResult(False, error=f"Perplexity HTTP {r.status_code}: {r.text[:300]}")
        content = r.json()["choices"][0]["message"]["content"]
        return ToolResult(True, data={"text": content})
    except Exception as e:
        return ToolResult(False, error=str(e))


def _handle_mcp_web_search(args: dict, ctx: ToolContext) -> ToolResult:
    q = (args.get("query") or "").strip()
    if not q:
        return ToolResult(False, error="query is required")
    peer = _mcp_peer()
    if not _mcp_can_invoke(ctx):
        return ToolResult(
            False,
            error="Set MCP_ROUTER_HTTP (direct router) or MCP_SERVICE_PEER_ID + worker API base",
        )
    raw = mcp_tools_call(
        ctx.worker_api_base,
        peer,
        "web-search",
        "web_search",
        {"query": q},
    )
    return _parse_mcp_response(raw)


def _handle_web_search(args: dict, ctx: ToolContext) -> ToolResult:
    """Use Perplexity Sonar if API key is set, otherwise fall back to MCP DuckDuckGo."""
    if os.environ.get("PERPLEXITY_API_KEY", "").strip():
        return _handle_perplexity_web_search(args, ctx)
    return _handle_mcp_web_search(args, ctx)


def _handle_mcp_memory_put(args: dict, ctx: ToolContext) -> ToolResult:
    scope = (args.get("scope") or ctx.bounty_id or "global").strip()
    key = (args.get("key") or "").strip()
    value = str(args.get("value", ""))
    if not key:
        return ToolResult(False, error="key is required")
    peer = _mcp_peer()
    if not _mcp_can_invoke(ctx):
        return ToolResult(False, error="MCP_ROUTER_HTTP or MCP_SERVICE_PEER_ID / worker API not configured")
    raw = mcp_tools_call(
        ctx.worker_api_base,
        peer,
        "shared-memory",
        "memory_put",
        {
            "scope": scope,
            "key": key,
            "value": value,
            "ttl_sec": args.get("ttl_sec"),
        },
    )
    return _parse_mcp_response(raw)


def _handle_mcp_memory_get(args: dict, ctx: ToolContext) -> ToolResult:
    scope = (args.get("scope") or ctx.bounty_id or "global").strip()
    key = (args.get("key") or "").strip()
    if not key:
        return ToolResult(False, error="key is required")
    peer = _mcp_peer()
    if not _mcp_can_invoke(ctx):
        return ToolResult(False, error="MCP_ROUTER_HTTP or MCP_SERVICE_PEER_ID / worker API not configured")
    raw = mcp_tools_call(
        ctx.worker_api_base,
        peer,
        "shared-memory",
        "memory_get",
        {"scope": scope, "key": key},
    )
    return _parse_mcp_response(raw)


def _handle_mcp_memory_list(args: dict, ctx: ToolContext) -> ToolResult:
    scope = (args.get("scope") or ctx.bounty_id or "global").strip()
    peer = _mcp_peer()
    if not _mcp_can_invoke(ctx):
        return ToolResult(False, error="MCP_ROUTER_HTTP or MCP_SERVICE_PEER_ID / worker API not configured")
    raw = mcp_tools_call(
        ctx.worker_api_base,
        peer,
        "shared-memory",
        "memory_list",
        {"scope": scope},
    )
    return _parse_mcp_response(raw)


def _mcp_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="web_search",
            description=(
                "Search the web for fresh facts, news, prices, or citations. "
                "Uses Perplexity Sonar when PERPLEXITY_API_KEY is set, otherwise DuckDuckGo via MCP."
            ),
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=lambda a, c: _handle_web_search(a, c),
        ),
        ToolSpec(
            name="shared_memory_put",
            description="Store intermediate JSON or text under a bounty-scoped scratchpad.",
            parameters={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "Usually bounty id; defaults to current bounty.",
                    },
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "ttl_sec": {"type": "number"},
                },
                "required": ["key", "value"],
            },
            handler=lambda a, c: _handle_mcp_memory_put(a, c),
        ),
        ToolSpec(
            name="shared_memory_get",
            description="Read a value from the scratchpad.",
            parameters={
                "type": "object",
                "properties": {
                    "scope": {"type": "string"},
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
            handler=lambda a, c: _handle_mcp_memory_get(a, c),
        ),
        ToolSpec(
            name="shared_memory_list",
            description="List scratchpad keys for a scope (defaults to current bounty).",
            parameters={
                "type": "object",
                "properties": {"scope": {"type": "string"}},
                "required": [],
            },
            handler=lambda a, c: _handle_mcp_memory_list(a, c),
        ),
    ]


def _perplexity_enabled() -> bool:
    return bool(os.environ.get("PERPLEXITY_API_KEY", "").strip())


def tools_for_data_analyst(worker_api_base: str) -> list[ToolSpec]:
    tools = list(DATA_ANALYST_LOCAL_TOOLS)
    if _mcp_tools_enabled() or _perplexity_enabled():
        tools.extend(_mcp_tool_specs())
    elif worker_api_base:
        logger.debug("MCP and Perplexity unset — web_search disabled")
    return tools


def tools_for_creative_strategist(worker_api_base: str) -> list[ToolSpec]:
    tools = list(CREATIVE_LOCAL_TOOLS)
    if _mcp_tools_enabled() or _perplexity_enabled():
        tools.extend(_mcp_tool_specs())
    return tools


def capability_manifest_for(role: str) -> dict:
    """Embedded into CLAIM JSON for bridge + arbiter."""
    if role == "data":
        ids = [t.name for t in DATA_ANALYST_LOCAL_TOOLS]
        classes = ["market_data", "defi", "price_feed"]
    else:
        ids = [t.name for t in CREATIVE_LOCAL_TOOLS]
        classes = ["image_generation", "creative"]
    if _mcp_tools_enabled() or _perplexity_enabled():
        ids.extend(["web_search", "shared_memory_put", "shared_memory_get", "shared_memory_list"])
        classes.extend(["web_search", "memory"])
    return {
        "tool_ids": ids,
        "tool_classes": sorted(set(classes)),
        "supports_artifact_output": role != "data",
    }
