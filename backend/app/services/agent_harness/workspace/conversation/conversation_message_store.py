"""HomeHarness transcript facade backed by session_v2.

V2 user-visible messages are projected from conversation_events by the
presentation reducer. This facade is retained for internal/model transcript
records only.
"""

from __future__ import annotations

from typing import Any

from app.services.agent_harness.workspace.session_v2 import service as session_service

_UNSET = object()


def save_message(user_id: int, conversation_id: str, message: dict) -> dict[str, Any]:
    return session_service.append_message(user_id, conversation_id, message)


def append_message(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    return save_message(user_id, conversation_id, message)


def update_message(
    user_id: int,
    conversation_id: str,
    *,
    message_id: str,
    content: Any = _UNSET,
    blocks: Any = _UNSET,
    metadata: Any = _UNSET,
    streaming: Any = _UNSET,
) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {"message_id": message_id}
    if content is not _UNSET:
        kwargs["content"] = content
    if blocks is not _UNSET:
        kwargs["blocks"] = blocks
    if metadata is not _UNSET:
        kwargs["metadata"] = metadata
    if streaming is not _UNSET:
        kwargs["streaming"] = streaming
    return session_service.update_message(user_id, conversation_id, **kwargs)


def append_message_content_delta(
    user_id: int,
    conversation_id: str,
    *,
    message_id: str,
    delta: str,
) -> dict[str, Any] | None:
    return session_service.append_message_content_delta(
        user_id,
        conversation_id,
        message_id=message_id,
        delta=delta,
    )


def load_messages(user_id: int, conversation_id: str) -> list[dict]:
    return session_service.load_messages(user_id, conversation_id)


def load_messages_after_seq(user_id: int, conversation_id: str, *, after_seq: int) -> list[dict[str, Any]]:
    return session_service.load_messages_after_seq(user_id, conversation_id, after_seq=after_seq)


def read_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    return session_service.read_messages_page(
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
    )


def load_recent_messages(user_id: int, conversation_id: str, *, limit: int) -> list[dict]:
    return session_service.load_recent_messages(
        user_id,
        conversation_id,
        limit=limit,
    )


def iter_messages_reverse(
    user_id: int,
    conversation_id: str,
    *,
    page_size: int = 50,
    max_messages: int | None = None,
):
    yield from session_service.iter_messages_reverse(
        user_id,
        conversation_id,
        page_size=page_size,
        max_messages=max_messages,
    )
