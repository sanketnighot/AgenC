"""Unit tests for bounty arbiter fallbacks and normalization."""

import pytest

import arbiter as arbiter_mod

from arbiter import (
    BRIDGE_PROVIDERS,
    _resolve_bridge_api_key,
    fallback_winner,
    match_winner_node_key,
    normalize_fit_score,
    resolve_winner,
)


def test_resolve_bridge_api_key_gemini_falls_back_to_worker_env(monkeypatch):
    monkeypatch.delenv("BRIDGE_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "worker-gemini-key")
    assert _resolve_bridge_api_key(BRIDGE_PROVIDERS["gemini"]) == "worker-gemini-key"


def test_resolve_bridge_api_key_openrouter_falls_back_to_worker_env(monkeypatch):
    monkeypatch.delenv("BRIDGE_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "worker-or-key")
    assert _resolve_bridge_api_key(BRIDGE_PROVIDERS["openrouter"]) == "worker-or-key"


def test_normalize_fit_score_explicit():
    assert normalize_fit_score({"fit_score": 0.7}) == pytest.approx(0.7)


def test_normalize_fit_score_clamped():
    assert normalize_fit_score({"fit_score": 99}) == 1.0
    assert normalize_fit_score({"fit_score": -3}) == 0.0


def test_normalize_fit_score_confidence_fallback():
    assert normalize_fit_score({"confidence": "high"}) == pytest.approx(0.85)
    assert normalize_fit_score({"confidence": "low"}) == pytest.approx(0.25)


def test_fallback_winner_by_fit_score():
    claims = [
        {
            "from_peer": "aaa",
            "node_key": "worker_1",
            "specialty": "A",
            "fit_score": 0.3,
            "claim_rationale": "",
            "received_at": 10.0,
        },
        {
            "from_peer": "bbb",
            "node_key": "worker_2",
            "specialty": "B",
            "fit_score": 0.9,
            "claim_rationale": "",
            "received_at": 11.0,
        },
    ]
    out = fallback_winner(claims, {"worker_1", "worker_2"})
    assert out.winner_node_key == "worker_2"
    assert out.source == "fallback_fit_score"


def test_resolve_winner_skip_llm_single(monkeypatch):
    monkeypatch.delenv("BRIDGE_OPENAI_API_KEY", raising=False)
    claims = [
        {
            "from_peer": "aaa",
            "node_key": "worker_1",
            "specialty": "A",
            "fit_score": 0.5,
            "claim_rationale": "",
            "received_at": 1.0,
        },
    ]
    out = resolve_winner(
        "task",
        "1 USDC",
        claims,
        skip_llm_when_unanimous=True,
    )
    assert out.winner_node_key == "worker_1"


def test_match_winner_node_key_specialty_and_worker_alias():
    claims = [
        {"node_key": "worker_1", "specialty": "Data Analyst", "from_peer": "aa"},
        {"node_key": "worker_2", "specialty": "Creative Strategist", "from_peer": "bb"},
    ]
    valid = {"worker_1", "worker_2"}
    assert match_winner_node_key("Data Analyst", valid, claims) == "worker_1"
    assert match_winner_node_key("worker 1", valid, claims) == "worker_1"
    assert match_winner_node_key("WORKER_2", valid, claims) == "worker_2"


def test_match_winner_node_key_peer_prefix():
    fp = "7f735488b692e04fbb3071c4ad6a2774bd0ec3bb7b5508e09a0d00a31af0e5f4"
    claims = [{"node_key": "worker_1", "specialty": "A", "from_peer": fp}]
    assert match_winner_node_key(fp[:8], {"worker_1"}, claims) == "worker_1"


def test_resolve_winner_heuristic_collab_when_llm_missing(monkeypatch):
    monkeypatch.delenv("BRIDGE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BRIDGE_LLM_PROVIDER", "openai")
    task = (
        "Analyze Bitcoin's 5-year price volatility and write a compelling creative "
        "for a social media post."
    )
    claims = [
        {
            "from_peer": "aaa",
            "node_key": "worker_1",
            "specialty": "Data Analyst",
            "fit_score": 0.2,
            "claim_rationale": "",
            "received_at": 1.0,
        },
        {
            "from_peer": "bbb",
            "node_key": "worker_2",
            "specialty": "Creative Strategist",
            "fit_score": 0.95,
            "received_at": 2.0,
        },
    ]
    out = resolve_winner(task, "1 USDC", claims, skip_llm_when_unanimous=False)
    assert out.mode == "collaborate"
    assert out.source == "heuristic_collab"
    assert set(out.collaborator_node_keys) == {"worker_1", "worker_2"}
    assert out.winner_node_key == "worker_2"


def test_resolve_winner_heuristic_disabled_falls_back(monkeypatch):
    monkeypatch.setattr(arbiter_mod, "ARBITER_HEURISTIC_COLLAB", False)
    monkeypatch.delenv("BRIDGE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BRIDGE_LLM_PROVIDER", "openai")
    task = "Analyze Bitcoin volatility and write creative social media copy."
    claims = [
        {
            "from_peer": "aaa",
            "node_key": "worker_1",
            "specialty": "Data Analyst",
            "fit_score": 0.2,
            "received_at": 1.0,
        },
        {
            "from_peer": "bbb",
            "node_key": "worker_2",
            "specialty": "Creative Strategist",
            "fit_score": 0.9,
            "received_at": 2.0,
        },
    ]
    out = resolve_winner(task, "1 USDC", claims, skip_llm_when_unanimous=False)
    assert out.mode == "winner_take_all"
    assert out.source == "fallback_fit_score"
    assert out.winner_node_key == "worker_2"


def test_resolve_winner_fallback_when_llm_missing(monkeypatch):
    monkeypatch.delenv("BRIDGE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BRIDGE_LLM_PROVIDER", "openai")
    claims = [
        {
            "from_peer": "aaa",
            "node_key": "worker_1",
            "specialty": "A",
            "fit_score": 0.2,
            "claim_rationale": "",
            "received_at": 1.0,
        },
        {
            "from_peer": "bbb",
            "node_key": "worker_2",
            "specialty": "B",
            "fit_score": 0.95,
            "claim_rationale": "",
            "received_at": 2.0,
        },
    ]
    out = resolve_winner(
        "task",
        "1 USDC",
        claims,
        skip_llm_when_unanimous=False,
    )
    assert out.winner_node_key == "worker_2"
    assert out.source == "fallback_fit_score"
