"""Gemini image generation tool for the Creative Strategist worker."""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import requests

from worker_tools.base import ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "images"


def _api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def handle_gemini_generate_image(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """
    Generate an image from a text prompt via Gemini API (image-capable model).
    Saves PNG under ./artifacts/images/<bounty_id|misc>/.
    """
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(False, error="prompt is required")
    key = _api_key()
    if not key:
        return ToolResult(False, error="GEMINI_API_KEY not set")

    # Dedicated env var so chat LLM_MODEL / GEMINI_* defaults don't collide with image models.
    model = ("gemini-3.1-flash-image-preview").strip()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": float(args.get("temperature", 0.9)),
        },
    }
    try:
        r = requests.post(url, params={"key": key}, json=body, timeout=120)
        if r.status_code != 200:
            return ToolResult(
                False,
                {"body": r.text[:800]},
                error=f"Gemini HTTP {r.status_code}",
            )
        data = r.json()
    except Exception as e:
        return ToolResult(False, error=str(e))

    # Extract first inline image part
    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    image_b64 = None
    mime = "image/png"
    caption = ""
    for p in parts:
        if isinstance(p, dict):
            if "text" in p:
                caption += str(p.get("text", ""))
            inline = p.get("inlineData") or p.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                image_b64 = inline["data"]
                mime = inline.get("mimeType") or inline.get("mime_type") or mime

    if not image_b64:
        return ToolResult(
            False,
            {"raw_keys": list(data.keys())},
            error="No image in Gemini response (model may not support image output)",
        )

    try:
        raw = base64.b64decode(image_b64)
    except Exception as e:
        return ToolResult(False, error=f"base64 decode failed: {e}")

    scope = (ctx.bounty_id or "misc").replace("/", "_")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = ARTIFACTS_DIR / scope
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:12]}.png"
    path = out_dir / fname
    path.write_bytes(raw)
    path_str = str(path)
    ctx.artifact_paths.append(path_str)

    return ToolResult(
        True,
        data={
            "path": path_str,
            "mime": mime,
            "caption_hint": caption.strip()[:500],
            "prompt_excerpt": prompt[:200],
        },
    )


from worker_tools.base import ToolSpec

CREATIVE_LOCAL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="gemini_generate_image",
        description=(
            "Generate a brand/visual image from a text prompt using Google Gemini image "
            "generation. Returns a local file path under artifacts/ and a short caption hint."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed image prompt (style, mood, composition).",
                },
                "temperature": {
                    "type": "number",
                    "description": "Optional sampling temperature (default 0.9).",
                },
            },
            "required": ["prompt"],
        },
        handler=lambda a, c: handle_gemini_generate_image(a, c),
    ),
]
