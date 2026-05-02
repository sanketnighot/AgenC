"""Tests for worker_tools.artifact_store."""

import base64
from pathlib import Path

import pytest

from worker_tools.artifact_store import ArtifactStore, merge_bounty_images
from worker_tools.base import ToolContext


def test_merge_bounty_images_budget(tmp_path: Path):
    tiny = base64.b64encode(b"x").decode("ascii")
    big = base64.b64encode(b"y" * 100).decode("ascii")
    a = [{"mime": "image/png", "data_base64": tiny}]
    b = [{"mime": "image/png", "data_base64": big}]
    out = merge_bounty_images(a, b, max_images=10, max_total_bytes=50)
    assert len(out) >= 1


def test_merge_dedupes():
    s = base64.b64encode(b"hello-world").decode("ascii")
    g = [{"mime": "image/png", "data_base64": s}]
    out = merge_bounty_images(g, g)
    assert len(out) == 1


def test_finalize_reads_png(tmp_path: Path):
    root = tmp_path / "artifacts" / "images" / "bid123"
    root.mkdir(parents=True)
    png = root / "a.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    store = ArtifactStore(tmp_path / "artifacts" / "images")
    ctx = ToolContext(
        node_key="worker_2",
        bounty_id="bid123",
        stream_id=None,
        worker_api_base="http://127.0.0.1:8003",
    )
    out = store.finalize("done", ctx, "bid123")
    assert out.images
    assert "data_base64" in out.images[0]
