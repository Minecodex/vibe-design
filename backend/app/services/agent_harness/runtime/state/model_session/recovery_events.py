from __future__ import annotations

import uuid
from typing import Any

from app.services.agent_harness.runtime.execution_support.failure_contract import failure_from_review
from app.services.agent_harness.runtime.conversation_events import (
    append_conversation_event,
    load_conversation_events,
)
from app.services.agent_harness.runtime.state.store_core import utc_now


def append_recovery_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str | None,
    stage: str | None,
    source: str,
    decision: str,
    review: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
    recovery_hint: dict[str, Any] | None = None,
    attempt_count: int | None = None,
    related_tool_call_id: str | None = None,
    sync_runtime: bool = True,
) -> dict[str, Any]:
    normalized_review = review if isinstance(review, dict) else {}
    normalized_failure = (
        failure
        if isinstance(failure, dict)
        else failure_from_review(
            normalized_review,
            failure_stage=str(stage or normalized_review.get("failure_stage") or "").strip() or None,
            retryable=decision in {"retry", "switch_strategy", "blocked"},
        )
    )
    normalized_hint = (
        recovery_hint
        if isinstance(recovery_hint, dict)
        else normalized_review.get("recovery_hint")
        if isinstance(normalized_review.get("recovery_hint"), dict)
        else None
    )
    event = {
        "event_id": uuid.uuid4().hex[:12],
        "run_id": run_id,
        "stage": stage or normalized_review.get("failure_stage"),
        "source": source,
        "decision": decision,
        "review": normalized_review,
        "failure": normalized_failure,
        "recovery_hint": normalized_hint,
        "attempt_count": int(attempt_count or 0),
        "related_tool_call_id": related_tool_call_id,
        "created_at": utc_now(),
    }
    try:
        append_conversation_event(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type="recovery_event",
            payload=event,
            lane="system",
            tool_call_id=related_tool_call_id,
        )
    except FileNotFoundError:
        pass
    if sync_runtime:
        _sync_recovery_projection(user_id, conversation_id, event)
    return event


def load_recovery_events(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in load_conversation_events(user_id, conversation_id):
        if str(record.get("type") or "") != "recovery_event":
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if payload:
            events.append(payload)
    return events


def project_recovery_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "retryable": False,
            "last_failure_signature": None,
            "attempt_count": 0,
            "required_next_action": None,
            "avoid_tools": [],
            "preferred_tools": [],
            "terminal_failure": None,
            "blocked_reason": None,
        }
    latest = events[-1]
    review = latest.get("review") if isinstance(latest.get("review"), dict) else {}
    failure = latest.get("failure") if isinstance(latest.get("failure"), dict) else None
    hint = latest.get("recovery_hint") if isinstance(latest.get("recovery_hint"), dict) else {}
    decision = str(latest.get("decision") or "")
    terminal_failure = failure if decision in {"stop", "failed"} else None
    return {
        "retryable": decision in {"retry", "switch_strategy", "blocked"},
        "last_failure_signature": (
            review.get("no_progress_signature")
            or review.get("failure_signature")
            or (failure or {}).get("failure_signature")
        ),
        "attempt_count": int(latest.get("attempt_count") or 0),
        "required_next_action": (
            review.get("required_next_action")
            or (failure or {}).get("required_next_action")
        ),
        "avoid_tools": list(hint.get("avoid_tools") or []),
        "preferred_tools": list(hint.get("preferred_tools") or []),
        "terminal_failure": terminal_failure,
        "blocked_reason": (
            review.get("failure_kind")
            if decision in {"blocked", "stop", "failed"}
            else None
        ),
    }


def recovery_summary_from_event(event: dict[str, Any]) -> dict[str, Any]:
    review = event.get("review") if isinstance(event.get("review"), dict) else {}
    return {
        "failure_signature": review.get("no_progress_signature") or review.get("failure_signature"),
        "failure_kind": review.get("failure_kind"),
        "failure_stage": event.get("stage") or review.get("failure_stage"),
        "decision": event.get("decision"),
        "attempt_count": event.get("attempt_count"),
        "required_next_action": review.get("required_next_action"),
        "root_cause_hint": review.get("root_cause_hint"),
        "recovery_hint": event.get("recovery_hint"),
        "failure": event.get("failure"),
    }


def _sync_recovery_projection(user_id: int, conversation_id: str, event: dict[str, Any]) -> None:
    try:
        from app.services.agent_harness.workspace.conversation.conversation_meta_store import update_conversation

        update_conversation(
            user_id,
            conversation_id,
            recovery_summary=recovery_summary_from_event(event),
            failure=event.get("failure"),
        )
    except Exception:
        return

