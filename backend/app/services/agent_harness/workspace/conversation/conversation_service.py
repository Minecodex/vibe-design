"""Facade for HomeHarness conversation storage."""

from __future__ import annotations

from typing import Any, Callable

from . import transcript_store as _message
from . import conversation_meta_store as _meta
from . import workspace_preview_service as _preview

_write_json = _meta.write_json
_read_json = _meta.read_json

create_conversation = _meta.create_conversation
get_conversation = _meta.get_conversation
get_conversation_async = _meta.get_conversation_async
update_conversation = _meta.update_conversation
update_conversation_async = _meta.update_conversation_async
delete_conversation = _meta.delete_conversation
list_conversations = _meta.list_conversations
get_runtime_state = _meta.get_runtime_state
iter_running_conversation_refs = _meta.iter_running_conversation_refs
get_conversation_dir = _meta.get_conversation_dir

save_message = _message.save_message
append_message = _message.append_message
append_message_content_delta = _message.append_message_content_delta
iter_messages_reverse = _message.iter_messages_reverse
load_recent_messages = _message.load_recent_messages
load_messages_after_seq = _message.load_messages_after_seq
update_message = _message.update_message
load_messages = _message.load_messages
read_messages_page = _message.read_messages_page

list_workspace_files = _preview.list_workspace_files


def _call_preview_with_conversation_dir(
    preview_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    return preview_fn(*args, get_conversation_dir_fn=get_conversation_dir, **kwargs)


def get_workspace_file_path(user_id: int, conversation_id: str, file_path: str):
    return _call_preview_with_conversation_dir(
        _preview.get_workspace_file_path,
        user_id,
        conversation_id,
        file_path,
    )


def get_preview_workspace_file_path(user_id: int, conversation_id: str, file_path: str):
    return _call_preview_with_conversation_dir(
        _preview.get_preview_workspace_file_path,
        user_id,
        conversation_id,
        file_path,
    )


def create_html_bundle(user_id: int, conversation_id: str, file_path: str):
    return _call_preview_with_conversation_dir(
        _preview.create_html_bundle,
        user_id,
        conversation_id,
        file_path,
    )


def render_html_preview_document(user_id: int, conversation_id: str, file_path: str, *, preview_url_builder: callable):
    return _call_preview_with_conversation_dir(
        _preview.render_html_preview_document,
        user_id,
        conversation_id,
        file_path,
        preview_url_builder=preview_url_builder,
    )


def render_html_bundle_preview_document(
    user_id: int,
    conversation_id: str,
    file_id: str,
    version_id: str | None,
    *,
    preview_url_builder: callable,
    entry: str | None = None,
):
    return _call_preview_with_conversation_dir(
        _preview.render_html_bundle_preview_document,
        user_id,
        conversation_id,
        file_id,
        version_id,
        preview_url_builder=preview_url_builder,
        entry=entry,
    )


def render_css_preview_document(user_id: int, conversation_id: str, file_path: str, *, preview_url_builder: callable):
    return _call_preview_with_conversation_dir(
        _preview.render_css_preview_document,
        user_id,
        conversation_id,
        file_path,
        preview_url_builder=preview_url_builder,
    )


def _humanize_skill_id(skill_id: str | None) -> str:
    normalized = str(skill_id or "").strip()
    if not normalized:
        return ""
    return " ".join(part[:1].upper() + part[1:] for part in normalized.replace("_", "-").split("-") if part)


def build_auto_selection_announcement_message(
    *,
    previous_skill_id: str | None,
    next_skill_id: str | None,
    language: str | None = None,
) -> dict[str, Any] | None:
    normalized_next_skill_id = str(next_skill_id or "").strip() or None
    normalized_previous_skill_id = str(previous_skill_id or "").strip() or None
    if not normalized_next_skill_id or normalized_next_skill_id == normalized_previous_skill_id:
        return None

    skill_name = _humanize_skill_id(normalized_next_skill_id)
    if not skill_name:
        return None

    normalized_language = str(language or "").strip().lower()
    content = (
        f"已自动选择技能：{skill_name}。"
        if normalized_language.startswith("zh")
        else f"Automatically selected skill: {skill_name}."
    )
    return {
        "role": "assistant",
        "content": content,
        "metadata": {
            "source": "auto_selection_announcement",
            "selected_skill_id": normalized_next_skill_id,
            "previous_skill_id": normalized_previous_skill_id,
        },
    }


def build_internal_skill_activation_message(
    *,
    selected_skill_id: str | None,
    internal_skill_ids: list[str] | None,
    language: str | None = None,
) -> dict[str, Any] | None:
    normalized_selected_skill_id = str(selected_skill_id or "").strip() or None
    normalized_internal_skill_ids = [
        str(skill_id).strip()
        for skill_id in list(internal_skill_ids or [])
        if str(skill_id).strip()
    ]
    if not normalized_selected_skill_id or not normalized_internal_skill_ids:
        return None

    skill_names = [_humanize_skill_id(skill_id) for skill_id in normalized_internal_skill_ids]
    skill_names = [name for name in skill_names if name]
    if not skill_names:
        return None

    normalized_language = str(language or "").strip().lower()
    delimiter = "、" if normalized_language.startswith("zh") else ", "
    content = (
        f"已加载内部技能：{delimiter.join(skill_names)}。"
        if normalized_language.startswith("zh")
        else f"Loaded internal skills: {delimiter.join(skill_names)}."
    )
    return {
        "role": "assistant",
        "content": content,
        "metadata": {
            "message_kind": "internal_audit_note",
            "source": "internal_hidden_skill_activation",
            "selected_skill_id": normalized_selected_skill_id,
            "internal_skill_ids": normalized_internal_skill_ids,
        },
    }


def persist_auto_selection_announcement(
    user_id: int,
    conversation_id: str,
    *,
    previous_skill_id: str | None,
    next_skill_id: str | None,
    language: str | None = None,
) -> dict[str, Any] | None:
    message = build_auto_selection_announcement_message(
        previous_skill_id=previous_skill_id,
        next_skill_id=next_skill_id,
        language=language,
    )
    if not message:
        return None
    return append_message(
        user_id,
        conversation_id,
        message,
    )


__all__ = [
    "_read_json",
    "_write_json",
    "create_conversation",
    "create_html_bundle",
    "delete_conversation",
    "append_message",
    "append_message_content_delta",
    "build_auto_selection_announcement_message",
    "build_internal_skill_activation_message",
    "get_conversation",
    "get_conversation_dir",
    "get_preview_workspace_file_path",
    "get_runtime_state",
    "get_workspace_file_path",
    "iter_messages_reverse",
    "iter_running_conversation_refs",
    "list_conversations",
    "list_workspace_files",
    "load_recent_messages",
    "load_messages",
    "read_messages_page",
    "persist_auto_selection_announcement",
    "render_css_preview_document",
    "render_html_bundle_preview_document",
    "render_html_preview_document",
    "save_message",
    "update_message",
    "update_conversation",
]
