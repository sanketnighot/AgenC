"""Lightweight tests for worker tool registry (no network)."""

from worker_tools.local_registry import capability_manifest_for, tools_for_data_analyst


def test_capability_manifest_keys():
    m = capability_manifest_for("data")
    assert "tool_ids" in m and "tool_classes" in m


def test_data_tools_without_mcp_peer(monkeypatch):
    monkeypatch.delenv("MCP_SERVICE_PEER_ID", raising=False)
    monkeypatch.delenv("MCP_ROUTER_HTTP", raising=False)
    tools = tools_for_data_analyst("http://127.0.0.1:8002")
    names = {t.name for t in tools}
    assert "market_price_usd" in names
    assert "web_search" not in names


def test_data_tools_with_mcp_peer(monkeypatch):
    monkeypatch.setenv("MCP_SERVICE_PEER_ID", "a" * 64)
    tools = tools_for_data_analyst("http://127.0.0.1:8002")
    names = {t.name for t in tools}
    assert "web_search" in names


def test_data_tools_with_direct_router_only(monkeypatch):
    monkeypatch.delenv("MCP_SERVICE_PEER_ID", raising=False)
    monkeypatch.setenv("MCP_ROUTER_HTTP", "http://127.0.0.1:9003")
    tools = tools_for_data_analyst("http://127.0.0.1:8002")
    names = {t.name for t in tools}
    assert "web_search" in names
