"""Tool specifications and execution context for worker agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

JsonDict = dict[str, Any]

# Maximum JSON-serialized tool output passed back to the LLM (characters).
MAX_TOOL_RESULT_CHARS = 24_000


@dataclass
class ToolContext:
    """Per-invocation context (never log secrets)."""

    node_key: str
    bounty_id: str | None
    stream_id: str | None = None
    worker_api_base: str = ""  # e.g. http://127.0.0.1:8002 — for MCP HTTP calls via local node


@dataclass
class ToolResult:
    ok: bool
    data: JsonDict = field(default_factory=dict)
    error: str | None = None

    def as_json_text(self) -> str:
        payload = {"ok": self.ok, "data": self.data}
        if self.error:
            payload["error"] = self.error
        s = json.dumps(payload, ensure_ascii=False)
        if len(s) > MAX_TOOL_RESULT_CHARS:
            s = s[: MAX_TOOL_RESULT_CHARS - 80] + "\n…[truncated]"
        return s


ToolHandler = Callable[[JsonDict, ToolContext], ToolResult]


@dataclass
class ToolSpec:
    """Maps to OpenAI Chat Completions `tools[].function` schema."""

    name: str
    description: str
    parameters: JsonDict
    handler: ToolHandler

    def openai_tool_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
