"""POST /api/worker/telemetry auth and payload validation."""

import pytest
from starlette.testclient import TestClient

import config


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(config, "BRIDGE_TELEMETRY_SECRET", "test-secret-telemetry")
    from main import app

    return app


def test_telemetry_rejects_missing_secret_header(secret):
    client = TestClient(secret)
    res = client.post(
        "/api/worker/telemetry",
        json={
            "node_key": "worker_1",
            "stream_id": "s1",
            "phase": "execute",
            "delta": "hi",
            "done": False,
        },
    )
    assert res.status_code == 403


def test_telemetry_rejects_wrong_secret(secret):
    client = TestClient(secret)
    res = client.post(
        "/api/worker/telemetry",
        headers={"X-Telemetry-Secret": "wrong"},
        json={
            "node_key": "worker_1",
            "stream_id": "s1",
            "phase": "idle",
            "delta": "",
            "done": True,
        },
    )
    assert res.status_code == 403


def test_telemetry_rejects_unknown_node(secret):
    client = TestClient(secret)
    res = client.post(
        "/api/worker/telemetry",
        headers={"X-Telemetry-Secret": "test-secret-telemetry"},
        json={
            "node_key": "worker_99",
            "stream_id": "s1",
            "phase": "idle",
            "delta": "",
            "done": True,
        },
    )
    assert res.status_code == 400


def test_telemetry_invalid_phase(secret):
    client = TestClient(secret)
    res = client.post(
        "/api/worker/telemetry",
        headers={"X-Telemetry-Secret": "test-secret-telemetry"},
        json={
            "node_key": "worker_1",
            "stream_id": "s1",
            "phase": "not_a_phase",
            "delta": "x",
            "done": False,
        },
    )
    assert res.status_code == 422


def test_telemetry_ok(secret, monkeypatch):
    posted: list[tuple[str, dict]] = []

    async def capture(event: str, data: dict) -> None:
        posted.append((event, data))

    import main

    monkeypatch.setattr(main, "broadcast", capture)

    client = TestClient(secret)
    res = client.post(
        "/api/worker/telemetry",
        headers={"X-Telemetry-Secret": "test-secret-telemetry"},
        json={
            "node_key": "worker_2",
            "stream_id": "stream-abc",
            "phase": "evaluate_claim",
            "bounty_id": "deadbeef",
            "delta": "thinking token",
            "done": False,
        },
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    events = [e for e, _ in posted]
    assert "worker_llm_delta" in events
    assert "worker_phase" in events
    deltas = [d for e, d in posted if e == "worker_llm_delta"]
    assert deltas[0]["delta"] == "thinking token"
    assert deltas[0]["node_key"] == "worker_2"


def test_telemetry_status_enabled(secret):
    client = TestClient(secret)
    assert client.get("/api/telemetry/status").json() == {"enabled": True}


def test_telemetry_status_disabled(monkeypatch):
    monkeypatch.setattr(config, "BRIDGE_TELEMETRY_SECRET", "")
    from main import app

    client = TestClient(app)
    assert client.get("/api/telemetry/status").json() == {"enabled": False}


def test_telemetry_disabled_when_empty_secret(monkeypatch):
    monkeypatch.setattr(config, "BRIDGE_TELEMETRY_SECRET", "")
    import main

    client = TestClient(main.app)
    res = client.post(
        "/api/worker/telemetry",
        headers={"X-Telemetry-Secret": "anything"},
        json={
            "node_key": "worker_1",
            "stream_id": "s",
            "phase": "idle",
            "delta": "",
            "done": True,
        },
    )
    assert res.status_code == 503
