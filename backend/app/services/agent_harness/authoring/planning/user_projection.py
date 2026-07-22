from __future__ import annotations

import re
from typing import Any

from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.publisher import publish_presentation_event
from .step_status import derive_active_step
from .user_plan import normalize_artifact_type
from .user_plan import validate_user_plan
from .outline_plan import outline_to_user_plan

_TECHNICAL_PROGRESS_RE = re.compile(
    r"代码|脚本|工具|目录|发布|patch|code|script|tool|publish|folder",
    re.IGNORECASE,
)


def build_generic_progress(
    *,
    phase: str,
    status: str | None = None,
    message: str | None = None,
    completed_message: str | None = None,
) -> dict[str, Any]:
    normalized_phase = str(phase or "").lower()
    normalized_status = str(status or "").strip() or (
        "completed" if normalized_phase == "completed" else "in_progress"
    )
    normalized_message = str(message or "").strip()
    if not normalized_message:
        if normalized_phase == "executing_started":
            normalized_message = "开始执行"
        elif normalized_phase == "executing":
            normalized_message = "正在执行"
        elif normalized_phase == "completed":
            normalized_message = "已完成"
        else:
            normalized_message = "正在处理"
    return {
        "status": normalized_status,
        "message": normalized_message,
        "completed_message": str(completed_message or "").strip() or None,
    }


def _default_progress_message(*, artifact_type: str, phase: str) -> str:
    normalized_phase = str(phase or "").lower()
    if normalized_phase == "planning_ready":
        if artifact_type == "ppt":
            return "PPT大纲已准备好"
        if artifact_type == "word":
            return "文档章节已准备好"
        if artifact_type == "excel":
            return "表格结构已准备好"
        if artifact_type == "html":
            return "页面结构已准备好"
        return "当前大纲已准备好"
    return "正在执行"


def build_execution_progress(
    *,
    plan_state: dict[str, Any] | None,
    current_outline: dict[str, Any] | None,
    phase: str,
) -> dict[str, Any]:
    execution_state = (plan_state or {}).get("execution_state") if isinstance((plan_state or {}).get("execution_state"), dict) else {}
    steps = [step for step in list(execution_state.get("steps") or (plan_state or {}).get("steps") or []) if isinstance(step, dict)]
    current_step = derive_active_step(steps)
    completed_step = next((step for step in reversed(steps) if str(step.get("status") or "") == "completed"), None)
    artifact_type = normalize_artifact_type(((current_outline or {}).get("artifact_type")) or "")
    progress_message = str((current_outline or {}).get("progress_message") or "").strip()
    current_step_title = str((current_step or {}).get("title") or "").strip()
    if _TECHNICAL_PROGRESS_RE.search(current_step_title):
        current_step_title = ""
    message = progress_message or current_step_title or _default_progress_message(
        artifact_type=artifact_type,
        phase=phase,
    )
    return {
        "status": str((plan_state or {}).get("status") or "in_progress"),
        "message": message,
        "completed_message": str((completed_step or {}).get("title") or "").strip() or None,
    }


def _phase_from_plan_state(plan_state: dict[str, Any] | None) -> str:
    status = str((plan_state or {}).get("status") or "").lower()
    if status in {"planning_ready"}:
        return "planning_ready"
    if status in {"completed", "failed"}:
        return status
    return "executing"


def build_user_plan(plan_state: dict[str, Any] | None, *, mode: str) -> dict[str, Any]:
    outline_state = (plan_state or {}).get("outline_state") if isinstance((plan_state or {}).get("outline_state"), dict) else None
    if outline_state:
        return outline_to_user_plan(outline_state) or {}
    validation = validate_user_plan(plan_state or {}, mode=mode)
    return validation.normalized_plan if validation.valid else {}


def build_user_progress(plan_state: dict[str, Any] | None, *, mode: str) -> dict[str, Any]:
    outline_state = (plan_state or {}).get("outline_state") if isinstance((plan_state or {}).get("outline_state"), dict) else None
    execution_state = (plan_state or {}).get("execution_state") if isinstance((plan_state or {}).get("execution_state"), dict) else None
    current_outline = build_user_plan(plan_state, mode=mode)
    return build_execution_progress(
        plan_state={**(plan_state or {}), "execution_state": execution_state} if isinstance(execution_state, dict) else plan_state,
        current_outline=current_outline,
        phase=_phase_from_plan_state(plan_state),
    )


def _publish_user_render_ops(
    user_id: int,
    conversation_id: str,
    run_id: str,
    *,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Stream the user-facing render cards for a plan/outline domain event.

    The durable projection already persists these cards by reducing the domain
    event. We also publish reducer-built presentation events so direct live
    streams render the card immediately. Both paths converge on the same
    ``message_key``/``block_key``, so replay and reload update one row/card.
    """
    from app.services.agent_harness.runtime.presentation_v2 import reducer as presentation_reducer

    synthetic_event = {
        "type": event_type,
        "lane": "user",
        "conversation_id": conversation_id,
        "run_id": run_id,
        "sequence": 0,
        "payload": data,
    }
    for op in presentation_reducer.reduce_event_to_ops(synthetic_event):
        publish_presentation_event(
            user_id,
            conversation_id,
            run_id=run_id,
            draft=presentation_v2.event_draft(dict(op)),
        )


def emit_current_outline_updated(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    current_outline: dict[str, Any],
    created: bool,
    change_source: str | None = None,
) -> None:
    projection = current_outline.get("projection_state") if isinstance(current_outline.get("projection_state"), dict) else None
    execution_state = current_outline.get("execution_state") if isinstance(current_outline.get("execution_state"), dict) else None
    event_type = "current_outline_created" if created else "current_outline_updated"
    data = {"outline": current_outline, "projection": projection, "execution_state": execution_state, "change_source": change_source}
    publish_user_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=event_type,
        data=data,
        lane="user",
    )
    _publish_user_render_ops(user_id, conversation_id, run_id, event_type=event_type, data=data)


def emit_execution_started(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    current_outline: dict[str, Any],
    change_source: str | None = "execution_started",
) -> None:
    projection = current_outline.get("projection_state") if isinstance(current_outline.get("projection_state"), dict) else None
    execution_state = current_outline.get("execution_state") if isinstance(current_outline.get("execution_state"), dict) else None
    data = {"outline": current_outline, "projection": projection, "execution_state": execution_state, "change_source": change_source}
    publish_user_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type="execution_started",
        data=data,
        lane="user",
    )
    _publish_user_render_ops(user_id, conversation_id, run_id, event_type="execution_started", data=data)


def emit_execution_progress(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    plan_state: dict[str, Any] | None,
    current_outline: dict[str, Any] | None,
    phase: str,
    progress: dict[str, Any] | None = None,
) -> None:
    payload = progress or build_execution_progress(plan_state=plan_state, current_outline=current_outline, phase=phase)
    publish_presentation_event(
        user_id,
        conversation_id,
        run_id=run_id,
        draft=presentation_v2.event_draft(
            presentation_v2.progress_card(
                conversation_id=conversation_id,
                run_id=run_id,
                progress=payload,
                complete=str(payload.get("status") or "").strip().lower() == "completed",
            ),
        ),
    )


def plan_for_user_state(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    return outline_to_user_plan(plan)
