from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from .step_status import normalize_execution_step_statuses
from .user_plan import normalize_artifact_type

OutlineStatus = str
ExecutionStatus = str

class OutlineLockedError(ValueError):
    """Raised when a caller tries to edit an outline after execution starts."""


def _elapsed_ms(started_at: Any, completed_at: Any) -> int | None:
    if not started_at or not completed_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(int((completed - started).total_seconds() * 1000), 0)


def _item_prefix_for_artifact(artifact_type: str) -> str:
    return {
        "ppt": "slide",
        "word": "section",
        "excel": "sheet",
        "html": "section",
    }.get(normalize_artifact_type(artifact_type), "item")


def _ordered_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: int(item.get("order") or 0))


def _extract_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(raw.get("items"), list):
        return [item for item in raw["items"] if isinstance(item, dict)]
    outline = raw.get("outline")
    if isinstance(outline, list):
        return [item for item in outline if isinstance(item, dict)]
    return []


def _normalize_items(
    *,
    artifact_type: str,
    items: list[dict[str, Any]],
    previous_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prefix = _item_prefix_for_artifact(artifact_type)
    previous_by_title = {
        str(item.get("title") or "").strip(): str(item.get("id") or "").strip()
        for item in list(previous_items or [])
        if str(item.get("title") or "").strip() and str(item.get("id") or "").strip()
    }
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        title = str(item.get("title") or "").strip() or f"项目 {index}"
        item_id = str(item.get("id") or "").strip() or previous_by_title.get(title) or f"{prefix}-{index}"
        if item_id in used_ids:
            item_id = f"{prefix}-{index}"
        used_ids.add(item_id)
        normalized.append(
            {
                "id": item_id,
                "title": title,
                "summary": str(item.get("summary") or item.get("description") or "").strip() or None,
                "order": index,
                "artifact_ref": item.get("artifact_ref") or item.get("artifactRef"),
            }
        )
    return normalized


def create_outline_state(
    *,
    artifact_type: str,
    title: str,
    summary: str,
    items: list[dict[str, Any]],
    status: OutlineStatus = "draft",
    version: int = 1,
    outline_id: str | None = None,
    plan_instance_id: str | None = None,
    snapshot_status: str = "active",
    previous_items: list[dict[str, Any]] | None = None,
    constraints: list[str] | None = None,
    style_notes: list[str] | None = None,
) -> dict[str, Any]:
    normalized_artifact_type = normalize_artifact_type(artifact_type)
    return {
        "outline_id": outline_id or f"outline-{uuid.uuid4().hex[:12]}",
        "plan_instance_id": plan_instance_id or f"plan-{uuid.uuid4().hex[:12]}",
        "version": int(version or 1),
        "artifact_type": normalized_artifact_type,
        "title": str(title or "").strip() or "任务大纲",
        "summary": str(summary or "").strip(),
        "snapshot_status": snapshot_status,
        "items": _normalize_items(
            artifact_type=normalized_artifact_type,
            items=items,
            previous_items=previous_items,
        ),
        "constraints": [str(item).strip() for item in list(constraints or []) if str(item).strip()],
        "style_notes": [str(item).strip() for item in list(style_notes or []) if str(item).strip()],
    }


def outline_to_user_plan(outline_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(outline_state, dict):
        return None
    artifact_type = normalize_artifact_type(outline_state.get("artifact_type"))
    items = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "order": item.get("order"),
            "artifact_ref": item.get("artifact_ref"),
        }
        for item in _ordered_items([item for item in list(outline_state.get("items") or []) if isinstance(item, dict)])
    ]
    return {
        "artifact_type": artifact_type,
        "title": str(outline_state.get("title") or ""),
        "summary": str(outline_state.get("summary") or ""),
        "plan_instance_id": outline_state.get("plan_instance_id"),
        "snapshot_status": outline_state.get("snapshot_status"),
        "items": items,
        "outline": items,
        "constraints": list(outline_state.get("constraints") or []),
        "style_notes": list(outline_state.get("style_notes") or []),
        "outline_id": outline_state.get("outline_id"),
        "version": outline_state.get("version"),
        "readonly": str(outline_state.get("snapshot_status") or "") in {"finalizing", "completed", "abandoned"},
    }


def outline_from_user_plan(
    raw_plan: dict[str, Any],
    *,
    previous_outline: dict[str, Any] | None = None,
    status: OutlineStatus = "draft",
) -> dict[str, Any]:
    source = raw_plan if isinstance(raw_plan, dict) else {}
    artifact_type = normalize_artifact_type(source.get("artifact_type") or "other")
    previous_items = previous_outline.get("items") if isinstance(previous_outline, dict) else None
    items = _extract_items(source)
    if not items:
        raise ValueError("user_plan outline is required to build outline state")
    return create_outline_state(
        artifact_type=artifact_type,
        title=str(source.get("title") or "任务大纲"),
        summary=str(source.get("summary") or ""),
        items=items,
        status=status,
        version=int((previous_outline or {}).get("version") or 0) + 1 if previous_outline else 1,
        outline_id=(previous_outline or {}).get("outline_id"),
        plan_instance_id=(previous_outline or {}).get("plan_instance_id"),
        snapshot_status="active",
        previous_items=previous_items if isinstance(previous_items, list) else None,
        constraints=list(source.get("constraints") or []),
        style_notes=list(source.get("style_notes") or source.get("styleNotes") or []),
    )


def compile_execution_plan(outline_state: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in list(outline_state.get("items") or []) if isinstance(item, dict)]
    item_ids = [str(item.get("id")) for item in items if str(item.get("id") or "").strip()]
    if not item_ids:
        item_ids = ["item-1"]
    step_templates = [
        ("research", "检索与整理素材", "收集并整理大纲所需的信息。"),
        ("validate_data", "校验内容依据", "核对关键数据、事实和口径。"),
        ("generate_artifact", "生成交付内容", "按照确认大纲生成交付内容。"),
        ("publish_artifact", "完成交付整理", "整理最终文件并准备交付。"),
    ]
    steps = []
    for index, (step_type, title, description) in enumerate(step_templates, start=1):
        steps.append(
            {
                "id": f"step-{index}",
                "type": step_type,
                "order": index,
                "title": title,
                "description": description,
                "status": "pending",
                "outline_item_ids": list(item_ids),
                "progress_message": None,
                "started_at": None,
                "last_activity_at": None,
                "completed_at": None,
                "elapsed_ms": None,
            }
        )
    return {
        "execution_plan_id": f"exec-{uuid.uuid4().hex[:12]}",
        "outline_id": outline_state.get("outline_id"),
        "outline_version": int(outline_state.get("version") or 1),
        "status": "draft",
        "current_item_id": None,
        "steps": steps,
    }


def execution_state_from_steps(
    *,
    outline_state: dict[str, Any],
    steps: list[dict[str, Any]],
    status: str = "draft",
    current_item_id: str | None = None,
    previous_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item_ids = [
        str(item.get("id"))
        for item in list(outline_state.get("items") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if not item_ids:
        item_ids = ["item-1"]
    item_id_set = set(item_ids)
    normalized_current_item_id = str(current_item_id or "").strip()
    if normalized_current_item_id not in item_id_set:
        normalized_current_item_id = ""
    previous_by_id = {
        str(step.get("id")): step
        for step in list((previous_execution or {}).get("steps") or [])
        if isinstance(step, dict) and str(step.get("id") or "").strip()
    }
    normalized_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(normalize_execution_step_statuses(steps), start=1):
        if not isinstance(raw_step, dict):
            continue
        step_id = str(raw_step.get("id") or f"step-{index}")
        previous_step = previous_by_id.get(step_id) or {}
        started_at = raw_step.get("started_at") or previous_step.get("started_at")
        completed_at = raw_step.get("completed_at") or previous_step.get("completed_at")
        elapsed_ms = raw_step.get("elapsed_ms") or previous_step.get("elapsed_ms")
        if elapsed_ms is None and str(raw_step.get("status") or "pending") == "completed":
            elapsed_ms = _elapsed_ms(started_at, completed_at)
        raw_outline_item_ids = raw_step.get("outline_item_ids") or previous_step.get("outline_item_ids")
        outline_item_ids = [
            str(item_id).strip()
            for item_id in list(raw_outline_item_ids or [])
            if str(item_id).strip() in item_id_set
        ] if isinstance(raw_outline_item_ids, list) else []
        if not outline_item_ids:
            outline_item_ids = [normalized_current_item_id] if normalized_current_item_id else item_ids
        normalized_steps.append(
            {
                "id": step_id,
                "type": str(raw_step.get("type") or previous_step.get("type") or "generate_artifact"),
                "order": int(raw_step.get("order") or index),
                "title": str(raw_step.get("title") or ""),
                "description": raw_step.get("description"),
                "status": str(raw_step.get("status") or "pending"),
                "outline_item_ids": outline_item_ids,
                "progress_message": raw_step.get("progress_message") or previous_step.get("progress_message"),
                "started_at": started_at,
                "last_activity_at": raw_step.get("last_activity_at") or previous_step.get("last_activity_at"),
                "completed_at": completed_at,
                "elapsed_ms": elapsed_ms,
            }
        )
    return {
        "execution_plan_id": str((previous_execution or {}).get("execution_plan_id") or f"exec-{uuid.uuid4().hex[:12]}"),
        "outline_id": outline_state.get("outline_id"),
        "outline_version": int(outline_state.get("version") or 1),
        "status": status,
        "current_item_id": normalized_current_item_id or None,
        "steps": normalized_steps,
    }


def _last_completed_step_for_item(item_id: str, steps: list[dict[str, Any]]) -> str | None:
    related = [
        step for step in steps
        if item_id in [str(value) for value in list(step.get("outline_item_ids") or [])]
    ]
    completed = next((step for step in reversed(related) if str(step.get("status") or "") == "completed"), None)
    return str((completed or {}).get("id") or "").strip() or None


def build_outline_projection(
    outline_state: dict[str, Any] | None,
    execution_state: dict[str, Any] | None,
) -> dict[str, Any]:
    outline = deepcopy(outline_state or {})
    execution = execution_state or {}
    steps = [step for step in list(execution.get("steps") or []) if isinstance(step, dict)]
    projected_items = []
    for item in _ordered_items([item for item in list(outline.get("items") or []) if isinstance(item, dict)]):
        item_id = str(item.get("id") or "")
        projected = dict(item)
        projected["last_completed_step"] = _last_completed_step_for_item(item_id, steps)
        projected["blocked_reason"] = item.get("blocked_reason")
        projected_items.append(projected)
    return {
        "outline_id": outline.get("outline_id"),
        "outline_version": outline.get("version"),
        "plan_instance_id": outline.get("plan_instance_id"),
        "snapshot_status": outline.get("snapshot_status"),
        "execution_plan_id": execution.get("execution_plan_id"),
        "status": str(execution.get("status") or "draft"),
        "artifact_type": normalize_artifact_type(outline.get("artifact_type")),
        "title": str(outline.get("title") or ""),
        "summary": str(outline.get("summary") or ""),
        "items": projected_items,
        "current_item_id": execution.get("current_item_id"),
        "execution_steps": deepcopy(steps),
        "readonly": str(execution.get("status") or "").lower() in {"in_progress", "finalizing", "completed", "failed", "blocked", "cancelled"},
    }


def apply_outline_patch(
    outline_state: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    title: str | None = None,
    summary: str | None = None,
    constraints: list[str] | None = None,
    style_notes: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    current_status = str((outline_state or {}).get("snapshot_status") or "")
    if current_status in {"approved", "executing", "finalizing", "completed", "abandoned"}:
        raise OutlineLockedError("当前计划已开始执行，请重新生成新的计划后再修改大纲。")
    patched = create_outline_state(
        artifact_type=str(outline_state.get("artifact_type") or "other"),
        title=title if title is not None else str(outline_state.get("title") or ""),
        summary=summary if summary is not None else str(outline_state.get("summary") or ""),
        items=items,
        status="draft",
        version=int(outline_state.get("version") or 1) + 1,
        outline_id=str(outline_state.get("outline_id") or ""),
        plan_instance_id=str(outline_state.get("plan_instance_id") or ""),
        previous_items=list(outline_state.get("items") or []),
        constraints=constraints if constraints is not None else list(outline_state.get("constraints") or []),
        style_notes=style_notes if style_notes is not None else list(outline_state.get("style_notes") or []),
    )
    execution = compile_execution_plan(patched)
    projection = build_outline_projection(patched, execution)
    return patched, execution, projection
