"""Authoritative bounty dict, locks, persistence, and image merge helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from typing import Any

logger = logging.getLogger(__name__)


class BountyFSM:
    """Mutable bounty store + per-bounty asyncio locks + JSON persistence."""

    __slots__ = ("save_path", "bounties", "_locks")

    def __init__(self, save_path: str) -> None:
        self.save_path = save_path
        self.bounties: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, bounty_id: str) -> asyncio.Lock:
        if bounty_id not in self._locks:
            self._locks[bounty_id] = asyncio.Lock()
        return self._locks[bounty_id]

    def save(self) -> None:
        try:
            pathlib.Path(self.save_path).write_text(
                json.dumps(self.bounties, default=str),
            )
        except Exception as e:
            logger.warning("bounty save failed: %s", e)

    def load(self) -> None:
        try:
            data = json.loads(pathlib.Path(self.save_path).read_text())
            if isinstance(data, dict):
                self.bounties.update(data)
        except Exception:
            pass
        # Migrate legacy persisted status (pre-EXECUTING vocabulary).
        for rec in self.bounties.values():
            if isinstance(rec, dict) and rec.get("status") == "CLAIMED":
                rec["status"] = "EXECUTING"

    def clear(self) -> None:
        self.bounties.clear()
        self._locks.clear()

    @staticmethod
    def merge_image_payloads(
        existing: list[Any],
        new_images: list[Any],
        *,
        max_images: int = 12,
    ) -> list[dict[str, Any]]:
        """Dedupe-merge bounty image dicts when a worker sends supplemental COMPLETED_BOUNTY."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for group in (existing, new_images):
            if not isinstance(group, list):
                continue
            for img in group:
                if len(out) >= max_images:
                    return out
                if not isinstance(img, dict):
                    continue
                db = img.get("data_base64")
                if not isinstance(db, str) or not db.strip():
                    continue
                key = db[:240]
                if key in seen:
                    continue
                seen.add(key)
                mime = img.get("mime") if isinstance(img.get("mime"), str) else "image/png"
                out.append({"mime": mime, "data_base64": db})
        return out
