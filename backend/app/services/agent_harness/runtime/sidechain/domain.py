from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SidechainStatus(StrEnum):
    CREATED = "created"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


SIDECHAIN_TERMINAL_STATUSES = {
    SidechainStatus.COMPLETED,
    SidechainStatus.FAILED,
    SidechainStatus.CANCELLED,
}

SIDECHAIN_RETRYABLE_TERMINAL_STATUSES = {
    SidechainStatus.FAILED,
    SidechainStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class SidechainIdentity:
    task_id: str
    parent_conversation_id: str
    parent_run_id: str
    parent_tool_call_id: str | None = None
    parent_usage_log_id: int | None = None
    child_run_id: str | None = None

    def __post_init__(self) -> None:
        required = {
            "task_id": self.task_id,
            "parent_conversation_id": self.parent_conversation_id,
            "parent_run_id": self.parent_run_id,
        }
        missing = [key for key, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError(f"Missing sidechain identity fields: {', '.join(missing)}")

    def to_event_identity(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_conversation_id": self.parent_conversation_id,
            "parent_run_id": self.parent_run_id,
            "parent_tool_call_id": self.parent_tool_call_id,
            "parent_usage_log_id": self.parent_usage_log_id,
            "child_run_id": self.child_run_id,
        }


def coerce_sidechain_status(value: SidechainStatus | str) -> SidechainStatus:
    if isinstance(value, SidechainStatus):
        return value
    return SidechainStatus(str(value))


def is_terminal_sidechain_status(value: SidechainStatus | str) -> bool:
    return coerce_sidechain_status(value) in SIDECHAIN_TERMINAL_STATUSES


def is_retryable_terminal_status(value: SidechainStatus | str) -> bool:
    return coerce_sidechain_status(value) in SIDECHAIN_RETRYABLE_TERMINAL_STATUSES


def assert_valid_transition(current: SidechainStatus | str | None, next_status: SidechainStatus | str) -> None:
    if current is None:
        return
    current_status = coerce_sidechain_status(current)
    proposed = coerce_sidechain_status(next_status)
    if current_status in SIDECHAIN_TERMINAL_STATUSES and proposed != current_status:
        raise ValueError(f"Sidechain terminal state is immutable: {current_status.value} -> {proposed.value}")
