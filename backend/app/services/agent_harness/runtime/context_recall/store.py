from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime.conversation_events import append_conversation_event, load_conversation_events
from app.services.agent_harness.runtime.state.store_core import utc_now


def load_memory_index(user_id: int, conversation_id: str, *, meta_dir=None) -> dict[str, Any]:
    return {"entries": []}


def save_memory_index(user_id: int, conversation_id: str, payload: dict[str, Any], *, meta_dir=None) -> dict[str, Any]:
    normalized = {
        "entries": [entry for entry in payload.get("entries") or [] if isinstance(entry, dict)],
        "updated_at": utc_now(),
    }
    return normalized


def load_collapse_commits(user_id: int, conversation_id: str, *, meta_dir=None) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    for event in load_conversation_events(user_id, conversation_id):
        if str(event.get("type") or "") != "collapse_commit":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if payload:
            commits.append(payload)
    return commits


def load_compact_failures(user_id: int, conversation_id: str, *, meta_dir=None) -> dict[str, Any]:
    count = 0
    updated_at = None
    for event in load_conversation_events(user_id, conversation_id):
        event_type = str(event.get("type") or "")
        if event_type == "llm_compact_failure_reset":
            count = 0
            updated_at = event.get("created_at")
        elif event_type == "llm_compact_failure":
            count += 1
            updated_at = event.get("created_at")
    return {"llm_failure_count": max(0, count), "updated_at": updated_at}


def record_llm_compact_failure(user_id: int, conversation_id: str, *, meta_dir=None) -> dict[str, Any]:
    current = load_compact_failures(user_id, conversation_id, meta_dir=meta_dir)
    payload = {"llm_failure_count": int(current.get("llm_failure_count") or 0) + 1, "updated_at": utc_now()}
    try:
        append_conversation_event(
            user_id,
            conversation_id,
            run_id=None,
            event_type="llm_compact_failure",
            payload=payload,
            lane="system",
        )
    except FileNotFoundError:
        pass
    return payload


def reset_llm_compact_failures(user_id: int, conversation_id: str, *, meta_dir=None) -> dict[str, Any]:
    payload = {"llm_failure_count": 0, "updated_at": utc_now()}
    try:
        append_conversation_event(
            user_id,
            conversation_id,
            run_id=None,
            event_type="llm_compact_failure_reset",
            payload=payload,
            lane="system",
        )
    except FileNotFoundError:
        pass
    return payload


def append_collapse_commit(
    user_id: int,
    conversation_id: str,
    *,
    source_item_count: int,
    replacement_item_count: int,
    estimated_tokens_before: int,
    estimated_tokens_after: int,
    levels_applied: list[str],
    searchable_sources: list[str],
    preserved_recent_groups: int,
    message_range: dict[str, Any] | None = None,
    covered_message_ids: list[str] | None = None,
    result_refs: list[str] | None = None,
    meta_dir=None,
) -> dict[str, Any]:
    import uuid

    record = {
        "commit_id": uuid.uuid4().hex[:12],
        "created_at": utc_now(),
        "source_item_count": source_item_count,
        "replacement_item_count": replacement_item_count,
        "estimated_tokens_before": estimated_tokens_before,
        "estimated_tokens_after": estimated_tokens_after,
        "levels_applied": list(levels_applied),
        "searchable_sources": list(searchable_sources),
        "preserved_recent_groups": preserved_recent_groups,
        "message_range": message_range if isinstance(message_range, dict) else {},
        "covered_message_ids": list(covered_message_ids or []),
        "result_refs": list(result_refs or []),
    }
    try:
        append_conversation_event(
            user_id,
            conversation_id,
            run_id=None,
            event_type="collapse_commit",
            payload=record,
            lane="system",
        )
    except FileNotFoundError:
        return record
    try:
        from app.services.agent_harness.runtime.recall_sidecar import rebuild_recall_sidecar_with_guard

        rebuild_recall_sidecar_with_guard(user_id, conversation_id, meta_dir=meta_dir)
    except Exception:
        pass
    return record
