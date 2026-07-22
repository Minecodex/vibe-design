"""Home Harness v2 session storage.

The v2 contract keeps the user-visible conversation history append-only and
serves list/detail views from small projections.
"""

from .service import (
    append_message,
    append_message_content_delta,
    create_conversation_files,
    delete_conversation,
    get_conversation,
    list_conversations,
    load_messages,
    message_count,
    patch_runtime_state,
    read_messages_page,
    read_ui_messages_page,
    upsert_workspace_asset,
    upsert_workspace_file,
    update_conversation,
    update_message,
)

__all__ = [
    "append_message",
    "append_message_content_delta",
    "create_conversation_files",
    "delete_conversation",
    "get_conversation",
    "list_conversations",
    "load_messages",
    "message_count",
    "patch_runtime_state",
    "read_messages_page",
    "read_ui_messages_page",
    "upsert_workspace_asset",
    "upsert_workspace_file",
    "update_conversation",
    "update_message",
]
