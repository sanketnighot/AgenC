"""Bridge-only LLM arbiter: picks winner_node_key among CLAIM records with fallbacks."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

BRIDGE_PROVIDERS = {
    "openai": {
        "base_url": None,
        "api_key_env": "BRIDGE_OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "BRIDGE_GEMINI_API_KEY",
        "fallback_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "BRIDGE_OPENROUTER_API_KEY",
        "fallback_key_env": "OPENROUTER_API_KEY",
        "model": "openai/gpt-4o-mini",
    },
}


def _resolve_bridge_api_key(cfg: dict[str, Any]) -> str | None:
    primary = os.environ.get(cfg["api_key_env"])
    if primary:
        return primary
    fb = cfg.get("fallback_key_env")
    if fb:
        return os.environ.get(fb)
    return None


def _bridge_client() -> tuple[OpenAI, str]:
    provider = os.environ.get("BRIDGE_LLM_PROVIDER", "openai").strip().lower()
    if provider not in BRIDGE_PROVIDERS:
        raise ValueError(f"Unknown BRIDGE_LLM_PROVIDER={provider!r}")
    cfg = BRIDGE_PROVIDERS[provider]
    model = os.environ.get("BRIDGE_LLM_MODEL", cfg["model"]).strip()
    api_key = _resolve_bridge_api_key(cfg)
    if not api_key:
        hint = cfg["api_key_env"]
        if cfg.get("fallback_key_env"):
            hint = f"{hint} or {cfg['fallback_key_env']}"
        raise RuntimeError(
            f"Missing API key ({hint}) for BRIDGE_LLM_PROVIDER={provider}",
        )
    client = OpenAI(
        base_url=cfg["base_url"],
        api_key=api_key,
    )
    return client, model


@dataclass
class ArbiterOutcome:
    mode: str                              # "winner_take_all" | "collaborate"
    winner_node_key: str                   # primary winner / lead in collaborate mode
    collaborator_node_keys: list[str] = field(default_factory=list)  # all collaborators incl. lead; empty = winner_take_all
    reason: str = ""
    source: str = ""                       # "llm" | "fallback_fit_score" | "fallback_first_claim"


def _confidence_to_score(conf: str | None) -> float | None:
    if not conf:
        return None
    c = str(conf).strip().lower()
    if c == "high":
        return 0.85
    if c == "medium":
        return 0.55
    if c == "low":
        return 0.25
    return None


def normalize_fit_score(payload: dict[str, Any]) -> float:
    raw = payload.get("fit_score")
    if raw is None:
        alt = _confidence_to_score(payload.get("confidence"))
        return float(alt) if alt is not None else 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 0.0
    return max(0.0, min(1.0, v))


def fallback_winner(
    claims: list[dict[str, Any]],
    valid_node_keys: set[str],
) -> ArbiterOutcome:
    """Highest fit_score; tie-break earliest received_at; then lexicographic node_key."""
    if not claims:
        raise ValueError("empty claims")

    def sort_key(c: dict[str, Any]) -> tuple[float, float, str]:
        nk = c.get("node_key") or ""
        fs = float(c.get("fit_score") or 0.0)
        ra = float(c.get("received_at") or 0.0)
        return (-fs, ra, nk)

    ranked = sorted(
        [c for c in claims if c.get("node_key") in valid_node_keys],
        key=sort_key,
    )
    if not ranked:
        ranked = sorted(claims, key=sort_key)
    w = ranked[0]
    nk = w.get("node_key") or ""
    return ArbiterOutcome(
        mode="winner_take_all",
        winner_node_key=nk,
        collaborator_node_keys=[],
        reason="fallback: highest fit_score among claimants",
        source="fallback_fit_score",
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def select_winner_llm(
    task: str,
    reward: str,
    claims: list[dict[str, Any]],
    valid_node_keys: set[str],
) -> ArbiterOutcome | None:
    """Returns None on failure so caller can fallback."""
    try:
        client, model = _bridge_client()
    except Exception as e:
        logger.warning("Bridge LLM unavailable: %s", e)
        return None

    compact = []
    for c in claims:
        compact.append(
            {
                "node_key": c.get("node_key"),
                "specialty": c.get("specialty"),
                "fit_score": c.get("fit_score"),
                "claim_rationale": (c.get("claim_rationale") or "")[:400],
                "peer_short_id": (c.get("from_peer") or "")[:8],
            }
        )

    multiple_claimants = len(valid_node_keys) > 1
    collab_instruction = (
        " If multiple specialists have claimed and the task would genuinely benefit "
        "from both specialties working together, set mode to 'collaborate' and pick "
        "the best lead. If the task clearly fits only one specialty, use 'winner_take_all'."
        if multiple_claimants
        else " With only one claimant, always use 'winner_take_all'."
    )

    system = (
        "You are a neutral routing arbiter for agent bounties. "
        "Given a task and competing CLAIM entries, decide whether one agent should handle "
        "it alone (winner_take_all) or all specialists should collaborate (collaborate). "
        "Pick a winner_node_key from the provided list — this is the sole winner for "
        "winner_take_all, or the lead collaborator for collaborate mode. "
        "Respond with valid JSON only, no markdown: "
        '{"mode":"winner_take_all","winner_node_key":"<key>","reason":"<one sentence>"}' +
        collab_instruction
    )
    user = json.dumps(
        {
            "task": task[:8000],
            "reward": reward,
            "claimants": compact,
            "allowed_node_keys": sorted(valid_node_keys),
        },
        ensure_ascii=False,
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 200,
        "temperature": 0.2,
        "timeout": 45.0,
    }
    provider = os.environ.get("BRIDGE_LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        kwargs["response_format"] = {"type": "json_object"}

    content = ""
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()
            break
        except Exception as e:
            msg_l = str(e).lower()
            retryable = (
                "429" in msg_l
                or "rate" in msg_l
                or "resource exhausted" in msg_l
                or "503" in msg_l
                or "overloaded" in msg_l
            )
            if not retryable or attempt == 3:
                logger.warning("Arbiter LLM call failed: %s", e)
                return None
            delay = min(10.0, 1.5 * (2**attempt))
            logger.warning(
                "Arbiter LLM transient error (attempt %s); retry in %.1fs",
                attempt + 1,
                delay,
            )
            time.sleep(delay)

    data = _extract_json_object(content)
    if not data:
        logger.warning("Arbiter returned unparseable content")
        return None

    wk = data.get("winner_node_key")
    if not isinstance(wk, str) or wk not in valid_node_keys:
        logger.warning("Arbiter returned invalid winner_node_key %r", wk)
        return None

    mode = data.get("mode", "winner_take_all")
    if mode not in ("winner_take_all", "collaborate"):
        mode = "winner_take_all"

    reason = data.get("reason")
    if not isinstance(reason, str):
        reason = "selected by bridge arbiter"

    collaborator_node_keys = list(valid_node_keys) if mode == "collaborate" else []

    return ArbiterOutcome(
        mode=mode,
        winner_node_key=wk,
        collaborator_node_keys=collaborator_node_keys,
        reason=reason[:500],
        source="llm",
    )


def resolve_winner(
    task: str,
    reward: str,
    claims: list[dict[str, Any]],
    *,
    skip_llm_when_unanimous: bool,
) -> ArbiterOutcome:
    """Pick winner: optional skip LLM for single claimant, else LLM, else numeric fallback."""
    valid = {c["node_key"] for c in claims if c.get("node_key")}
    if not valid:
        raise ValueError("no valid node_key in claims")

    if len(valid) == 1 and skip_llm_when_unanimous:
        nk = next(iter(valid))
        return ArbiterOutcome(
            mode="winner_take_all",
            winner_node_key=nk,
            collaborator_node_keys=[],
            reason="single claimant (arbiter skipped)",
            source="fallback_fit_score",
        )

    llm = select_winner_llm(task, reward, claims, valid)
    if llm:
        return llm

    return fallback_winner(claims, valid)
