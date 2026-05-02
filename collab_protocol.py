"""Single source of truth for collaboration roles (memory keys, artifact flags, timing)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollaborationRole:
    """Maps manifest keys (`data` / `creative`) to collaboration behavior."""

    memory_writes: tuple[str, ...]
    memory_reads: tuple[str, ...]
    artifact_producer: bool
    lead_candidate: bool
    non_lead_delay_sec: float


ROLES: dict[str, CollaborationRole] = {
    "data": CollaborationRole(
        memory_writes=(
            "eth_price",
            "defi_tvl_data",
            "market_summary",
            "uniswap_pools",
            "research_summary",
        ),
        memory_reads=("research_summary", "strategy_brief"),
        artifact_producer=False,
        lead_candidate=True,
        non_lead_delay_sec=0.0,
    ),
    "creative": CollaborationRole(
        memory_writes=("research_summary", "strategy_brief"),
        memory_reads=(
            "eth_price",
            "defi_tvl_data",
            "market_summary",
            "uniswap_pools",
        ),
        artifact_producer=True,
        lead_candidate=False,
        non_lead_delay_sec=20.0,
    ),
}


def get_role(manifest_key: str) -> CollaborationRole:
    if manifest_key not in ROLES:
        raise KeyError(f"unknown collaboration manifest key {manifest_key!r}")
    return ROLES[manifest_key]


def artifact_producer_for(manifest_key: str) -> bool:
    return ROLES[manifest_key].artifact_producer


def collab_memory_hint(manifest_key: str) -> str:
    """Short line listing keys this role should write for peers."""
    r = ROLES[manifest_key]
    return ", ".join(r.memory_writes)


def collab_read_hint(manifest_key: str) -> str:
    """Keys this role should read from shared memory when synthesizing."""
    r = ROLES[manifest_key]
    return ", ".join(r.memory_reads)
