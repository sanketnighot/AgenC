"""Tests for bounty FSM persistence helpers."""

import json
from pathlib import Path

from bounty_fsm import BountyFSM


def test_merge_image_payloads_dedupes(tmp_path: Path):
    a = [{"mime": "image/png", "data_base64": "AAA" * 100}]
    b = [{"mime": "image/png", "data_base64": "AAA" * 100}]  # same prefix → dedupe
    c = [{"mime": "image/png", "data_base64": "BBB" * 100}]
    out = BountyFSM.merge_image_payloads(a, b + c, max_images=12)
    assert len(out) == 2


def test_load_migrates_claimed_to_executing(tmp_path: Path):
    p = tmp_path / "b.json"
    p.write_text(
        json.dumps(
            {"abc12345": {"status": "CLAIMED", "task": "t", "reward": "1"}},
        ),
    )
    fsm = BountyFSM(str(p))
    fsm.load()
    assert fsm.bounties["abc12345"]["status"] == "EXECUTING"


def test_save_roundtrip(tmp_path: Path):
    p = tmp_path / "round.json"
    fsm = BountyFSM(str(p))
    fsm.bounties["x"] = {"status": "PENDING", "task": "hi"}
    fsm.save()
    fsm2 = BountyFSM(str(p))
    fsm2.load()
    assert fsm2.bounties["x"]["task"] == "hi"
