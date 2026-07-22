from __future__ import annotations

from typing import Any

from .turn_payloads import payload_versioned


def prepare_message_run_payload(
    *,
    content: str,
    attachments: list[dict[str, Any]],
    base_file_versions: list[dict[str, Any]],
    hidden_user_context: str,
    user_message_metadata: dict[str, Any],
    user_message_event: dict[str, Any] | None = None,
    language: str,
    web_search_enabled: bool,
    model_preferences: dict[str, Any],
    effective_artifact_mode: str | None,
    turn_route: dict[str, Any],
    skill_selection: dict[str, Any],
    canvas: dict[str, Any],
) -> dict[str, Any]:
    return payload_versioned(
        {
            "content": content,
            "attachments": list(attachments or []),
            "base_file_versions": list(base_file_versions or []),
            "hidden_user_context": hidden_user_context,
            "message_metadata": dict(user_message_metadata or {}),
            "user_message_event": dict(user_message_event or {}),
            "language": language,
            "web_search_enabled": web_search_enabled,
            "model_preferences": dict(model_preferences or {}),
            "effective_artifact_mode": effective_artifact_mode,
            "turn_route": dict(turn_route or {}),
            "activity": (turn_route or {}).get("activity"),
            "skill_selection": dict(skill_selection or {}),
            "canvas": dict(canvas or {}),
        }
    )

