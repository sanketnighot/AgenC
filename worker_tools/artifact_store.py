"""On-disk bounty artifacts: embed PNGs for COMPLETED_BOUNTY and merge worker groups."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worker_tools.base import ToolContext

logger = logging.getLogger(__name__)

# Align with bridge supplemental merge caps where relevant; worker-side merge defaults
# match legacy worker_image_merge.py.
MAX_MERGE_IMAGES = 8
MAX_MERGE_TOTAL_BYTES = 4_500_000

DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "images"


@dataclass
class TaskOutput:
    """Final worker text plus optional inline images for the bridge UI."""

    text: str
    images: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ArtifactStore:
    """Harvest tool-written files under artifacts_dir/<bounty_id>/ and embed as payloads."""

    artifacts_dir: Path

    def harvest(self, ctx: ToolContext, bounty_id: str | None) -> None:
        """Attach any PNGs already saved under artifacts_dir/<bounty_id>/."""
        if not bounty_id:
            return
        root = self.artifacts_dir / bounty_id.replace("/", "_")
        if not root.is_dir():
            return
        for p in sorted(root.glob("*.png")):
            ps = str(p.resolve())
            if ps not in ctx.artifact_paths:
                ctx.artifact_paths.append(ps)

    def images_from_paths(
        self,
        paths: list[str],
        *,
        max_images: int = 4,
        max_total_bytes: int = MAX_MERGE_TOTAL_BYTES,
    ) -> list[dict[str, str]]:
        """Encode images from disk paths into bounty payload dicts."""
        out: list[dict[str, str]] = []
        total = 0
        seen: set[str] = set()
        for p in paths:
            if len(out) >= max_images:
                break
            if p in seen:
                continue
            seen.add(p)
            path = Path(p)
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if total + len(raw) > max_total_bytes:
                logger.warning(
                    "Skipping image %s: would exceed bounty image budget (%s bytes)",
                    path.name,
                    max_total_bytes,
                )
                break
            total += len(raw)
            suffix = path.suffix.lower()
            mime = "image/png"
            if suffix in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif suffix == ".webp":
                mime = "image/webp"
            elif suffix == ".gif":
                mime = "image/gif"
            out.append(
                {"mime": mime, "data_base64": base64.b64encode(raw).decode("ascii")}
            )
        return out

    def embed_with_retry(
        self,
        ctx: ToolContext,
        *,
        attempts: int = 80,
        delay_sec: float = 0.25,
    ) -> list[dict[str, str]]:
        """Poll disk briefly — artifact write may lag behind tool return."""
        for _ in range(attempts):
            imgs = self.images_from_paths(ctx.artifact_paths)
            if imgs:
                return imgs
            if not ctx.artifact_paths:
                break
            time.sleep(delay_sec)
        return self.images_from_paths(ctx.artifact_paths)

    def finalize(
        self, text: str, ctx: ToolContext, bounty_id: str | None
    ) -> TaskOutput:
        self.harvest(ctx, bounty_id)
        imgs = self.embed_with_retry(ctx)
        return TaskOutput(text=text, images=imgs)

    def from_timeout(
        self, ctx: ToolContext, bounty_id: str | None, message: str
    ) -> TaskOutput:
        """Recover on-disk images after asyncio.TimeoutError."""
        self.harvest(ctx, bounty_id)
        imgs = self.embed_with_retry(ctx, attempts=120, delay_sec=0.25)
        if imgs:
            logger.warning(
                "[timeout] recovered %s on-disk image(s) for bounty %s",
                len(imgs),
                bounty_id,
            )
            text = (
                f"{message}\n\n"
                "(A partial image was recovered from the worker after the run timed out.)"
            )
            return TaskOutput(text=text, images=imgs)
        return TaskOutput(text=message, images=[])

    @staticmethod
    def merge_groups(
        *groups: list[dict[str, str]],
        max_images: int = MAX_MERGE_IMAGES,
        max_total_bytes: int = MAX_MERGE_TOTAL_BYTES,
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
                        "merge_groups: stopping — budget exceeded (%s bytes)",
                        max_total_bytes,
                    )
                    return out
                total += raw_len
                mime = img.get("mime") if isinstance(img.get("mime"), str) else "image/png"
                out.append({"mime": mime, "data_base64": db})
        return out


DEFAULT_STORE = ArtifactStore(DEFAULT_ARTIFACTS_DIR)


def merge_bounty_images(
    *groups: list[dict[str, str]],
    max_images: int = MAX_MERGE_IMAGES,
    max_total_bytes: int = MAX_MERGE_TOTAL_BYTES,
) -> list[dict[str, str]]:
    """Backward-compatible name for collaboration merge (worker1/worker2)."""
    return ArtifactStore.merge_groups(*groups, max_images=max_images, max_total_bytes=max_total_bytes)
