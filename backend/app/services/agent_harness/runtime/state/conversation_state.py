"""Unified runtime snapshot for a Harness conversation turn."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.services.agent_harness.authoring.planning.step_status import derive_active_step

from .runtime_state import RuntimeState


def merge_summary_with_plan(
    summary_data: dict[str, Any] | None,
    *,
    plan_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if summary_data is None and plan_state is None:
        return None

    merged = {
        "goal": list((summary_data or {}).get("goal") or []),
        "completed": list((summary_data or {}).get("completed") or []),
        "files": list((summary_data or {}).get("files") or []),
        "blockers": list((summary_data or {}).get("blockers") or []),
        "next_step": list((summary_data or {}).get("next_step") or []),
    }

    if not plan_state:
        return merged

    summary = str(plan_state.get("summary") or "").strip()
    if summary:
        merged["goal"] = [summary]

    steps = plan_state.get("steps") or []
    if isinstance(steps, list):
        completed = [
            str(step.get("title") or "").strip()
            for step in steps
            if isinstance(step, dict)
            and str(step.get("status") or "") == "completed"
            and str(step.get("title") or "").strip()
        ]
        if completed:
            merged["completed"] = completed[:5]

        active_step = derive_active_step([step for step in steps if isinstance(step, dict)])
        active_title = str((active_step or {}).get("title") or "").strip()
        if active_title:
            merged["next_step"] = [active_title]
        else:
            pending = next(
                (
                    str(step.get("title") or "").strip()
                    for step in steps
                    if isinstance(step, dict)
                    and str(step.get("status") or "") in {"in_progress", "pending"}
                    and str(step.get("title") or "").strip()
                ),
                "",
            )
            if pending:
                merged["next_step"] = [pending]

    merged["files"] = _dedupe_preserve_order(merged["files"])
    return merged


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


@dataclass(slots=True)
class ConversationStateSnapshot:
    runtime_state: RuntimeState
    history_summary: dict[str, Any] | None
    plan_state: dict[str, Any] | None
    recovery_summary: dict[str, Any] | None
    manifest_summary: str
    session_memory: str

    @classmethod
    def build(
        cls,
        *,
        runtime_state: RuntimeState,
        history_summary: dict[str, Any] | None,
        plan_state: dict[str, Any] | None,
        recovery_summary: dict[str, Any] | None,
        manifest_summary: str,
        session_memory: str,
    ) -> "ConversationStateSnapshot":
        merged_history = merge_summary_with_plan(history_summary, plan_state=plan_state)
        return cls(
            runtime_state=runtime_state,
            history_summary=merged_history,
            plan_state=plan_state,
            recovery_summary=recovery_summary,
            manifest_summary=manifest_summary,
            session_memory=session_memory,
        )

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "runtime_state": {
                "phase": self.runtime_state.phase,
                "plan_policy": self.runtime_state.plan_policy,
                "execution_policy": self.runtime_state.execution_policy,
                "is_committed_execution": self.runtime_state.is_committed_execution,
                "permission_mode": self.runtime_state.permission_mode.value,
            },
            "history_summary": self.history_summary,
            "plan_state": self.plan_state,
            "recovery_summary": self.recovery_summary,
            "manifest_summary": self.manifest_summary,
            "session_memory_preview": self.session_memory[:500],
        }

    def sha256(self) -> str:
        payload = json.dumps(self.to_audit_payload(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
