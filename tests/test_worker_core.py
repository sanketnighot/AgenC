"""Tests for worker_core MessageRouter."""

import asyncio

import pytest

from worker_core import (
    MessageRouter,
    collab_share_from_payload,
    parse_claim_json,
    run_recv_loop,
)


def test_collab_share_normalizes():
    d = collab_share_from_payload({"result": "hi", "images": [{"x": 1}]})
    assert d["result"] == "hi"
    assert len(d["images"]) == 1


def test_parse_claim_json_extracts_embedded():
    raw = 'Sure: {"should_claim": true, "fit_score": 0.5}'
    d = parse_claim_json(raw)
    assert d.get("should_claim") is True


@pytest.mark.asyncio
async def test_router_award_future():
    r = MessageRouter()
    fut = r.register_decision("b1")
    assert r.dispatch("AWARD", "b1", {"type": "AWARD"})
    msg_type, payload = await asyncio.wait_for(fut, timeout=1)
    assert msg_type == "AWARD"


@pytest.mark.asyncio
async def test_run_recv_loop_spawns_new_bounty(monkeypatch):
    calls: list[tuple[str | None, dict]] = []

    async def handle_new_bounty(from_peer: str | None, payload: dict) -> None:
        calls.append((from_peer, payload))

    _recv_calls = 0

    def fake_axl_recv(worker_api: str):
        nonlocal _recv_calls
        if _recv_calls == 0:
            _recv_calls += 1
            return "peer_hex", {"type": "NEW_BOUNTY", "bounty_id": "x1", "task": "t"}
        return None, None

    monkeypatch.setattr(
        "worker_core.axl_recv",
        fake_axl_recv,
    )

    router = MessageRouter()

    async def short_loop() -> None:
        task = asyncio.create_task(
            run_recv_loop(router, "http://noop", handle_new_bounty, poll_sec=0.01),
        )
        await asyncio.sleep(0.06)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await short_loop()
    assert len(calls) >= 1
    assert calls[0][1]["bounty_id"] == "x1"
