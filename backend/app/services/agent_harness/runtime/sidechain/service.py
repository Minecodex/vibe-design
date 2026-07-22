from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable

from .domain import SIDECHAIN_TERMINAL_STATUSES, SidechainIdentity, SidechainStatus, assert_valid_transition, coerce_sidechain_status


@dataclass(frozen=True, slots=True)
class SidechainTask:
    identity: SidechainIdentity
    label: str | None
    objective: str
    context_mode: str
    status: SidechainStatus = SidechainStatus.CREATED
    output_contract: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    reason_code: str | None = None
    transcript_ref: str | None = None
    result_ref: str | None = None
    usage_summary: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_event(self) -> dict[str, Any]:
        return {
            **self.identity.to_event_identity(),
            "label": self.label,
            "objective": self.objective,
            "context_mode": self.context_mode,
            "status": self.status.value,
            "output_contract": self.output_contract,
            "summary": self.summary,
            "reason_code": self.reason_code,
            "transcript_ref": self.transcript_ref,
            "result_ref": self.result_ref,
            "usage_summary": self.usage_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SidechainTaskService:
    def __init__(self, *, event_appender: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._tasks: dict[str, SidechainTask] = {}
        self._event_appender = event_appender

    def create(
        self,
        *,
        identity: SidechainIdentity,
        label: str | None,
        objective: str,
        context_mode: str,
        output_contract: dict[str, Any] | None = None,
    ) -> SidechainTask:
        existing = self._tasks.get(identity.task_id)
        if existing is not None:
            return existing
        task = SidechainTask(
            identity=identity,
            label=label,
            objective=objective,
            context_mode=context_mode,
            output_contract=dict(output_contract or {}),
        )
        self._tasks[identity.task_id] = task
        self._append(task)
        return task

    def transition(
        self,
        task_id: str,
        status: SidechainStatus | str,
        *,
        summary: str | None = None,
        reason_code: str | None = None,
        transcript_ref: str | None = None,
        result_ref: str | None = None,
        usage_summary: dict[str, Any] | None = None,
    ) -> SidechainTask:
        existing = self._tasks.get(task_id)
        if existing is None:
            raise KeyError(task_id)
        next_status = coerce_sidechain_status(status)
        if existing.status in SIDECHAIN_TERMINAL_STATUSES:
            return existing
        assert_valid_transition(existing.status, next_status)
        task = replace(
            existing,
            status=next_status,
            summary=summary if summary is not None else existing.summary,
            reason_code=reason_code if reason_code is not None else existing.reason_code,
            transcript_ref=transcript_ref if transcript_ref is not None else existing.transcript_ref,
            result_ref=result_ref if result_ref is not None else existing.result_ref,
            usage_summary=dict(usage_summary) if usage_summary is not None else existing.usage_summary,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks[task_id] = task
        self._append(task)
        return task

    def get(self, task_id: str) -> SidechainTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _append(self, task: SidechainTask) -> None:
        if self._event_appender is not None:
            self._event_appender(task.to_event())
