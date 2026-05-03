"""Yield-specific tools: DeFiLlama yield pools, Aave market rates, protocol TVL."""

from __future__ import annotations

import requests

from worker_tools.base import ToolContext, ToolResult, ToolSpec

_DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
_DEFILLAMA_TVL_URL = "https://api.llama.fi/protocols"


def _fetch_llama_pools() -> list[dict]:
    r = requests.get(_DEFILLAMA_POOLS_URL, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def handle_defi_llama_yields(args: dict, _ctx: ToolContext) -> ToolResult:
    """
    Fetch top yield-bearing pools from DeFiLlama across all protocols and chains.
    Filters by chain and minimum TVL, sorts by APY descending.
    """
    chain = (args.get("chain") or "").strip()
    min_tvl = float(args.get("min_tvl_usd", 500_000))
    limit = min(int(args.get("limit", 15)), 30)
    stable_only = bool(args.get("stable_only", False))

    try:
        pools = _fetch_llama_pools()

        filtered = [
            p for p in pools
            if (not chain or p.get("chain", "").lower() == chain.lower())
            and float(p.get("tvlUsd") or 0) >= min_tvl
            and p.get("apy") is not None
            and float(p.get("apy") or 0) > 0
            and (not stable_only or p.get("stablecoin"))
        ]

        filtered.sort(key=lambda p: float(p.get("apy") or 0), reverse=True)
        top = filtered[:limit]

        result = [
            {
                "project": p.get("project"),
                "chain": p.get("chain"),
                "pool_symbol": p.get("symbol"),
                "tvl_usd": round(float(p.get("tvlUsd") or 0)),
                "apy_total": round(float(p.get("apy") or 0), 2),
                "apy_base": round(float(p.get("apyBase") or 0), 2),
                "apy_reward": round(float(p.get("apyReward") or 0), 2),
                "il_risk": p.get("ilRisk"),
                "stablecoin": bool(p.get("stablecoin")),
                "outlook": p.get("predictions", {}).get("predictedClass") if isinstance(p.get("predictions"), dict) else None,
            }
            for p in top
        ]
        return ToolResult(
            True,
            data={
                "pools": result,
                "total_matching": len(filtered),
                "filters": {"chain": chain or "all", "min_tvl_usd": min_tvl, "stable_only": stable_only},
            },
        )
    except Exception as e:
        return ToolResult(False, error=str(e))


def handle_aave_market_rates(args: dict, _ctx: ToolContext) -> ToolResult:
    """
    Fetch Aave V2/V3 supply APY rates for specific assets or all assets.
    Sourced from DeFiLlama yields (no API key needed).
    """
    asset_filter = (args.get("asset") or "").strip().upper()
    chain_filter = (args.get("chain") or "").strip().lower()

    try:
        pools = _fetch_llama_pools()

        aave_pools = [
            p for p in pools
            if "aave" in (p.get("project") or "").lower()
            and (not asset_filter or asset_filter in (p.get("symbol") or "").upper())
            and (not chain_filter or (p.get("chain") or "").lower() == chain_filter)
            and float(p.get("tvlUsd") or 0) > 100_000
        ]

        aave_pools.sort(key=lambda p: float(p.get("tvlUsd") or 0), reverse=True)
        top = aave_pools[:20]

        result = [
            {
                "project": p.get("project"),
                "chain": p.get("chain"),
                "asset": p.get("symbol"),
                "supply_apy": round(float(p.get("apy") or 0), 3),
                "tvl_usd": round(float(p.get("tvlUsd") or 0)),
                "stablecoin": bool(p.get("stablecoin")),
            }
            for p in top
        ]
        return ToolResult(True, data={"aave_markets": result, "count": len(result)})
    except Exception as e:
        return ToolResult(False, error=str(e))


def handle_protocol_tvl_ranking(args: dict, _ctx: ToolContext) -> ToolResult:
    """
    Fetch top DeFi protocols by TVL from DeFiLlama. Optionally filter by category.
    """
    category_filter = (args.get("category") or "").strip().lower()
    limit = min(int(args.get("limit", 15)), 30)

    try:
        r = requests.get(_DEFILLAMA_TVL_URL, timeout=20)
        r.raise_for_status()
        protocols = r.json()

        if category_filter:
            protocols = [
                p for p in protocols
                if category_filter in (p.get("category") or "").lower()
            ]

        protocols.sort(key=lambda p: float(p.get("tvl") or 0), reverse=True)
        top = protocols[:limit]

        result = [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "chain": p.get("chain"),
                "tvl_usd": round(float(p.get("tvl") or 0)),
                "change_1d_pct": p.get("change_1d"),
                "change_7d_pct": p.get("change_7d"),
            }
            for p in top
        ]
        return ToolResult(
            True,
            data={
                "protocols": result,
                "filter": category_filter or "all categories",
            },
        )
    except Exception as e:
        return ToolResult(False, error=str(e))


YIELD_SCOUT_LOCAL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="defi_llama_yields",
        description=(
            "Fetch top yield-bearing DeFi pools from DeFiLlama across all chains and protocols. "
            "Filter by chain (e.g. 'Ethereum', 'Base', 'Arbitrum'), minimum TVL, and stable_only. "
            "Returns APY (base + reward), TVL, impermanent loss risk, and AI outlook prediction."
        ),
        parameters={
            "type": "object",
            "properties": {
                "chain": {
                    "type": "string",
                    "description": "Chain name to filter (e.g. 'Ethereum', 'Base', 'Arbitrum'). Leave empty for all chains.",
                },
                "min_tvl_usd": {
                    "type": "number",
                    "description": "Minimum pool TVL in USD (default 500000)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max pools to return (default 15, max 30)",
                },
                "stable_only": {
                    "type": "boolean",
                    "description": "If true, only return stablecoin pools (lower IL risk)",
                },
            },
            "required": [],
        },
        handler=lambda a, c: handle_defi_llama_yields(a, c),
    ),
    ToolSpec(
        name="aave_market_rates",
        description=(
            "Fetch Aave V2/V3 supply APY rates from DeFiLlama for specific assets "
            "(e.g. 'USDC', 'ETH', 'WBTC') or all Aave markets. "
            "Optionally filter by chain (e.g. 'Ethereum', 'Polygon', 'Arbitrum')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "Token symbol to filter (e.g. USDC, ETH). Leave empty for all.",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain name to filter (e.g. Ethereum, Polygon).",
                },
            },
            "required": [],
        },
        handler=lambda a, c: handle_aave_market_rates(a, c),
    ),
    ToolSpec(
        name="protocol_tvl_ranking",
        description=(
            "Fetch top DeFi protocols ranked by Total Value Locked (TVL) from DeFiLlama. "
            "Optionally filter by category (e.g. 'dexes', 'lending', 'yield', 'liquid staking'). "
            "Returns TVL, 1d and 7d change percentages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Protocol category filter: dexes, lending, yield, liquid staking, bridge, etc.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max protocols to return (default 15, max 30)",
                },
            },
            "required": [],
        },
        handler=lambda a, c: handle_protocol_tvl_ranking(a, c),
    ),
]
