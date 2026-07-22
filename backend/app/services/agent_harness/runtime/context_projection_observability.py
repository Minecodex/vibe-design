from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select

from app.core.config import (
    HARNESS_CONTEXT_PROJECTION_PERF_LOG_DIR,
    HARNESS_CONTEXT_PROJECTION_PERF_LOG_ENABLED,
)
from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import ContextProjectionState


PERF_LOG_FILENAME = "harness_context_projection_perf.jsonl"
_MAX_STRING_CHARS = 240
_MAX_LIST_ITEMS = 20
_MAX_DICT_ITEMS = 40
_SENSITIVE_KEY_PARTS = {
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "secret",
    "token",
    "prompt",
    "content",
    "message",
    "messages",
    "tool_output",
    "tool_result",
    "signed_url",
}


def emit_projection_perf_event(event: str, **payload: Any) -> None:
    if not HARNESS_CONTEXT_PROJECTION_PERF_LOG_ENABLED:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "event": str(event or "context_projection.event")[:120],
        **sanitize_projection_perf_payload(payload),
    }
    try:
        path = _perf_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        return


def sanitize_projection_perf_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    sanitized = _sanitize_mapping(payload, depth=0)
    return sanitized if isinstance(sanitized, dict) else {}


def get_context_projection_worker_health(*, repeated_failure_threshold: int = 3) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    threshold = max(1, int(repeated_failure_threshold or 3))
    with harness_sync_session_scope() as session:
        states = list(session.scalars(select(ContextProjectionState)))

    dirty = [row for row in states if str(row.dirty_mask or "").strip()]
    processing = [
        row
        for row in states
        if row.lease_token and row.lease_expires_at and _as_aware(row.lease_expires_at) > now
    ]
    failed = [row for row in dirty if row.last_failure_at is not None]
    repeated = [row for row in failed if int(row.attempts or 0) >= threshold]
    max_lag = max(
        [
            max(0, int(row.latest_observed_sequence or 0) - int(row.latest_processed_sequence or 0))
            for row in dirty
        ],
        default=0,
    )
    if processing:
        status = "processing"
    elif repeated:
        status = "repeated_failure"
    elif failed:
        status = "failing"
    elif dirty:
        status = "lagging"
    else:
        status = "idle"
    return {
        "status": status,
        "dirty_conversations": len(dirty),
        "processing_conversations": len(processing),
        "failed_conversations": len(failed),
        "repeated_failure_conversations": len(repeated),
        "max_sequence_lag": max_lag,
        "oldest_next_project_at": min(
            [_iso(row.next_project_at) for row in dirty if row.next_project_at is not None],
            default=None,
        ),
        "oldest_failure_at": min(
            [_iso(row.last_failure_at) for row in failed if row.last_failure_at is not None],
            default=None,
        ),
    }


def count_claimable_projection_states() -> int:
    now = datetime.now(timezone.utc)
    with harness_sync_session_scope() as session:
        return len(
            list(
                session.scalars(
                    select(ContextProjectionState.conversation_id).where(
                        ContextProjectionState.dirty_mask != "",
                        or_(ContextProjectionState.next_project_at.is_(None), ContextProjectionState.next_project_at <= now),
                        or_(
                            ContextProjectionState.lease_token.is_(None),
                            ContextProjectionState.lease_expires_at.is_(None),
                            ContextProjectionState.lease_expires_at <= now,
                        ),
                    )
                )
            )
        )


def _perf_log_path() -> Path:
    raw_dir = str(HARNESS_CONTEXT_PROJECTION_PERF_LOG_DIR or "work")
    configured = Path(raw_dir)
    if configured.is_absolute():
        return configured / PERF_LOG_FILENAME
    backend_dir = Path(__file__).resolve().parents[4]
    return backend_dir / configured / PERF_LOG_FILENAME


def _sanitize_mapping(value: dict[str, Any], *, depth: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, child in list(value.items())[:_MAX_DICT_ITEMS]:
        normalized_key = str(key or "")[:80]
        if _is_sensitive_key(normalized_key):
            continue
        sanitized = _sanitize_value(child, depth=depth + 1)
        if sanitized is not None:
            out[normalized_key] = sanitized
    return out


def _sanitize_value(value: Any, *, depth: int) -> Any:
    if depth >= 4:
        return _sanitize_scalar(value)
    if isinstance(value, dict):
        return _sanitize_mapping(value, depth=depth)
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item, depth=depth + 1) for item in list(value)[:_MAX_LIST_ITEMS]]
    return _sanitize_scalar(value)


def _sanitize_scalar(value: Any) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return _iso(value)
    text = str(value)
    if len(text) <= _MAX_STRING_CHARS:
        return text
    return text[:_MAX_STRING_CHARS].rstrip() + f" [truncated {len(text) - _MAX_STRING_CHARS} chars]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return _as_aware(value).isoformat()
    copied = deepcopy(value)
    return str(copied) if copied is not None else None
