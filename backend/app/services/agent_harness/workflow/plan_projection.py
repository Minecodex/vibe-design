from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.agent_harness.authoring.planning.outline_plan import (
    build_outline_projection,
    compile_execution_plan,
    outline_to_user_plan,
)

from .contracts import EventSpec
from .status import RUN_KIND_REVISE_PLAN, RUN_KIND_START_PLAN

_TERMINAL_EXECUTION_SNAPSHOT_STATUSES = {"completed", "failed", "blocked", "cancelled"}


def _planning_ready_steps(steps: Any) -> list[dict[str, Any]]:
    return [
        {
            **step,
            "status": "pending",
            "started_at": None,
            "last_activity_at": None,
            "completed_at": None,
            "elapsed_ms": None,
        }
        for step in list(steps or [])
        if isinstance(step, dict)
    ]


def apply_planning_draft_projection(
    *,
    run_id: str,
    step_id: str,
    conversation: dict[str, Any] | None,
    planning_draft: dict[str, Any],
) -> tuple[dict[str, Any], list[EventSpec]]:
    phase = str((conversation or {}).get("phase") or "planning").strip().lower()
    if phase not in {"planning", "revising_plan"}:
        phase = "planning"
    draft = deepcopy(planning_draft)
    runtime_patch = {
        "phase": phase,
        "runtime_status": "running",
        "run_state": "planning" if phase == "planning" else "revising",
        "turn_status": "running",
        "activity": "planning_outline",
        "planning_draft": draft,
    }
    draft_payload = {"planning_draft": draft}
    return runtime_patch, [
        EventSpec(
            event_type="planning_draft_updated",
            payload=draft_payload,
            idempotency_key=f"run:{run_id}:step:{step_id}:event:planning-draft-updated",
        ),
        # Stream the planning-draft card as a live presentation op too. The domain
        # event above only persists the card via the durable projection; without
        # this the draft card would not render until a reload.
        *_render_presentation_event_specs(
            "planning_draft_updated",
            draft_payload,
            idempotency_prefix=f"run:{run_id}:step:{step_id}:event:planning-draft-card",
        ),
    ]


def _render_presentation_event_specs(
    event_type: str,
    payload: dict[str, Any],
    *,
    idempotency_prefix: str,
) -> list[EventSpec]:
    """Build live presentation EventSpecs with the same message/block keys used
    by the durable reducer, so live replay and reload converge on one card."""
    from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
    from app.services.agent_harness.runtime.presentation_v2 import reducer as presentation_reducer

    from .presentation_events import event_spec_from_presentation_draft

    synthetic_event = {"type": event_type, "lane": "user", "sequence": 0, "payload": payload}
    specs: list[EventSpec] = []
    for index, op in enumerate(presentation_reducer.reduce_event_to_ops(synthetic_event)):
        draft = presentation_v2.event_draft(dict(op), idempotency_key=f"{idempotency_prefix}:{index}")
        specs.append(event_spec_from_presentation_draft(draft))
    return specs


def apply_plan_approval_projection(
    *,
    run_id: str,
    step_id: str,
    conversation: dict[str, Any] | None,
    plan_state: dict[str, Any],
) -> tuple[dict[str, Any], list[EventSpec]]:
    next_plan = deepcopy(plan_state)
    outline = (
        next_plan.get("outline_state")
        if isinstance(next_plan.get("outline_state"), dict)
        else None
    )
    execution = (
        next_plan.get("execution_state")
        if isinstance(next_plan.get("execution_state"), dict)
        else None
    )
    if not isinstance(outline, dict):
        raise ValueError("request_plan_approval requires outline_state")
    outline = {**outline, "snapshot_status": "active"}
    next_plan["outline_state"] = outline
    if isinstance(execution, dict):
        execution = {
            **execution,
            "status": "planning_ready",
            "steps": _planning_ready_steps(execution.get("steps")),
        }
    else:
        execution = {**compile_execution_plan(outline), "status": "planning_ready"}
    next_plan["execution_state"] = execution
    projection = build_outline_projection(outline, execution)
    next_plan["projection_state"] = projection
    next_plan["status"] = "planning_ready"
    if not isinstance(next_plan.get("user_plan"), dict):
        next_plan["user_plan"] = outline_to_user_plan(outline)
    current_outline = _current_outline_payload(next_plan)
    runtime_patch = {
        "phase": "planning_ready",
        "runtime_status": "waiting_input",
        "run_state": "waiting_input",
        "turn_status": "waiting_input",
        "activity": "waiting_input",
        "user_interaction": None,
        "plan_state": next_plan,
        "outline_runtime": _outline_runtime_from_plan(
            next_plan, change_source="approval_requested"
        ),
    }
    events = [
        EventSpec(
            event_type="current_outline_updated",
            payload={
                "outline": current_outline,
                "projection": projection,
                "execution_state": execution,
                "change_source": "approval_requested",
            },
            idempotency_key=f"run:{run_id}:step:{step_id}:event:current-outline-approval-requested",
        )
    ]
    if str((conversation or {}).get("phase") or "").strip().lower() == "revising_plan":
        events.append(
            EventSpec(
                event_type="plan_revision_applied",
                payload={
                    "outline": current_outline,
                    "projection": projection,
                    "execution_state": execution,
                },
                idempotency_key=f"run:{run_id}:step:{step_id}:event:plan-revision-applied",
            )
        )
    return runtime_patch, events


def apply_execution_progress_projection(
    *,
    run_id: str,
    step_id: str,
    plan_state: dict[str, Any],
) -> tuple[dict[str, Any], list[EventSpec]]:
    next_plan = deepcopy(plan_state)
    outline = next_plan.get("outline_state") if isinstance(next_plan.get("outline_state"), dict) else None
    execution = next_plan.get("execution_state") if isinstance(next_plan.get("execution_state"), dict) else None
    projection = next_plan.get("projection_state") if isinstance(next_plan.get("projection_state"), dict) else None
    if isinstance(outline, dict) and isinstance(execution, dict):
        status = str(execution.get("status") or next_plan.get("status") or "in_progress").strip().lower()
        if status in _TERMINAL_EXECUTION_SNAPSHOT_STATUSES:
            outline = {**outline, "snapshot_status": status}
            next_plan["outline_state"] = outline
            next_plan["status"] = status
        projection = build_outline_projection(outline, execution)
        next_plan["projection_state"] = projection
        if status in _TERMINAL_EXECUTION_SNAPSHOT_STATUSES:
            user_plan = outline_to_user_plan(outline) or {}
            user_plan["readonly"] = True
            next_plan["user_plan"] = user_plan
    current_outline = _current_outline_payload(next_plan)
    runtime_patch = {
        "phase": "executing",
        "runtime_status": "running",
        "run_state": "executing",
        "turn_status": "running",
        "activity": "executing",
        "plan_state": next_plan,
        "outline_runtime": _outline_runtime_from_plan(
            next_plan, change_source="execution_progress"
        ),
    }
    return runtime_patch, [
        EventSpec(
            event_type="execution_projection_updated",
            payload={
                "outline": current_outline,
                "projection": projection,
                "execution_state": execution,
                "change_source": "execution_progress",
            },
            idempotency_key=f"run:{run_id}:step:{step_id}:event:execution-projection-updated",
        )
    ]


def start_plan_execution_projection(
    *,
    run_id: str,
    step_id: str,
    conversation: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[EventSpec]]:
    plan_state = deepcopy((conversation or {}).get("plan_state") or {})
    outline = (
        plan_state.get("outline_state")
        if isinstance(plan_state.get("outline_state"), dict)
        else None
    )
    if not isinstance(outline, dict):
        raise ValueError("current outline is required before starting execution")
    execution = (
        plan_state.get("execution_state")
        if isinstance(plan_state.get("execution_state"), dict)
        else compile_execution_plan(outline)
    )
    if str(execution.get("status") or "").strip().lower() != "planning_ready":
        raise ValueError("approved planning_ready execution state is required before starting execution")
    outline = {**outline, "snapshot_status": "active"}
    execution = {
        **execution,
        "outline_id": outline.get("outline_id"),
        "outline_version": int(outline.get("version") or 1),
        "status": "in_progress",
    }
    projection = build_outline_projection(outline, execution)
    user_plan = outline_to_user_plan(outline) or {}
    user_plan["readonly"] = True
    plan_state.update(
        {
            "status": "in_progress",
            "outline_state": outline,
            "execution_state": execution,
            "projection_state": projection,
            "user_plan": user_plan,
        }
    )
    current_outline = _current_outline_payload(plan_state)
    run_output_anchor = _run_output_anchor_from_payload(payload)
    runtime_patch = {
        "phase": "executing",
        "runtime_status": "running",
        "run_state": "executing",
        "turn_status": "running",
        "activity": "executing",
        "plan_state": plan_state,
        "run_output_anchor": run_output_anchor,
        "outline_runtime": _outline_runtime_from_plan(
            plan_state, change_source="execution_started"
        ),
    }
    return runtime_patch, [
        EventSpec(
            event_type="execution_started",
            payload={
                "outline": current_outline,
                "projection": projection,
                "execution_state": execution,
                "change_source": "execution_started",
                **run_output_anchor,
            },
            idempotency_key=f"run:{run_id}:step:{step_id}:event:execution-started",
        )
    ]


def _run_output_anchor_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    user_message_event = payload.get("user_message_event") if isinstance(payload, dict) else None
    if not isinstance(user_message_event, dict):
        return {}
    anchor_message_id = str(user_message_event.get("id") or "").strip()
    if not anchor_message_id:
        return {}
    anchor: dict[str, Any] = {
        "anchor_message_id": anchor_message_id,
        "anchor_source": "plan_execution_approved",
    }
    created_at = str(user_message_event.get("created_at") or user_message_event.get("createdAt") or "").strip()
    if created_at:
        anchor["anchor_created_at"] = created_at
    return anchor


def _current_outline_payload(plan_state: dict[str, Any]) -> dict[str, Any] | None:
    outline = (
        plan_state.get("outline_state")
        if isinstance(plan_state.get("outline_state"), dict)
        else None
    )
    if not isinstance(outline, dict):
        return None
    current_outline = dict(outline)
    if isinstance(plan_state.get("execution_state"), dict):
        current_outline["execution_state"] = plan_state["execution_state"]
    if isinstance(plan_state.get("projection_state"), dict):
        current_outline["projection_state"] = plan_state["projection_state"]
    return current_outline


def _outline_runtime_from_plan(
    plan_state: dict[str, Any], *, change_source: str
) -> dict[str, Any]:
    return {
        "current_outline": _current_outline_payload(plan_state),
        "execution_state": (
            deepcopy(plan_state.get("execution_state"))
            if isinstance(plan_state.get("execution_state"), dict)
            else None
        ),
        "projection_state": (
            deepcopy(plan_state.get("projection_state"))
            if isinstance(plan_state.get("projection_state"), dict)
            else None
        ),
        "last_revision": (
            {"mode": change_source}
            if change_source in {"ai_revision", "approval_requested"}
            else None
        ),
    }


def run_kind_from_step_input(input_payload: dict[str, Any]) -> str:
    kind = str(input_payload.get("kind") or "").strip()
    if kind in {RUN_KIND_START_PLAN, RUN_KIND_REVISE_PLAN}:
        return kind
    return kind
