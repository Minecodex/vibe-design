from __future__ import annotations

import shutil
import uuid
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.message_visibility import assert_transcript_persistable_message
from app.services.agent_harness.workspace.conversation.conversation_store_support import (
    get_conversation_dir,
)

from . import db_store

TAIL_LIMIT = 80
_UNSET = object()
logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_id() -> str:
    return uuid.uuid4().hex[:8]


def _base_header(conversation: dict[str, Any]) -> dict[str, Any]:
    return dict(conversation)


def _ensure_conversation_workspace(conv_dir: Path) -> None:
    for subdir in (
        "project",
        "references/inputs",
        "references/sources",
        "references/generated",
        "skill",
        "published",
        ".agent",
        ".meta",
    ):
        (conv_dir / subdir).mkdir(parents=True, exist_ok=True)


def create_conversation_files(user_id: int, conversation: dict[str, Any]) -> dict[str, Any]:
    conversation_id = str(conversation["id"])
    runtime_profile = str(conversation.get("runtime_profile") or "home")
    project_id = conversation.get("project_id")
    conv_dir = get_conversation_dir(
        user_id,
        conversation_id,
        runtime_profile=runtime_profile,
        project_id=project_id,
    )
    stored = db_store.create_conversation_record(user_id, conversation, conv_dir)
    try:
        _ensure_conversation_workspace(conv_dir)
    except Exception:
        db_store.delete_conversation_record(user_id, conversation_id)
        raise
    return stored


def get_conversation(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    return db_store.get_conversation_record(user_id, conversation_id)


def update_conversation(user_id: int, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    return db_store.update_conversation_record(user_id, conversation_id, updates)


def delete_conversation(user_id: int, conversation_id: str) -> bool:
    current = get_conversation(user_id, conversation_id)
    runtime_profile = str((current or {}).get("runtime_profile") or "home")
    project_id = (current or {}).get("project_id")
    deleted = db_store.delete_conversation_record(user_id, conversation_id)
    if not deleted:
        return False
    conv_dir = get_conversation_dir(
        user_id,
        conversation_id,
        runtime_profile=runtime_profile,
        project_id=project_id,
    )
    if conv_dir.exists():
        shutil.rmtree(conv_dir, ignore_errors=True)
    return True


def list_conversations(
    user_id: int,
    *,
    runtime_profile: str = "home",
    project_id: int | None = None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    return db_store.list_conversation_records(
        user_id,
        runtime_profile=runtime_profile,
        project_id=project_id,
        page=page,
        page_size=page_size,
    )


def append_message(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    stored = sanitize_persistent_payload(deepcopy(message))
    assert_transcript_persistable_message(stored)
    _assert_direct_transcript_message_allowed(stored)
    stored.setdefault("id", _message_id())
    stored.setdefault("created_at", utc_now())
    stored.setdefault("role", str(stored.get("role") or "assistant"))
    result = db_store.append_message_record(user_id, conversation_id, stored)
    try:
        from app.services.agent_harness.runtime.recall_sidecar import append_message_to_recall_sidecar

        append_message_to_recall_sidecar(user_id, conversation_id, result)
    except Exception:
        pass
    return result


def normalize_message_id(message_id: str | None) -> str:
    return db_store.normalize_message_id(message_id)


def load_messages(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    return db_store.load_message_records(user_id, conversation_id)


def load_messages_after_seq(user_id: int, conversation_id: str, *, after_seq: int) -> list[dict[str, Any]]:
    return db_store.load_message_records_after_seq(user_id, conversation_id, after_seq=after_seq)


def message_count(user_id: int, conversation_id: str) -> int | None:
    return db_store.message_count(user_id, conversation_id)


def count_assistant_tool_calls_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    return db_store.count_assistant_tool_calls_by_name(user_id, conversation_id, tool_name)


def count_successful_tool_messages_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    return db_store.count_successful_tool_messages_by_name(user_id, conversation_id, tool_name)


def count_tool_messages_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    return db_store.count_tool_messages_by_name(user_id, conversation_id, tool_name)


def patch_runtime_state(
    user_id: int,
    conversation_id: str,
    updates: dict[str, Any],
    *,
    touch_updated_at: bool = True,
) -> dict[str, Any]:
    merged_updates = dict(updates)
    if touch_updated_at and "updated_at" not in merged_updates:
        merged_updates["updated_at"] = utc_now()
    updated = db_store.update_conversation_record(user_id, conversation_id, merged_updates)
    return dict(updated or {})


def upsert_workspace_file(user_id: int, conversation_id: str, file: dict[str, Any]) -> None:
    db_store.patch_workspace_file(user_id, conversation_id, file)
    _emit_workspace_file_upserted(user_id, conversation_id, file)


def upsert_workspace_asset(user_id: int, conversation_id: str, asset: dict[str, Any]) -> None:
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import _workspace_asset_item

    upsert_workspace_file(user_id, conversation_id, _workspace_asset_item(asset))


def _current_version_payload(file: dict[str, Any]) -> dict[str, Any] | None:
    versions = file.get("versions")
    if not isinstance(versions, list):
        return None
    current_version_id = str(file.get("current_version_id") or "").strip()
    if current_version_id:
        for version in versions:
            if isinstance(version, dict) and str(version.get("version_id") or "").strip() == current_version_id:
                return version
    for version in reversed(versions):
        if isinstance(version, dict):
            return version
    return None


def _workspace_file_event_idempotency_key(file: dict[str, Any]) -> str:
    file_id = str(file.get("file_id") or file.get("asset_id") or file.get("path") or "").strip()
    current_version_id = str(file.get("current_version_id") or "").strip()
    path = str(file.get("current_version_path") or file.get("path") or "").strip()
    updated_at = str(file.get("updated_at") or file.get("created_at") or "").strip()
    size = str(file.get("size") or "").strip()
    return "workspace_file_upserted:{file_id}:{version}:{path}:{stamp}".format(
        file_id=file_id or "file",
        version=current_version_id or "current",
        path=path or "path",
        stamp=updated_at or size or "snapshot",
    )


def _emit_workspace_file_upserted(user_id: int, conversation_id: str, file: dict[str, Any]) -> None:
    if not isinstance(file, dict):
        return
    file_id = str(file.get("file_id") or file.get("asset_id") or file.get("path") or "").strip()
    path = str(file.get("path") or file.get("current_version_path") or "").strip()
    if not file_id and not path:
        return
    current_version = _current_version_payload(file) or {}
    run_id = str(
        file.get("run_id")
        or current_version.get("run_id")
        or "workspace"
    ).strip() or "workspace"
    try:
        from app.services.agent_harness.runtime.eventing.event_log import append_event

        append_event(
            int(user_id),
            str(conversation_id),
            run_id=run_id,
            event_type="workspace_file_upserted",
            payload=dict(file),
            lane="user",
            artifact_id=file_id or path or None,
            idempotency_key=_workspace_file_event_idempotency_key(file),
        )
    except Exception:
        logger.info(
            "Failed to emit workspace file upsert event for conversation %s",
            conversation_id,
            exc_info=True,
        )


def read_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    return db_store.read_messages_page(user_id, conversation_id, before_seq=before_seq, limit=limit)


def read_presentation_snapshot_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    return db_store.read_presentation_snapshot_messages_page(
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
    )


def read_ui_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    conversation = get_conversation(user_id, conversation_id)
    if conversation is None:
        return {"messages": [], "messages_page": {"has_more": False, "oldest_seq": None, "limit": limit}}
    return read_presentation_snapshot_messages_page(
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
    )


def load_recent_messages(user_id: int, conversation_id: str, *, limit: int) -> list[dict[str, Any]]:
    page = read_messages_page(
        user_id,
        conversation_id,
        before_seq=None,
        limit=max(1, int(limit)),
    )
    messages = page.get("messages")
    if not isinstance(messages, list):
        return []
    return [
        {key: deepcopy(value) for key, value in message.items() if not str(key).startswith("_")}
        for message in messages
        if isinstance(message, dict)
    ]


def iter_messages_reverse(
    user_id: int,
    conversation_id: str,
    *,
    page_size: int = 50,
    max_messages: int | None = None,
):
    remaining = None if max_messages is None else max(0, int(max_messages))
    before_seq: int | None = None
    while remaining is None or remaining > 0:
        limit = max(1, min(int(page_size), remaining)) if remaining is not None else max(1, int(page_size))
        page = read_messages_page(
            user_id,
            conversation_id,
            before_seq=before_seq,
            limit=limit,
        )
        messages = page.get("messages")
        page_info = page.get("messages_page") if isinstance(page.get("messages_page"), dict) else {}
        if not isinstance(messages, list) or not messages:
            return
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            yield message
            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    return
        if not page_info.get("has_more"):
            return
        oldest_seq = page_info.get("oldest_seq")
        if oldest_seq is None:
            return
        before_seq = int(oldest_seq)


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
    return db_store.update_message_record(
        user_id,
        conversation_id,
        message_id=message_id,
        content=content if content is not _UNSET else None,
        blocks=blocks if blocks is not _UNSET else None,
        metadata=metadata if metadata is not _UNSET else None,
        streaming=streaming if streaming is not _UNSET else None,
        has_content=content is not _UNSET,
        has_blocks=blocks is not _UNSET,
        has_metadata=metadata is not _UNSET,
        has_streaming=streaming is not _UNSET,
    )


def append_message_content_delta(
    user_id: int,
    conversation_id: str,
    *,
    message_id: str,
    delta: str,
) -> dict[str, Any] | None:
    result = db_store.append_message_delta_record(user_id, conversation_id, message_id=message_id, delta=delta)
    if result is not None:
        try:
            from app.services.agent_harness.runtime.recall_sidecar import append_message_to_recall_sidecar

            append_message_to_recall_sidecar(user_id, conversation_id, result)
        except Exception:
            pass
    return result


def detail_snapshot(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    snapshot = db_store.build_detail_snapshot(user_id, conversation_id)
    if snapshot is None:
        return None
    return snapshot


async def get_conversation_async(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    return await db_store.get_conversation_record_async(user_id, conversation_id)


async def update_conversation_async(user_id: int, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    return await db_store.update_conversation_record_async(user_id, conversation_id, updates)


async def append_message_async(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    stored = sanitize_persistent_payload(deepcopy(message))
    assert_transcript_persistable_message(stored)
    _assert_direct_transcript_message_allowed(stored)
    stored.setdefault("id", _message_id())
    stored.setdefault("created_at", utc_now())
    stored.setdefault("role", str(stored.get("role") or "assistant"))
    result = await db_store.append_message_record_async(user_id, conversation_id, stored)
    try:
        from app.services.agent_harness.runtime.recall_sidecar import append_message_to_recall_sidecar

        append_message_to_recall_sidecar(user_id, conversation_id, result)
    except Exception:
        pass
    return result


def _assert_direct_transcript_message_allowed(message: dict[str, Any]) -> None:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    message_kind = str(metadata.get("message_kind") or "").strip()
    if message_kind == "agent_context" or message_kind.startswith("internal_"):
        return
    if metadata.get("ui_visible") is False and metadata.get("model_visible") is not False:
        return
    raise ValueError("user-visible messages must be projected from presentation events")


async def update_message_async(
    user_id: int,
    conversation_id: str,
    *,
    message_id: str,
    content: Any = _UNSET,
    blocks: Any = _UNSET,
    metadata: Any = _UNSET,
    streaming: Any = _UNSET,
    tool_calls: Any = _UNSET,
) -> dict[str, Any] | None:
    return await db_store.update_message_record_async(
        user_id,
        conversation_id,
        message_id=message_id,
        content=content if content is not _UNSET else None,
        blocks=blocks if blocks is not _UNSET else None,
        metadata=metadata if metadata is not _UNSET else None,
        streaming=streaming if streaming is not _UNSET else None,
        tool_calls=tool_calls if tool_calls is not _UNSET else Ellipsis,
        has_content=content is not _UNSET,
        has_blocks=blocks is not _UNSET,
        has_metadata=metadata is not _UNSET,
        has_streaming=streaming is not _UNSET,
    )


async def load_messages_async(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    return await db_store.load_message_records_async(user_id, conversation_id)


async def get_message_async(
    user_id: int, conversation_id: str, message_id: str
) -> dict[str, Any] | None:
    return await db_store.get_message_record_async(
        user_id, conversation_id, normalize_message_id(message_id)
    )


async def get_latest_assistant_message_async(
    user_id: int, conversation_id: str
) -> dict[str, Any] | None:
    return await db_store.get_latest_assistant_message_record_async(user_id, conversation_id)


async def message_count_async(user_id: int, conversation_id: str) -> int | None:
    return await db_store.message_count_async(user_id, conversation_id)


async def count_assistant_tool_calls_by_name_async(user_id: int, conversation_id: str, tool_name: str) -> int:
    return await db_store.count_assistant_tool_calls_by_name_async(user_id, conversation_id, tool_name)


async def count_tool_messages_by_name_async(user_id: int, conversation_id: str, tool_name: str) -> int:
    return await db_store.count_tool_messages_by_name_async(user_id, conversation_id, tool_name)


async def patch_runtime_state_async(
    user_id: int,
    conversation_id: str,
    updates: dict[str, Any],
    *,
    touch_updated_at: bool = True,
) -> dict[str, Any]:
    merged_updates = dict(updates)
    if touch_updated_at and "updated_at" not in merged_updates:
        merged_updates["updated_at"] = utc_now()
    updated = await db_store.update_conversation_record_async(user_id, conversation_id, merged_updates)
    return dict(updated or {})


async def read_messages_page_async(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    return await db_store.read_messages_page_async(user_id, conversation_id, before_seq=before_seq, limit=limit)


async def load_recent_messages_async(user_id: int, conversation_id: str, *, limit: int) -> list[dict[str, Any]]:
    page = await read_messages_page_async(
        user_id,
        conversation_id,
        before_seq=None,
        limit=max(1, int(limit)),
    )
    messages = page.get("messages")
    if not isinstance(messages, list):
        return []
    return [
        {key: deepcopy(value) for key, value in message.items() if not str(key).startswith("_")}
        for message in messages
        if isinstance(message, dict)
    ]
