"""Tests for collab_protocol."""

import pytest

from collab_protocol import ROLES, artifact_producer_for, collab_memory_hint, get_role


def test_get_role_creative():
    r = get_role("creative")
    assert r.non_lead_delay_sec == 20.0
    assert r.artifact_producer is True


def test_artifact_producer_for():
    assert artifact_producer_for("data") is False
    assert artifact_producer_for("creative") is True


def test_collab_memory_hint_non_empty():
    assert "eth_price" in collab_memory_hint("data")


def test_unknown_role_raises():
    with pytest.raises(KeyError):
        get_role("nope")


def test_roles_cover_manifest_keys():
    assert set(ROLES.keys()) == {"data", "creative"}
