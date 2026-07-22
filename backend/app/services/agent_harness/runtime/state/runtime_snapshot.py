from __future__ import annotations

from typing import Any

from app.services.agent_harness.authoring.planning.step_status import derive_active_step
from app.services.agent_harness.runtime.execution_support.failure_contract import build_failure_payload, failure_from_recovery_summary


_REVIEW_PHASES = {"discovery", "visual_lock", "planning", "planning_ready", "awaiting_plan_review", "revising_plan"}
_RUN_STATUS_BY_PHASE = {
    "skill_resolving": "running",
    "discovery": "waiting_input",
    "visual_lock": "waiting_input",
    "planning": "running",
    "planning_ready": "waiting_input",
    "revising_plan": "revising",
    "executing": "running",
    "completed": "completed",
    "failed": "failed",
}


def _normalize_items(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [item for item in list((plan or {}).get("items") or []) if isinstance(item, dict)]


def _derive_run_status(*, phase: str, runtime_status: str, user_run_status: str | None) -> str:
    normalized_phase = str(phase or "").lower()
    if normalized_phase in _RUN_STATUS_BY_PHASE:
        return _RUN_STATUS_BY_PHASE[normalized_phase]
    normalized_runtime = str(runtime_status or "").lower()
    if normalized_runtime == "waiting_input":
        return "waiting_review"
    if normalized_runtime == "running":
        return "running"
    if normalized_runtime in {"completed", "failed", "blocked", "cancelled"}:
        return normalized_runtime
    explicit = str(user_run_status or "").strip()
    if explicit:
        return explicit
    return "idle"


def _derive_completed_item_count(*, steps: list[dict[str, Any]], item_count: int, phase: str) -> int:
    if item_count <= 0:
        return 0
    if phase == "completed":
        return item_count
    if phase in _REVIEW_PHASES or not steps:
        return 0
    total_steps = len(steps)
    completed_steps = sum(1 for step in steps if str(step.get("status") or "").lower() == "completed")
    if completed_steps <= 0:
        return 0
    completed_items = int((completed_steps / max(total_steps, 1)) * item_count)
    if completed_items <= 0:
        completed_items = 1
    return min(completed_items, item_count)


def _derive_current_item_index(
    *,
    items: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    explicit_current_item_id: str,
    phase: str,
    completed_item_count: int,
) -> int | None:
    if not items or phase in _REVIEW_PHASES or phase == "completed":
        return None
    if explicit_current_item_id:
        explicit_index = next(
            (
                index
                for index, item in enumerate(items)
                if str(item.get("id") or "") == explicit_current_item_id
            ),
            None,
        )
        if explicit_index is not None:
            return explicit_index
    if phase == "failed":
        if completed_item_count >= len(items):
            return len(items) - 1
        return min(completed_item_count, len(items) - 1)
    if steps:
        active_step = derive_active_step(steps)
        active_step_id = str((active_step or {}).get("id") or "")
        current_step_index = next((index for index, step in enumerate(steps) if str(step.get("id") or "") == active_step_id), None)
        if current_step_index is not None:
            return min(len(items) - 1, int((current_step_index / max(len(steps), 1)) * len(items)))
    if completed_item_count >= len(items):
        return len(items) - 1
    return min(completed_item_count, len(items) - 1)


def _derive_current_action(*, phase: str, runtime_status: str, run_state: str, last_tool: str | None) -> str | None:
    normalized_phase = str(phase or "").lower()
    if normalized_phase == "planning_ready":
        return "ready_to_execute"
    if normalized_phase == "awaiting_plan_review":
        return "awaiting_review"
    if normalized_phase == "discovery":
        return "discovery"
    if normalized_phase == "visual_lock":
        return "visual_lock"
    if normalized_phase == "skill_resolving":
        return "skill_resolving"
    if normalized_phase == "revising_plan":
        return "revising_plan"
    if normalized_phase == "planning":
        return "planning_outline"
    if normalized_phase in {"completed", "failed"}:
        return normalized_phase
    if last_tool:
        return f"running:{last_tool}"
    if run_state:
        return str(run_state)
    if runtime_status:
        return str(runtime_status)
    return None


def _derive_activity(*, source: dict[str, Any], runtime_snapshot: dict[str, Any], phase: str, last_tool: str | None) -> str | None:
    explicit = str(source.get("activity") or runtime_snapshot.get("activity") or "").strip()
    if explicit:
        return explicit
    route = source.get("turn_route")
    if not isinstance(route, dict):
        route = runtime_snapshot.get("turn_route")
    if isinstance(route, dict):
        route_activity = str(route.get("activity") or "").strip()
        if route_activity:
            return route_activity
    if last_tool:
        tool_name = str(last_tool).strip()
        if tool_name in {"web_search", "fetch_webpage"}:
            return "searching"
        if tool_name in {"analyze_image", "analyze_file"}:
            return "analyzing"
        return "executing"
    if phase == "planning":
        return "planning_outline"
    if phase in {"completed", "failed"}:
        return phase
    return None


def _coerce_runtime_failure(
    *,
    source: dict[str, Any],
    runtime_snapshot: dict[str, Any],
    phase: str,
) -> dict[str, Any] | None:
    for candidate in (
        source.get("failure"),
        runtime_snapshot.get("failure"),
    ):
        if isinstance(candidate, dict):
            failure = dict(candidate)
            if "retryable" not in failure:
                failure["retryable"] = phase not in {"completed"}
            return failure

    summary = str(source.get("last_error_summary") or "").strip() or None
    recovery_summary = source.get("recovery_summary")
    if isinstance(recovery_summary, dict):
        derived = failure_from_recovery_summary(
            recovery_summary,
            summary=summary,
            user_visible=bool(summary),
            failure_stage=str(recovery_summary.get("failure_stage") or phase).strip() or None,
            retryable=phase not in {"completed"},
        )
        if derived is not None:
            return derived
    if summary:
        return build_failure_payload(
            failure_kind=str((recovery_summary or {}).get("failure_kind") or "").strip() or None,
            failure_stage=phase,
            user_visible=True,
            summary=summary,
            failure_signature=str((recovery_summary or {}).get("failure_signature") or "").strip() or None,
            retryable=phase not in {"completed"},
        )
    return None


def build_runtime_state_snapshot(
    *,
    conversation_id: str,
    conversation: dict[str, Any] | None,
    outline_runtime_state: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    plan_review_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = conversation or {}
    review_state = outline_runtime_state or _outline_runtime_from_plan_review(plan_review_state)
    runtime_snapshot = runtime_state or {}
    runtime_status = str(source.get("runtime_status") or runtime_snapshot.get("runtime_status") or "")
    run_state = str(source.get("run_state") or runtime_snapshot.get("run_state") or "")
    phase = str(source.get("phase") or runtime_snapshot.get("phase") or "")
    if not phase:
        phase = run_state or "executing"
    if phase == "executing" and str(review_state.get("review_status") or "").lower() in {"awaiting_review", "pending_review"}:
        phase = "awaiting_plan_review"
    if phase == "executing" and run_state in {"skill_resolving", "discovery", "visual_lock", "planning", "revising"}:
        phase = "revising_plan" if run_state == "revising" else run_state
    last_tool = runtime_snapshot.get("last_tool") or source.get("last_tool")
    activity = _derive_activity(
        source=source,
        runtime_snapshot=runtime_snapshot,
        phase=phase,
        last_tool=str(last_tool) if last_tool else None,
    )
    plan_state = source.get("plan_state") if isinstance(source.get("plan_state"), dict) else {}
    execution_state = review_state.get("execution_state") if isinstance(review_state.get("execution_state"), dict) else plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else {}
    projection_state = review_state.get("projection_state") if isinstance(review_state.get("projection_state"), dict) else plan_state.get("projection_state") if isinstance(plan_state.get("projection_state"), dict) else {}
    steps = [step for step in list((execution_state or {}).get("steps") or plan_state.get("steps") or []) if isinstance(step, dict)]
    explicit_current_item_id = str((execution_state or {}).get("current_item_id") or plan_state.get("current_item_id") or "").strip()
    active_plan = review_state.get("current_outline") if isinstance(review_state.get("current_outline"), dict) else None
    projected_items = _normalize_items(projection_state if isinstance(projection_state, dict) else None)
    items = projected_items if projected_items else _normalize_items(active_plan)
    completed_item_count = _derive_completed_item_count(steps=steps, item_count=len(items), phase=phase)
    current_item_index = _derive_current_item_index(
        items=items,
        steps=steps,
        explicit_current_item_id=explicit_current_item_id,
        phase=phase,
        completed_item_count=completed_item_count,
    )
    item_progress: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if phase == "completed":
            status = "completed"
        elif phase in _REVIEW_PHASES:
            status = "pending"
        elif index < completed_item_count:
            status = "completed"
        elif current_item_index is not None and index == current_item_index:
            status = "in_progress"
        else:
            status = "pending"
        item_progress.append(
            {
                "id": str(item.get("id") or f"item-{index + 1}"),
                "title": str(item.get("title") or ""),
                "summary": item.get("summary"),
                "order": int(item.get("order") or (index + 1)),
                "status": status,
                "failure": None,
            }
        )
    current_item_id = None
    if current_item_index is not None and 0 <= current_item_index < len(item_progress):
        current_item_id = item_progress[current_item_index]["id"]
    failure = _coerce_runtime_failure(
        source=source,
        runtime_snapshot=runtime_snapshot,
        phase=phase,
    )
    return {
        "conversation_id": conversation_id,
        "parent_usage_log_id": source.get("parent_usage_log_id") or runtime_snapshot.get("parent_usage_log_id"),
        "updated_at": source.get("last_activity_at") or source.get("updated_at"),
        "phase": phase,
        "run_status": _derive_run_status(
            phase=phase,
            runtime_status=runtime_status,
            user_run_status=str(runtime_snapshot.get("run_status") or "").strip() or None,
        ),
        "current_item_id": current_item_id,
        "current_action": _derive_current_action(
            phase=phase,
            runtime_status=runtime_status,
            run_state=run_state,
            last_tool=str(last_tool) if last_tool else None,
        ),
        "activity": activity,
        "item_progress": item_progress,
        "artifacts": list(runtime_snapshot.get("artifacts") or []),
        "artifact_manifest": (
            runtime_snapshot.get("artifact_manifest")
            if isinstance(runtime_snapshot.get("artifact_manifest"), dict)
            else None
        ),
        "failure": failure,
        "runtime_status": runtime_status or None,
        "turn_status": source.get("turn_status"),
        "run_state": run_state or None,
        "run_id": source.get("run_id"),
        "last_tool": last_tool,
        "discovery_status": str(
            runtime_snapshot.get("discovery_status")
            or source.get("discovery_status")
            or ("completed" if phase not in {"discovery"} else "idle")
        ).strip().lower(),
        "discovery_started_at": runtime_snapshot.get("discovery_started_at")
        or source.get("discovery_started_at"),
        "discovery_completed_at": runtime_snapshot.get("discovery_completed_at")
        or source.get("discovery_completed_at"),
        "discovery_payload": (
            runtime_snapshot.get("discovery_payload")
            if isinstance(runtime_snapshot.get("discovery_payload"), dict)
            else None
        ),
        "discovery_schema": (
            list(runtime_snapshot.get("discovery_schema") or [])
            if isinstance(runtime_snapshot.get("discovery_schema"), list)
            else None
        ),
        "prepared_workspace": (
            runtime_snapshot.get("prepared_workspace")
            if isinstance(runtime_snapshot.get("prepared_workspace"), dict)
            else None
        ),
        "workspace_runtime_session": (
            runtime_snapshot.get("workspace_runtime_session")
            if isinstance(runtime_snapshot.get("workspace_runtime_session"), dict)
            else None
        ),
        "runtime_contract": (
            runtime_snapshot.get("runtime_contract")
            if isinstance(runtime_snapshot.get("runtime_contract"), dict)
            else None
        ),
        "turn_route": (
            source.get("turn_route")
            if isinstance(source.get("turn_route"), dict)
            else runtime_snapshot.get("turn_route")
            if isinstance(runtime_snapshot.get("turn_route"), dict)
            else None
        ),
        "model_session_state": (
            runtime_snapshot.get("model_session_state")
            if isinstance(runtime_snapshot.get("model_session_state"), dict)
            else None
        ),
        "user_interaction": (
            source.get("user_interaction")
            if "user_interaction" in source
            else runtime_snapshot.get("user_interaction")
        ),
        "review_status": review_state.get("review_status"),
    }


def _outline_runtime_from_plan_review(plan_review_state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plan_review_state, dict):
        return {}
    active_outline = None
    for key in ("approved_outline", "draft_outline", "draft_plan"):
        candidate = plan_review_state.get(key)
        if isinstance(candidate, dict):
            active_outline = candidate
            break
    return {
        "current_outline": active_outline,
        "projection_state": active_outline,
        "execution_state": {"status": plan_review_state.get("review_status")},
        "review_status": plan_review_state.get("review_status"),
    }

