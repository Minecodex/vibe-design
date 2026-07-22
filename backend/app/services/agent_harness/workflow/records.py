from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkflowRunRecord:
    id: int
    run_id: str
    user_id: int
    conversation_id: str
    kind: str
    status: str
    input: dict[str, Any]
    idempotency_key: str
    parent_usage_log_id: int | None
    cancel_requested: bool
    current_step_type: str | None = None
    created: bool = False


@dataclass(frozen=True)
class WorkflowStepRecord:
    id: int
    step_id: str
    run_id: str
    conversation_id: str
    user_id: int
    step_type: str
    status: str
    input: dict[str, Any]
    attempts: int
    max_attempts: int
    priority: int
    claim_owner: str | None
    claim_token: str | None
    claim_expires_at: datetime | None
    idempotency_key: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False


def run_from_orm(row) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        id=int(row.id),
        run_id=str(row.run_id),
        user_id=int(row.user_id),
        conversation_id=str(row.conversation_id),
        kind=str(row.kind),
        status=str(row.status),
        input=dict(row.input_json or {}),
        idempotency_key=str(row.idempotency_key),
        parent_usage_log_id=row.parent_usage_log_id,
        cancel_requested=bool(row.cancel_requested),
        current_step_type=row.current_step_type,
    )


def step_from_orm(row, *, cancel_requested: bool = False) -> WorkflowStepRecord:
    return WorkflowStepRecord(
        id=int(row.id),
        step_id=str(row.step_id),
        run_id=str(row.run_id),
        conversation_id=str(row.conversation_id),
        user_id=int(row.user_id),
        step_type=str(row.step_type),
        status=str(row.status),
        input=dict(row.input_json or {}),
        attempts=int(row.attempts or 0),
        max_attempts=int(row.max_attempts or 1),
        priority=int(row.priority or 0),
        claim_owner=row.claim_owner,
        claim_token=row.claim_token,
        claim_expires_at=row.claim_expires_at,
        idempotency_key=str(row.idempotency_key),
        checkpoint=dict(row.checkpoint_json or {}),
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cancel_requested=bool(cancel_requested),
    )
