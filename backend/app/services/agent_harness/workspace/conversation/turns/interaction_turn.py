from __future__ import annotations

from typing import Any

from .turn_payloads import conversation_web_search_enabled, payload_versioned


def prepare_resume_interaction_payload(
    *,
    conversation: dict[str, Any],
    request_id: str | None,
    answer: str | None,
    answers: dict[str, Any] | None,
    display_label: str | None,
    approved: bool | None,
    language: str,
) -> dict[str, Any]:
    return payload_versioned(
        {
            "request_id": request_id,
            "answer": answer,
            "answers": dict(answers or {}),
            "display_label": display_label,
            "approved": approved,
            "language": language,
            "web_search_enabled": conversation_web_search_enabled(conversation),
        }
    )

