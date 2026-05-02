"""On-chain worker reputation from BountyCompleted events (Base Sepolia)."""

from __future__ import annotations

import json
import logging
import os
import pathlib

from web3 import Web3

logger = logging.getLogger(__name__)

# lowercase eth_address → {completed: int, total_eth_wei: int}
_cache: dict[str, dict] = {}
_w3: Web3 | None = None


def _get_w3() -> Web3:
    global _w3
    if _w3 is None:
        rpc = os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
        _w3 = Web3(Web3.HTTPProvider(rpc))
    return _w3


def refresh_reputation() -> dict:
    """Fetch all BountyCompleted events; update and return _cache."""
    global _cache
    contract_addr_raw = os.environ.get("CONTRACT_ADDRESS", "")
    if not contract_addr_raw:
        return _cache
    try:
        w3 = _get_w3()
        abi_path = pathlib.Path(__file__).parent / "bounty_escrow_abi.json"
        abi = json.loads(abi_path.read_text())
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_addr_raw), abi=abi
        )
        events = contract.events.BountyCompleted().get_logs(
            from_block=0, to_block="latest"
        )
        fresh: dict[str, dict] = {}
        for evt in events:
            workers = evt["args"]["workers"]
            amounts = evt["args"]["amounts"]
            for addr, amt in zip(workers, amounts):
                key = addr.lower()
                if key not in fresh:
                    fresh[key] = {"completed": 0, "total_eth_wei": 0}
                fresh[key]["completed"] += 1
                fresh[key]["total_eth_wei"] += int(amt)
        _cache = fresh
    except Exception as e:
        logger.warning("reputation refresh failed: %s", e)
    return _cache


def get_cache() -> dict:
    return _cache
