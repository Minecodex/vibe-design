from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.agent_harness.runtime.presentation_v2.protocol import PROTOCOL_VERSION


def build_session_detail_snapshot_payload(
    *,
    conversation: dict[str, Any],
    messages_page: dict[str, Any],
    workspace_files: list[dict[str, Any]],
    projection_state: dict[str, Any],
    latest_event_sequence: int,
    tail_limit: int,
) -> dict[str, Any]:
    """Build the session detail payload exposed to Canvas/Home.

    The event cursor intentionally uses the projection cursor, not the latest
    durable event sequence. That keeps refresh and SSE resume aligned when
    projection is temporarily behind the event log.
    """
    tail = messages_page.get("messages") if isinstance(messages_page.get("messages"), list) else []
    page_state = messages_page.get("messages_page") if isinstance(messages_page.get("messages_page"), dict) else {}
    applied_event_sequence = int(projection_state.get("applied_event_sequence") or 0)
    oldest_seq = page_state.get("oldest_seq")

    return {
        **conversation,
        "protocol_version": PROTOCOL_VERSION,
        "messages": [
            {key: deepcopy(value) for key, value in message.items() if not key.startswith("_")}
            for message in tail
            if isinstance(message, dict)
        ],
        "messages_page": {
            "has_more": bool(page_state.get("has_more")),
            "oldest_seq": oldest_seq,
            "limit": tail_limit,
        },
        "workspace_files": workspace_files,
        "projection": {
            "last_seq": max((int(message.get("_seq") or 0) for message in tail if isinstance(message, dict)), default=0),
            "event_last_sequence": applied_event_sequence,
            "applied_event_sequence": applied_event_sequence,
            "latest_observed_sequence": int(projection_state.get("latest_observed_sequence") or latest_event_sequence or 0),
            "status": projection_state.get("status") or "idle",
            "message_count": len(tail),
        },
        "event_stream": {
            "last_sequence": latest_event_sequence,
        },
    }
