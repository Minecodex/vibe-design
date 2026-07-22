"""Simple token estimation for mixed CJK/English text."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 2 chars for mixed Chinese/English."""
    if not text:
        return 0
    return max(1, len(text) // 2)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens across a message list."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += estimate_tokens(part.get("text", ""))
        # Tool calls add overhead
        if msg.get("tool_calls"):
            import json
            total += estimate_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False))
    return total
