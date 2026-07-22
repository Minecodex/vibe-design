from __future__ import annotations

import json
from typing import Any

from app.services.agent_harness.workspace.conversation.conversation_service import get_conversation, update_conversation
from .outline_plan import (
    OutlineLockedError,
    apply_outline_patch,
    build_outline_projection,
    compile_execution_plan,
    create_outline_state,
    outline_from_user_plan,
    outline_to_user_plan,
)
from app.services.agent_harness.runtime.state.runtime_projection_store import persist_outline_runtime_state
from app.services.agent_harness.runtime.state.store_core import read_outline_runtime_state, utc_now
from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
from .step_status import derive_active_step
from .user_plan import normalize_artifact_type


def _outline_items_from_user_plan(user_plan: dict[str, Any]) -> list[dict[str, Any]]:
    outline = user_plan.get("outline")
    if not isinstance(outline, list):
        return []
    return [item for item in outline if isinstance(item, dict)]


def _normalize_items(user_plan: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(_outline_items_from_user_plan(user_plan), start=1):
        items.append(
            {
                "id": str(item.get("id") or f"item-{index}"),
                "title": str(item.get("title") or "").strip(),
                "summary": str(item.get("summary") or item.get("description") or "").strip() or None,
                "order": int(item.get("order") or index),
            }
        )
    return items


def _strip_outline_status(outline: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(outline, dict):
        return outline
    normalized = {key: value for key, value in outline.items() if key != "status"}
    normalized["items"] = [
        {key: value for key, value in item.items() if key != "status"}
        for item in list(outline.get("items") or [])
        if isinstance(item, dict)
    ]
    return normalized


def _normalize_constraints(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalized_outline_signature(outline: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(outline, dict):
        return None
    return {
        "title": str(outline.get("title") or "").strip(),
        "summary": str(outline.get("summary") or "").strip(),
        "constraints": tuple(str(item).strip() for item in list(outline.get("constraints") or []) if str(item).strip()),
        "style_notes": tuple(str(item).strip() for item in list(outline.get("style_notes") or []) if str(item).strip()),
        "items": tuple(
            (
                str(item.get("id") or "").strip(),
                str(item.get("title") or "").strip(),
                str(item.get("summary") or "").strip(),
                int(item.get("order") or 0),
            )
            for item in list(outline.get("items") or [])
            if isinstance(item, dict)
        ),
    }


def validate_revision_change(
    *,
    previous_outline: dict[str, Any] | None,
    next_outline: dict[str, Any] | None,
    revision_instruction: str,
) -> None:
    previous_signature = _normalized_outline_signature(previous_outline)
    next_signature = _normalized_outline_signature(next_outline)
    if previous_signature == next_signature:
        raise ValueError("修订后的大纲未体现用户要求的修改。")


def _runtime_projection_status(
    *,
    current_outline: dict[str, Any] | None,
    execution_state: dict[str, Any] | None,
    projection_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(projection_state, dict):
        return projection_state
    execution_status = str((execution_state or {}).get("status") or "").strip().lower()
    if execution_status == "completed":
        return {**projection_state, "status": "finalizing", "snapshot_status": "finalizing"}
    return projection_state


_TERMINAL_OUTLINE_STATUSES = {"completed", "failed", "blocked", "cancelled"}
_ACTIVE_STEP_STATUSES = {"in_progress", "running"}


def _terminal_timestamp_key(status: str) -> str:
    if status == "completed":
        return "completed_at"
    if status == "cancelled":
        return "cancelled_at"
    return "failed_at" if status == "failed" else "blocked_at"


def _terminalize_steps(
    steps: Any,
    *,
    status: str,
    finished_at: str,
) -> list[dict[str, Any]]:
    timestamp_key = _terminal_timestamp_key(status)
    step_list = [step for step in list(steps or []) if isinstance(step, dict)]
    active_step_id = str((derive_active_step(step_list) or {}).get("id") or "").strip()
    normalized_steps: list[dict[str, Any]] = []
    for step in step_list:
        step_status = str(step.get("status") or "").strip().lower()
        is_current = bool(active_step_id and str(step.get("id") or "") == active_step_id)
        should_terminalize = status == "completed" or (
            step_status in _ACTIVE_STEP_STATUSES
            and (not active_step_id or is_current)
        )
        if not should_terminalize:
            normalized_steps.append(step)
            continue
        updated = {
            **step,
            "status": status,
            "last_activity_at": step.get("last_activity_at") or finished_at,
        }
        if status == "completed":
            updated["completed_at"] = step.get("completed_at") or finished_at
        else:
            updated[timestamp_key] = step.get(timestamp_key) or finished_at
        normalized_steps.append(updated)
    return normalized_steps


def _terminalize_items(
    items: Any,
    *,
    status: str,
    current_item_id: str | None,
) -> list[dict[str, Any]]:
    return [dict(item) for item in list(items or []) if isinstance(item, dict)]


def _terminal_payload(status: str, *, finished_at: str, failure: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "snapshot_status": status,
        "finished_at": finished_at,
    }
    if failure is not None:
        payload["failure"] = failure
        payload["last_error_summary"] = str(failure.get("summary") or "").strip() or None
    return payload


def _outline_terminal_payload(status: str, *, finished_at: str, failure: dict[str, Any] | None) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in _terminal_payload(status, finished_at=finished_at, failure=failure).items()
        if key != "status"
    }
    return payload


def _should_start_new_plan_instance(previous_outline: dict[str, Any] | None) -> bool:
    if not isinstance(previous_outline, dict):
        return True
    return str(previous_outline.get("snapshot_status") or "").strip().lower() in {"completed", "failed", "abandoned"}


def _build_next_outline_state(
    *,
    plan_state: dict[str, Any],
    previous_outline: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    raw_user_plan = plan_state.get("user_plan") if isinstance(plan_state.get("user_plan"), dict) else {}
    if _should_start_new_plan_instance(previous_outline):
        source = raw_user_plan if isinstance(raw_user_plan, dict) else {}
        artifact_type = normalize_artifact_type(source.get("artifact_type") or plan_state.get("artifact_type") or "other")
        return create_outline_state(
            artifact_type=artifact_type,
            title=str(source.get("title") or plan_state.get("title") or "任务大纲"),
            summary=str(source.get("summary") or plan_state.get("summary") or ""),
            items=_outline_items_from_user_plan(source) or [{"title": "主要内容", "summary": str(plan_state.get("summary") or "").strip() or None}],
            status=status,
            version=1,
            plan_instance_id=None,
            outline_id=None,
            previous_items=None,
            constraints=list(source.get("constraints") or []),
            style_notes=list(source.get("style_notes") or source.get("styleNotes") or []),
            snapshot_status="active",
        )
    return outline_from_user_plan(
        raw_user_plan,
        previous_outline=previous_outline,
        status=status,
    )


def complete_outline_runtime_execution(user_id: int, conversation_id: str) -> dict[str, Any]:
    runtime_state = read_outline_runtime_state(user_id, conversation_id)
    current_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
    execution_state = runtime_state.get("execution_state") if isinstance(runtime_state.get("execution_state"), dict) else None
    execution_run = runtime_state.get("execution_run") if isinstance(runtime_state.get("execution_run"), dict) else None
    if current_outline is None:
        return runtime_state
    current_outline = {
        **(_strip_outline_status(current_outline) or {}),
        "snapshot_status": "completed",
    }
    if isinstance(execution_state, dict):
        finished_at = utc_now()
        execution_state = {
            **execution_state,
            "status": "completed",
            "current_item_id": None,
            "steps": [
                {
                    **step,
                    "status": "completed",
                    "completed_at": step.get("completed_at") or finished_at,
                    "last_activity_at": step.get("last_activity_at") or finished_at,
                }
                for step in list(execution_state.get("steps") or [])
                if isinstance(step, dict)
            ],
        }
    projection_state = _runtime_projection_status(
        current_outline=current_outline,
        execution_state=execution_state,
        projection_state=build_outline_projection(current_outline, execution_state),
    )
    if isinstance(projection_state, dict):
        projection_state = {
            **projection_state,
            "status": "completed",
            "snapshot_status": "completed",
            "current_item_id": None,
            "execution_steps": [
                {**step, "status": "completed"}
                for step in list(projection_state.get("execution_steps") or [])
                if isinstance(step, dict)
            ],
        }
    if isinstance(execution_run, dict):
        execution_run = {**execution_run, "status": "completed", "finished_at": utc_now()}
    return persist_outline_runtime_state(
        user_id,
        conversation_id,
        current_outline=current_outline,
        execution_state=execution_state,
        projection_state=projection_state,
        execution_run=execution_run,
        render_mode="replace_current",
        sync_runtime_state=False,
    )


def terminalize_outline_runtime_execution(
    user_id: int,
    conversation_id: str,
    status: str,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in _TERMINAL_OUTLINE_STATUSES:
        raise ValueError(f"unsupported outline terminal status: {status}")
    if normalized_status == "completed":
        return complete_outline_runtime_execution(user_id, conversation_id)

    runtime_state = read_outline_runtime_state(user_id, conversation_id)
    current_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
    execution_state = runtime_state.get("execution_state") if isinstance(runtime_state.get("execution_state"), dict) else None
    execution_run = runtime_state.get("execution_run") if isinstance(runtime_state.get("execution_run"), dict) else None
    finished_at = utc_now()

    current_item_id = str((execution_state or {}).get("current_item_id") or "").strip() or None
    terminal_payload = _terminal_payload(normalized_status, finished_at=finished_at, failure=failure)
    outline_terminal_payload = _outline_terminal_payload(normalized_status, finished_at=finished_at, failure=failure)

    if isinstance(current_outline, dict):
        current_outline = {
            **(_strip_outline_status(current_outline) or {}),
            **outline_terminal_payload,
        }

    if isinstance(execution_state, dict):
        execution_state = {
            **execution_state,
            **terminal_payload,
            "current_item_id": None,
            "steps": _terminalize_steps(
                execution_state.get("steps"),
                status=normalized_status,
                finished_at=finished_at,
            ),
        }

    projection_state = build_outline_projection(current_outline, execution_state)
    if isinstance(projection_state, dict):
        projection_state = {
            **projection_state,
            **terminal_payload,
            "current_item_id": None,
            "items": _terminalize_items(
                projection_state.get("items"),
                status=normalized_status,
                current_item_id=current_item_id,
            ),
            "execution_steps": _terminalize_steps(
                projection_state.get("execution_steps"),
                status=normalized_status,
                finished_at=finished_at,
            ),
        }

    if isinstance(execution_run, dict):
        execution_run = {
            **execution_run,
            **terminal_payload,
        }

    return persist_outline_runtime_state(
        user_id,
        conversation_id,
        current_outline=current_outline,
        execution_state=execution_state,
        projection_state=projection_state,
        execution_run=execution_run,
        render_mode="replace_current",
        sync_runtime_state=False,
    )


def complete_conversation_plan_state(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    conversation = get_conversation(user_id, conversation_id)
    if not isinstance(conversation, dict):
        return None
    plan_state = conversation.get("plan_state")
    if not isinstance(plan_state, dict):
        return conversation
    finished_at = utc_now()
    completed_plan = {
        **plan_state,
        "status": "completed",
        "current_item_id": None,
        "steps": [
            {
                **step,
                "status": "completed",
                "completed_at": step.get("completed_at") or finished_at,
                "last_activity_at": step.get("last_activity_at") or finished_at,
            }
            for step in list(plan_state.get("steps") or [])
            if isinstance(step, dict)
        ],
    }
    execution_state = plan_state.get("execution_state")
    if isinstance(execution_state, dict):
        completed_plan["execution_state"] = {
            **execution_state,
            "status": "completed",
            "current_item_id": None,
            "steps": [
                {
                    **step,
                    "status": "completed",
                    "completed_at": step.get("completed_at") or finished_at,
                    "last_activity_at": step.get("last_activity_at") or finished_at,
                }
                for step in list(execution_state.get("steps") or [])
                if isinstance(step, dict)
            ],
        }
    outline_state = plan_state.get("outline_state")
    if isinstance(outline_state, dict):
        completed_plan["outline_state"] = {
            **(_strip_outline_status(outline_state) or {}),
            "snapshot_status": "completed",
        }
        completed_plan["projection_state"] = build_outline_projection(
            completed_plan["outline_state"],
            completed_plan.get("execution_state")
            if isinstance(completed_plan.get("execution_state"), dict)
            else {
                "status": "completed",
                "current_item_id": None,
                "steps": completed_plan.get("steps") or [],
            },
        )
    user_plan = plan_state.get("user_plan")
    if isinstance(user_plan, dict):
        completed_plan["user_plan"] = {**user_plan, "status": "completed"}
    return update_conversation(user_id, conversation_id, plan_state=completed_plan)


def terminalize_conversation_plan_state(
    user_id: int,
    conversation_id: str,
    status: str,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in _TERMINAL_OUTLINE_STATUSES:
        raise ValueError(f"unsupported plan terminal status: {status}")
    if normalized_status == "completed":
        return complete_conversation_plan_state(user_id, conversation_id)

    conversation = get_conversation(user_id, conversation_id)
    if not isinstance(conversation, dict):
        return None
    plan_state = conversation.get("plan_state")
    if not isinstance(plan_state, dict):
        return conversation

    finished_at = utc_now()
    current_item_id = str(plan_state.get("current_item_id") or "").strip() or None
    execution_state = plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else None
    if isinstance(execution_state, dict):
        current_item_id = str(execution_state.get("current_item_id") or current_item_id or "").strip() or None

    terminal_payload = _terminal_payload(normalized_status, finished_at=finished_at, failure=failure)
    outline_terminal_payload = _outline_terminal_payload(normalized_status, finished_at=finished_at, failure=failure)
    terminal_plan = {
        **plan_state,
        **terminal_payload,
        "current_item_id": None,
        "steps": _terminalize_steps(
            plan_state.get("steps"),
            status=normalized_status,
            finished_at=finished_at,
        ),
    }

    if isinstance(execution_state, dict):
        terminal_plan["execution_state"] = {
            **execution_state,
            **terminal_payload,
            "current_item_id": None,
            "steps": _terminalize_steps(
                execution_state.get("steps"),
                status=normalized_status,
                finished_at=finished_at,
            ),
        }

    outline_state = plan_state.get("outline_state")
    if isinstance(outline_state, dict):
        terminal_plan["outline_state"] = {
            **(_strip_outline_status(outline_state) or {}),
            **outline_terminal_payload,
        }
        terminal_plan["projection_state"] = build_outline_projection(
            terminal_plan["outline_state"],
            terminal_plan.get("execution_state")
            if isinstance(terminal_plan.get("execution_state"), dict)
            else {
                "status": normalized_status,
                "current_item_id": None,
                "steps": terminal_plan.get("steps") or [],
            },
        )
        if isinstance(terminal_plan["projection_state"], dict):
            terminal_plan["projection_state"] = {
                **terminal_plan["projection_state"],
                **terminal_payload,
                "current_item_id": None,
            }

    user_plan = plan_state.get("user_plan")
    if isinstance(user_plan, dict):
        terminal_plan["user_plan"] = {**user_plan, "status": normalized_status}

    return update_conversation(user_id, conversation_id, plan_state=terminal_plan)


class OutlineCoordinator:
    def __init__(self, *, user_id: int, conversation_id: str, run_id: str, ctx) -> None:
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.ctx = ctx

    def _conversation_snapshot(self) -> dict[str, Any]:
        snapshot = get_conversation(self.user_id, self.conversation_id)
        return snapshot if isinstance(snapshot, dict) else {}

    def _plan_state_snapshot(self) -> dict[str, Any]:
        return dict(self._conversation_snapshot().get("plan_state") or {})

    def _update_conversation_outline_runtime(self, runtime_state: dict[str, Any], *, phase: str, runtime_status: str, run_state: str, turn_status: str) -> dict[str, Any]:
        conversation = update_conversation(
            self.user_id,
            self.conversation_id,
            phase=phase,
            runtime_status=runtime_status,
            run_state=run_state,
            turn_status=turn_status,
            outline_runtime=runtime_state,
        )
        return conversation if isinstance(conversation, dict) else self._conversation_snapshot()

    def _publish_outline_event(
        self,
        *,
        event_type: str,
        current_outline: dict[str, Any] | None,
        projection_state: dict[str, Any] | None,
        execution_state: dict[str, Any] | None,
        change_source: str,
    ) -> None:
        if not isinstance(current_outline, dict):
            return
        plan_instance_id = str(current_outline.get("plan_instance_id") or "plan-unknown")
        outline_version = int(current_outline.get("version") or 1)
        publish_user_event(
            self.user_id,
            self.conversation_id,
            run_id=self.run_id,
            event_type=event_type,
            data={
                "outline": current_outline,
                "projection": projection_state if isinstance(projection_state, dict) else None,
                "execution_state": execution_state if isinstance(execution_state, dict) else None,
                "change_source": change_source,
            },
            lane="user",
            idempotency_key=f"run:{self.run_id}:outline:{event_type}:{plan_instance_id}:v{outline_version}:{change_source}",
        )

    def set_current_outline(
        self,
        *,
        plan_state: dict[str, Any],
        mode: str,
        revision_instruction: str | None = None,
    ) -> dict[str, Any]:
        runtime_state = read_outline_runtime_state(self.user_id, self.conversation_id)
        previous_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
        starts_new_instance = _should_start_new_plan_instance(previous_outline)
        current_outline = (
            plan_state.get("outline_state")
            if isinstance(plan_state.get("outline_state"), dict)
            else _build_next_outline_state(
                plan_state={**plan_state, "artifact_type": mode},
                previous_outline=previous_outline,
                status="draft",
            )
        )
        if isinstance(current_outline, dict):
            current_outline = {**(_strip_outline_status(current_outline) or {}), "snapshot_status": "active"}
        if revision_instruction:
            validate_revision_change(
                previous_outline=previous_outline,
                next_outline=current_outline,
                revision_instruction=revision_instruction,
            )

        provided_execution = plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else None
        if isinstance(provided_execution, dict):
            execution_state = {
                **provided_execution,
                "outline_id": current_outline.get("outline_id"),
                "outline_version": int(current_outline.get("version") or 1),
                "status": "planning_ready",
            }
        else:
            execution_state = {**compile_execution_plan(current_outline), "status": "planning_ready"}
        projection_state = build_outline_projection(current_outline, execution_state)
        projection_state = _runtime_projection_status(
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
        )
        change_source = (
            "ai_revision"
            if revision_instruction
            else "initial_plan"
            if previous_outline is None
            else "new_plan_instance"
            if starts_new_instance
            else "replace_current"
        )
        next_runtime = persist_outline_runtime_state(
            self.user_id,
            self.conversation_id,
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
            execution_run=None,
            last_revision=(
                {
                    "mode": "ai_revision",
                    "instruction": revision_instruction,
                    "applied_at": utc_now(),
                }
                if revision_instruction
                else None
            ),
            render_mode="append_history" if change_source in {"ai_revision", "initial_plan", "new_plan_instance"} else "replace_current",
        )
        next_plan_state = {
            **dict(plan_state),
            "status": "planning_ready",
            "outline_state": current_outline,
            "execution_state": execution_state,
            "projection_state": projection_state,
            "user_plan": outline_to_user_plan(current_outline),
        }
        conversation = self._update_conversation_outline_runtime(
            next_runtime,
            phase="planning_ready",
            runtime_status="waiting_input",
            run_state="waiting_input",
            turn_status="waiting_input",
        )
        update_conversation(self.user_id, self.conversation_id, plan_state=next_plan_state)
        conversation["plan_state"] = next_plan_state
        self._publish_outline_event(
            event_type="current_outline_created" if previous_outline is None else "current_outline_updated",
            current_outline=current_outline,
            projection_state=projection_state,
            execution_state=execution_state,
            change_source=change_source,
        )
        return {
            "plan_state": next_plan_state,
            "current_outline": next_runtime.get("current_outline"),
            "execution_state": execution_state,
            "projection_state": projection_state,
            "outline_runtime": next_runtime,
            "conversation": conversation,
            "change_source": change_source,
        }

    def update_execution(self, *, plan_state: dict[str, Any], mode: str) -> dict[str, Any]:
        runtime_state = read_outline_runtime_state(self.user_id, self.conversation_id)
        current_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
        plan_state = dict(plan_state)
        if current_outline:
            current_outline = _strip_outline_status(current_outline)
            execution_state = (
                plan_state.get("execution_state")
                if isinstance(plan_state.get("execution_state"), dict)
                else runtime_state.get("execution_state")
            )
            current_outline = {
                **current_outline,
                "snapshot_status": "finalizing"
                if str((execution_state or {}).get("status") or "").strip().lower() == "completed"
                else str(current_outline.get("snapshot_status") or "active"),
            }
            projection_state = build_outline_projection(current_outline, execution_state if isinstance(execution_state, dict) else None)
            projection_state = _runtime_projection_status(
                current_outline=current_outline,
                execution_state=execution_state if isinstance(execution_state, dict) else None,
                projection_state=projection_state,
            )
            plan_state["outline_state"] = current_outline
            plan_state["projection_state"] = projection_state
            runtime_state = persist_outline_runtime_state(
                self.user_id,
                self.conversation_id,
                current_outline=current_outline,
                execution_state=execution_state if isinstance(execution_state, dict) else None,
                projection_state=projection_state,
                render_mode="replace_current",
                sync_runtime_state=False,
            )
            self._publish_outline_event(
                event_type="execution_projection_updated",
                current_outline=current_outline,
                projection_state=projection_state,
                execution_state=execution_state if isinstance(execution_state, dict) else None,
                change_source="execution_progress",
            )
        update_conversation(self.user_id, self.conversation_id, plan_state=plan_state)
        del mode
        return {
            "plan_state": plan_state,
            "current_outline": current_outline,
            "outline_runtime": runtime_state,
            "change_source": "execution_progress",
        }

    def patch_current_outline(self, *, plan: dict[str, Any], sync_runtime_state: bool = True) -> dict[str, Any]:
        runtime_state = read_outline_runtime_state(self.user_id, self.conversation_id)
        current_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
        if current_outline is None:
            current_outline = outline_from_user_plan(plan, status="draft")
        current_outline = _strip_outline_status(current_outline) or current_outline
        execution_status = str(
            (
                runtime_state.get("execution_state")
                if isinstance(runtime_state.get("execution_state"), dict)
                else {}
            ).get("status")
            or ""
        ).strip().lower()
        if execution_status in {"in_progress", "running", "finalizing", "completed", "failed", "blocked", "cancelled"}:
            raise ValueError("当前计划已开始执行，请重新生成新的计划后再修改大纲。")
        try:
            current_outline, execution_state, projection_state = apply_outline_patch(
                current_outline,
                items=[item for item in list(plan.get("items") or []) if isinstance(item, dict)],
                title=str(plan.get("title") or current_outline.get("title") or ""),
                summary=str(plan.get("summary") or current_outline.get("summary") or ""),
                constraints=_normalize_constraints(plan.get("constraints")),
                style_notes=_normalize_constraints(plan.get("style_notes")),
            )
        except OutlineLockedError:
            raise
        current_outline = {**(_strip_outline_status(current_outline) or {}), "snapshot_status": "active"}
        execution_state = {**execution_state, "status": "planning_ready"}
        projection_state = build_outline_projection(current_outline, execution_state)
        projection_state = _runtime_projection_status(
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
        )
        next_runtime = persist_outline_runtime_state(
            self.user_id,
            self.conversation_id,
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
            last_revision={
                "mode": "structured_edit",
                "dirty": True,
                "applied_at": utc_now(),
            },
            render_mode="replace_current",
            sync_runtime_state=sync_runtime_state,
        )
        plan_state = self._plan_state_snapshot()
        if plan_state:
            plan_state["status"] = "planning_ready"
            plan_state["outline_state"] = current_outline
            plan_state["execution_state"] = execution_state
            plan_state["projection_state"] = projection_state
            plan_state["user_plan"] = outline_to_user_plan(current_outline)
            update_conversation(self.user_id, self.conversation_id, plan_state=plan_state)
        self._update_conversation_outline_runtime(
            next_runtime,
            phase="planning_ready",
            runtime_status="waiting_input",
            run_state="waiting_input",
            turn_status="waiting_input",
        )
        self._publish_outline_event(
            event_type="current_outline_updated",
            current_outline=current_outline,
            projection_state=projection_state,
            execution_state=execution_state,
            change_source="manual_patch",
        )
        return {
            "current_outline": current_outline,
            "execution_state": execution_state,
            "projection_state": projection_state,
            "outline_runtime": next_runtime,
            "plan_state": plan_state,
            "change_source": "manual_patch",
        }

    def start_execution(self) -> dict[str, Any]:
        runtime_state = read_outline_runtime_state(self.user_id, self.conversation_id)
        current_outline = runtime_state.get("current_outline") if isinstance(runtime_state.get("current_outline"), dict) else None
        if not isinstance(current_outline, dict):
            raise ValueError("当前没有可执行的大纲。")
        current_outline = _strip_outline_status(current_outline) or current_outline
        execution_state = runtime_state.get("execution_state") if isinstance(runtime_state.get("execution_state"), dict) else compile_execution_plan(current_outline)
        current_outline = {**current_outline, "status": "executing", "snapshot_status": "executing"}
        execution_state = {
            **execution_state,
            "outline_id": current_outline.get("outline_id"),
            "outline_version": int(current_outline.get("version") or 1),
            "status": "in_progress",
        }
        projection_state = build_outline_projection(current_outline, execution_state)
        projection_state = _runtime_projection_status(
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
        )
        execution_run = {
            "status": "in_progress",
            "locked_outline_id": current_outline.get("outline_id"),
            "locked_outline_version": int(current_outline.get("version") or 1),
            "locked_plan_instance_id": current_outline.get("plan_instance_id"),
            "locked_outline_snapshot": current_outline,
            "started_at": utc_now(),
        }
        next_runtime = persist_outline_runtime_state(
            self.user_id,
            self.conversation_id,
            current_outline=current_outline,
            execution_state=execution_state,
            projection_state=projection_state,
            execution_run=execution_run,
            last_revision=None,
            render_mode="replace_current",
        )
        plan_state = self._plan_state_snapshot()
        plan_state["status"] = "in_progress"
        plan_state["outline_state"] = current_outline
        plan_state["execution_state"] = execution_state
        plan_state["projection_state"] = projection_state
        user_plan = outline_to_user_plan(current_outline) or {}
        user_plan["readonly"] = True
        plan_state["user_plan"] = user_plan
        update_conversation(self.user_id, self.conversation_id, plan_state=plan_state)
        self._update_conversation_outline_runtime(
            next_runtime,
            phase="executing",
            runtime_status="running",
            run_state="executing",
            turn_status="running",
        )
        self._publish_outline_event(
            event_type="execution_started",
            current_outline=current_outline,
            projection_state=projection_state,
            execution_state=execution_state,
            change_source="execution_started",
        )
        return {
            "current_outline": current_outline,
            "execution_state": execution_state,
            "projection_state": projection_state,
            "execution_run": execution_run,
            "outline_runtime": next_runtime,
            "plan_state": plan_state,
            "change_source": "execution_started",
        }


def build_plan_context_block(
    plan_state: dict[str, Any] | None,
    *,
    current_outline: dict[str, Any] | None = None,
    language: str,
) -> str | None:
    if not isinstance(plan_state, dict) and not isinstance(current_outline, dict):
        return None
    execution_state = (plan_state or {}).get("execution_state") if isinstance((plan_state or {}).get("execution_state"), dict) else {}
    compact = {
        "current_outline": current_outline,
        "execution_steps": [
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "status": step.get("status"),
                "description": step.get("description"),
                "outline_item_ids": step.get("outline_item_ids"),
            }
            for step in list(execution_state.get("steps") or (plan_state or {}).get("steps") or [])
            if isinstance(step, dict)
        ],
        "current_item_id": execution_state.get("current_item_id") or (plan_state or {}).get("current_item_id"),
        "plan_status": (plan_state or {}).get("status"),
    }
    body = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if language == "zh":
        return (
            "当前大纲与执行状态：\n"
            f"{body}\n"
            "current_outline 是当前内容蓝图。执行内容时必须遵守 current_outline。"
            "execution_steps 只用于执行推进和恢复，不要把技术步骤写进用户大纲。"
            "执行到某一页、某一章、某一讲讲义或某一部分时，请在 update_execution_progress.current_item_id 中填写对应 current_outline 条目 ID。"
            "执行进度只通过 steps[].status 表达；最多只能有一个 steps 条目标记为 in_progress。"
            "普通 assistant 文本中的进展描述不算计划更新。"
            "调用 update_execution_progress 时始终传完整结构：title、summary、完整 steps；不要只传 steps，也不要用 raw 包裹 JSON。"
            "开始执行前先调用一次 `update_execution_progress`。每完成一个步骤，立刻调用一次 `update_execution_progress`。"
            "如果一次工具执行超过一段时间且尚未完成，也要补一次阶段性 `update_execution_progress`。"
            "执行中继续调用 `update_execution_progress` 更新 steps 状态和进度。"
            "在最终答复前再次调用 update_execution_progress，同步最新完成状态。"
        )
    return (
        "Current outline and execution state:\n"
        f"{body}\n"
        "current_outline is the current content blueprint. Follow current_outline when generating deliverables. "
        "execution_steps are only for execution progress and recovery, not for user-facing outline content. "
        "When execution is focused on a specific page, chapter, course handout, or approved outline item, include that outline item id in update_execution_progress.current_item_id. "
        "Represent execution progress only through steps[].status; at most one step may be in_progress. "
        "Normal assistant progress text does not count as a plan update. "
        "Always call update_execution_progress with the full structured payload: title, summary, and the complete steps list; do not send steps only or wrap JSON in raw. "
        "Call `update_execution_progress` once before starting execution. Call `update_execution_progress` immediately after a step is completed. "
        "If a tool call runs for a while and is still not finished, add another stage update with `update_execution_progress`. "
        "Keep calling update_execution_progress during execution to update step state and progress. "
        "Before the final user-facing answer, call `update_execution_progress` again so the plan card reflects the latest completed state."
    )


def plan_has_unfinished_steps(plan_state: dict[str, Any] | None, *, execution_locked: bool) -> bool:
    if not execution_locked or not isinstance(plan_state, dict):
        return False
    status = str(plan_state.get("status") or "").lower()
    if status == "completed":
        return False
    steps = [step for step in list(plan_state.get("steps") or []) if isinstance(step, dict)]
    if not steps:
        return status not in {"", "completed"}
    return any(str(step.get("status") or "").lower() != "completed" for step in steps)
