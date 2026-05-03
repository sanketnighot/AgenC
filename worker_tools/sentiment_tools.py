"""Sentiment-specific tools: Fear & Greed index, CoinGecko trending, social signals."""

from __future__ import annotations

import requests

from worker_tools.base import ToolContext, ToolResult, ToolSpec


def handle_fear_greed_index(args: dict, _ctx: ToolContext) -> ToolResult:
    """Fetch Crypto Fear & Greed Index from alternative.me (free, no key)."""
    days = min(int(args.get("days", 7)), 30)
    try:
        r = requests.get(
            f"https://api.alternative.me/fng/?limit={days}",
            timeout=10,
        )
        r.raise_for_status()
        entries = r.json().get("data", [])
        if not entries:
            return ToolResult(False, error="No data returned from Fear & Greed API")
        current = entries[0]
        history = [
            {
                "value": int(e["value"]),
                "classification": e["value_classification"],
                "timestamp": e["timestamp"],
            }
            for e in entries
        ]
        return ToolResult(
            True,
            data={
                "current_value": int(current["value"]),
                "current_classification": current["value_classification"],
                "interpretation": (
                    "0-24 = Extreme Fear, 25-49 = Fear, "
                    "50 = Neutral, 51-74 = Greed, 75-100 = Extreme Greed"
                ),
                "history": history,
            },
        )
    except Exception as e:
        return ToolResult(False, error=str(e))


def handle_crypto_trending(args: dict, _ctx: ToolContext) -> ToolResult:
    """Fetch trending coins from CoinGecko (free, no key). Returns top 7 trending by search volume."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers={"accept": "application/json"},
            timeout=12,
        )
        r.raise_for_status()
        coins = r.json().get("coins", [])
        result = []
        for item in coins[:7]:
            c = item.get("item", {})
            result.append(
                {
                    "name": c.get("name"),
                    "symbol": c.get("symbol"),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "score": c.get("score"),
                }
            )
        nfts = r.json().get("nfts", [])[:3]
        nft_result = [
            {"name": n.get("name"), "symbol": n.get("symbol"), "floor_price_eth": n.get("floor_price_in_native_currency")}
            for n in nfts
        ]
        return ToolResult(
            True,
            data={
                "trending_coins": result,
                "trending_nfts": nft_result,
                "source": "CoinGecko trending (last 24h search volume)",
            },
        )
    except Exception as e:
        return ToolResult(False, error=str(e))


def handle_global_market_overview(args: dict, _ctx: ToolContext) -> ToolResult:
    """Fetch global crypto market stats: total market cap, BTC dominance, volume."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers={"accept": "application/json"},
            timeout=12,
        )
        r.raise_for_status()
        d = r.json().get("data", {})
        return ToolResult(
            True,
            data={
                "total_market_cap_usd": d.get("total_market_cap", {}).get("usd"),
                "total_volume_24h_usd": d.get("total_volume", {}).get("usd"),
                "btc_dominance_pct": round(d.get("market_cap_percentage", {}).get("btc", 0), 2),
                "eth_dominance_pct": round(d.get("market_cap_percentage", {}).get("eth", 0), 2),
                "active_cryptocurrencies": d.get("active_cryptocurrencies"),
                "market_cap_change_24h_pct": d.get("market_cap_change_percentage_24h_usd"),
            },
        )
    except Exception as e:
        return ToolResult(False, error=str(e))


SENTIMENT_LOCAL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="fear_greed_index",
        description=(
            "Fetch the Crypto Fear & Greed Index (0-100 scale). "
            "Values under 25 = Extreme Fear, over 75 = Extreme Greed. "
            "Includes up to 30 days of history."
        ),
        parameters={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of historical days to return (max 30, default 7)",
                }
            },
            "required": [],
        },
        handler=lambda a, c: handle_fear_greed_index(a, c),
    ),
    ToolSpec(
        name="crypto_trending",
        description=(
            "Fetch the top 7 trending cryptocurrencies on CoinGecko in the last 24 hours "
            "by search volume. Also returns top trending NFT collections."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=lambda a, c: handle_crypto_trending(a, c),
    ),
    ToolSpec(
        name="global_market_overview",
        description=(
            "Fetch global crypto market statistics: total market cap, 24h volume, "
            "BTC dominance %, ETH dominance %, and 24h market cap change %."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=lambda a, c: handle_global_market_overview(a, c),
    ),
]
