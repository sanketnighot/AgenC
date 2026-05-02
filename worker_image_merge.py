"""Merge image payloads from multiple workers for COMPLETED_BOUNTY."""

from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)


def merge_bounty_images(
    *groups: list[dict[str, str]],
    max_images: int = 8,
    max_total_bytes: int = 4_500_000,
) -> list[dict[str, str]]:
    """Concatenate image dicts from lead + peers; dedupe and enforce size budget."""
    out: list[dict[str, str]] = []
    total = 0
    seen: set[str] = set()
    for group in groups:
        for img in group:
            if len(out) >= max_images:
                return out
            if not isinstance(img, dict):
                continue
            db = img.get("data_base64")
            if not isinstance(db, str) or not db.strip():
                continue
            key = db[:200]
            if key in seen:
                continue
            seen.add(key)
            try:
                raw = base64.b64decode(db, validate=True)
            except (ValueError, TypeError):
                continue
            raw_len = len(raw)
            if total + raw_len > max_total_bytes:
                logger.warning(
                    "merge_bounty_images: stopping — budget exceeded (%s bytes)",
                    max_total_bytes,
                )
                return out
            total += raw_len
            mime = img.get("mime") if isinstance(img.get("mime"), str) else "image/png"
            out.append({"mime": mime, "data_base64": db})
    return out
