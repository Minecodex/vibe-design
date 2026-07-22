from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EventSpec:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    lane: str = "user"
    idempotency_key: str | None = None
    block_id: str | None = None
    tool_call_id: str | None = None
    artifact_id: str | None = None
    parent_block_id: str | None = None


@dataclass(frozen=True)
class MessageSpec:
    role: str
    content: str | None = None
    blocks: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    created_at: str | None = None
    streaming: bool = False
    idempotency_key: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class StepSpec:
    step_type: str
    input: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    priority: int = 0
    max_attempts: int = 1
    depends_on_step_id: str | None = None


@dataclass(frozen=True)
class BillingSpec:
    billing_key: str
    model_name: str
    task_type: str
    amount_cents: int = 0
    model_label: str | None = None
    parent_id: int | None = None
    params: dict[str, Any] | None = None
    task_status: str = "pending"
    billing_label: str | None = None
    elapsed_ms: int | None = None
    provider_code: str | None = None
    provider_request_id: str | None = None
    provider_trace_id: str | None = None
    provider_task_id: str | None = None
    billing_mode: str | None = None


@dataclass(frozen=True)
class BlobSpec:
    content: str
    tool_call_id: str
    tool_name: str
    threshold_chars: int | None = None


@dataclass(frozen=True)
class NotificationSpec:
    kind: str = "runtime"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceFileSpec:
    file: dict[str, Any]


@dataclass(frozen=True)
class StepError:
    error_type: str
    summary: str


@dataclass(frozen=True)
class StepResult:
    status: str
    runtime_patch: dict[str, Any] = field(default_factory=dict)
    events: list[EventSpec] = field(default_factory=list)
    messages: list[MessageSpec] = field(default_factory=list)
    next_steps: list[StepSpec] = field(default_factory=list)
    activity_summary: dict[str, Any] = field(default_factory=dict)
    error: StepError | None = None
