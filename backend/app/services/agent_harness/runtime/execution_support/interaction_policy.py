from __future__ import annotations

from typing import Any

HOME_INTERACTION_PROFILE = "home_blocking_preflight"
CANVAS_INTERACTION_PROFILE = "canvas_live_interaction"


def runtime_profile(conversation: dict[str, Any] | None) -> str:
    normalized = str((conversation or {}).get("runtime_profile") or "home").strip().lower() or "home"
    return normalized if normalized in {"home", "canvas"} else "home"


def interaction_profile(conversation: dict[str, Any] | None) -> str:
    return (
        CANVAS_INTERACTION_PROFILE
        if runtime_profile(conversation) == "canvas"
        else HOME_INTERACTION_PROFILE
    )


def allows_live_user_interaction(conversation: dict[str, Any] | None, *, phase: str) -> bool:
    if phase != "executing":
        return True
    return interaction_profile(conversation) == CANVAS_INTERACTION_PROFILE


def blocks_ask_user_tool(conversation: dict[str, Any] | None, *, phase: str) -> bool:
    return not allows_live_user_interaction(conversation, phase=phase)


def is_home_execution_interaction_blocked(conversation: dict[str, Any] | None, *, phase: str) -> bool:
    return phase == "executing" and interaction_profile(conversation) == HOME_INTERACTION_PROFILE


def required_ask_user_fields(raw_args: dict[str, Any] | None) -> list[str]:
    schema = (raw_args or {}).get("schema")
    if not isinstance(schema, dict):
        return []
    fields = schema.get("fields")
    if not isinstance(fields, list):
        return []
    required_fields: list[str] = []
    for item in fields:
        if not isinstance(item, dict) or not item.get("required"):
            continue
        field_id = str(item.get("id") or "").strip()
        if field_id:
            required_fields.append(field_id)
    return required_fields
