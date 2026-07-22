"""Transcript store for HomeHarness model/internal conversation history.

V2 user-visible history is the presentation snapshot. This facade is for
model context, recall, and other non-display transcript records.
"""

from __future__ import annotations

from .conversation_message_store import (
    append_message,
    append_message_content_delta,
    iter_messages_reverse,
    load_messages_after_seq,
    load_recent_messages,
    load_messages,
    read_messages_page,
    save_message,
    update_message,
)

__all__ = [
    "append_message",
    "append_message_content_delta",
    "iter_messages_reverse",
    "load_messages_after_seq",
    "load_recent_messages",
    "load_messages",
    "read_messages_page",
    "save_message",
    "update_message",
]
