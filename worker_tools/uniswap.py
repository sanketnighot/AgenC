"""Market data + Uniswap V3 subgraph helpers for the Data Analyst worker."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from worker_tools.base import ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# The Graph hosted service is deprecated. Set THEGRAPH_API_KEY to use the decentralized network,
# or set UNISWAP_V3_SUBGRAPH_URL to override entirely.
_THEGRAPH_DECENTRAL_SUBGRAPH_ID = "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"


def _get_subgraph_url() -> str:
    if custom := os.environ.get("UNISWAP_V3_SUBGRAPH_URL"):
        return custom
    if api_key := os.environ.get("THEGRAPH_API_KEY"):
        return f"https://gateway.thegraph.com/api/{api_key}/subgraphs/id/{_THEGRAPH_DECENTRAL_SUBGRAPH_ID}"
    return ""

# Ethereum mainnet common tokens (lowercase hex address)
MAINNET_TOKENS: dict[str, str] = {
    "eth": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "weth": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "btc": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "wbtc": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "usdc": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "usdt": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "dai": "0x6b175474e89094c44da98b954eedeac495271d0f",
}

COINGECKO_IDS: dict[str, str] = {
    "btc": "bitcoin",
    "wbtc": "bitcoin",
    "eth": "ethereum",
    "weth": "ethereum",
    "usdc": "usd-coin",
    "usdt": "tether",
    "dai": "dai",
    "sol": "solana",
    "bnb": "binancecoin",
}


def _addr(sym_or_addr: str) -> str | None:
    s = sym_or_addr.strip()
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", s):
        return s.lower()
    key = s.lower().replace(" ", "")
    return MAINNET_TOKENS.get(key)


def _sorted_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a.lower() < b.lower() else (b, a)


def handle_market_price_usd(args: dict[str, Any], _ctx: ToolContext) -> ToolResult:
    """CoinGecko simple price for major symbols (free tier)."""
    symbols = args.get("symbols") or args.get("symbol")
    if isinstance(symbols, str):
        symbols = [symbols]
    if not isinstance(symbols, list) or not symbols:
        return ToolResult(False, error="symbols required (list or string)")

    ids = []
    for sym in symbols[:12]:
        sid = str(sym).strip().lower()
        cid = COINGECKO_IDS.get(sid, sid)
        ids.append(cid)
    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        r = requests.get(
            url,
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return ToolResult(False, error=f"CoinGecko HTTP {r.status_code}")
        data = r.json()
        return ToolResult(True, data=data)
    except Exception as e:
        return ToolResult(False, error=str(e))


def _subgraph_query(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    endpoint = _get_subgraph_url()
    if not endpoint:
        return {"errors": [{"message": (
            "Uniswap V3 subgraph not configured. "
            "Set THEGRAPH_API_KEY (free at thegraph.com) or UNISWAP_V3_SUBGRAPH_URL."
        )}]}
    try:
        r = requests.post(
            endpoint,
            json={"query": query, "variables": variables},
            timeout=20,
        )
        if r.status_code != 200:
            return {"errors": [{"message": f"HTTP {r.status_code}"}]}
        return r.json()
    except Exception as e:
        return {"errors": [{"message": str(e)}]}


def handle_uniswap_v3_pool_snapshot(args: dict[str, Any], _ctx: ToolContext) -> ToolResult:
    """
    Fetch top Uniswap V3 pools for a token pair on Ethereum mainnet via subgraph.
    """
    token_a = args.get("token_a") or args.get("tokenA")
    token_b = args.get("token_b") or args.get("tokenB")
    if not token_a or not token_b:
        return ToolResult(False, error="token_a and token_b required")

    a = _addr(str(token_a))
    b = _addr(str(token_b))
    if not a or not b:
        return ToolResult(
            False,
            error=f"unknown token(s): {token_a!r} / {token_b!r} — use ETH, USDC, WBTC, or 0x address",
        )

    t0, t1 = _sorted_pair(a, b)

    q = """
    query ($token0: String!, $token1: String!) {
      pools(
        first: 5
        orderBy: totalValueLockedUSD
        orderDirection: desc
        where: {
          token0_: { id: $token0 }
          token1_: { id: $token1 }
        }
      ) {
        id
        feeTier
        liquidity
        sqrtPrice
        totalValueLockedUSD
        volumeUSD
        token0 { id symbol decimals }
        token1 { id symbol decimals }
      }
    }
    """
    variables = {"token0": t0.lower(), "token1": t1.lower()}
    raw = _subgraph_query(q, variables)
    if raw.get("errors"):
        return ToolResult(False, data={"raw": raw}, error=str(raw["errors"]))
    pools = (raw.get("data") or {}).get("pools") or []
    return ToolResult(True, data={"pools": pools, "pair": {"token0": t0, "token1": t1}})


DATA_ANALYST_LOCAL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="market_price_usd",
        description=(
            "Fetch spot USD prices and optional 24h change for major crypto symbols "
            "(e.g. ETH, BTC, USDC) via CoinGecko."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbols": {
                    "description": "Ticker symbols like ETH, BTC, or CoinGecko id",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                }
            },
            "required": ["symbols"],
        },
        handler=lambda a, c: handle_market_price_usd(a, c),
    ),
    ToolSpec(
        name="uniswap_v3_pool_snapshot",
        description=(
            "Look up Uniswap V3 liquidity pools for a token pair on Ethereum mainnet "
            "(symbols ETH/USDC/WBTC or 40-char hex addresses). Returns TVL and volume fields."
        ),
        parameters={
            "type": "object",
            "properties": {
                "token_a": {"type": "string"},
                "token_b": {"type": "string"},
            },
            "required": ["token_a", "token_b"],
        },
        handler=lambda a, c: handle_uniswap_v3_pool_snapshot(a, c),
    ),
]
