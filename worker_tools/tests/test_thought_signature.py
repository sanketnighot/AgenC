"""Gemini OpenAI-compat: thought_signature must round-trip on tool_calls."""

from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
)

from worker_tools.runtime import _assistant_message_for_history


def test_assistant_history_preserves_extra_content_on_tool_calls():
    tc = ChatCompletionMessageFunctionToolCall.model_validate(
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "market_price_usd", "arguments": '{"symbols":["eth"]}'},
            "extra_content": {"google": {"thought_signature": "sig-token"}},
        }
    )
    msg = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[tc],
    )
    wire = _assistant_message_for_history(msg)
    assert wire["role"] == "assistant"
    assert len(wire["tool_calls"]) == 1
    assert wire["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig-token"


def test_omit_null_extra_content_for_gemini_struct_validation():
    """Parallel tool calls may have extra_content: null; strip so Gemini does not 400."""
    from worker_tools.runtime import _omit_json_nulls

    msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "a",
                "extra_content": {"google": {"thought_signature": "x"}},
                "function": {"name": "f", "arguments": "{}"},
                "type": "function",
            },
            {
                "id": "b",
                "extra_content": None,
                "function": {"name": "g", "arguments": "{}"},
                "type": "function",
            },
        ],
    }
    cleaned = _omit_json_nulls(msg)
    assert "content" not in cleaned
    assert "extra_content" not in cleaned["tool_calls"][1]
    assert cleaned["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "x"
