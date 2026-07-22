from __future__ import annotations

from typing import Any


def conversation_web_search_enabled(conversation: dict[str, Any]) -> bool:
    return bool(conversation.get("web_search_enabled", True))


def conversation_model_preferences(conversation: dict[str, Any]) -> dict[str, Any]:
    value = conversation.get("model_preferences")
    return dict(value) if isinstance(value, dict) else {}


def payload_versioned(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("payload_version", 1)
    return result

