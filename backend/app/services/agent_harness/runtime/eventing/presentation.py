from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.services.agent_harness.authoring.planning.step_status import normalize_execution_step_statuses


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started_at: Any, completed_at: Any) -> int | None:
    if not started_at or not completed_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(int((completed - started).total_seconds() * 1000), 0)


def _base_block(
    *,
    block_id: str,
    ui_kind: str,
    status: str,
    order: int,
    payload: dict[str, Any],
    render_key: str | None = None,
) -> dict[str, Any]:
    block = {
        "id": block_id,
        "kind": "content",
        "order": order,
        "status": status,
        "visible": True,
        "ui_kind": ui_kind,
        "payload": payload,
        "user_visible": True,
        "debug_only": False,
    }
    if render_key:
        block["render_key"] = render_key
    return block


def _extract_media_identity_value(result_payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = result_payload.get(key)
        if value is None and isinstance(result_payload.get("metadata"), dict):
            value = result_payload["metadata"].get(key)
        text = str(value or "").strip()
        if text:
            return text
    return None


def _safe_media_identity_fragment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value).strip("-")


def _canonical_media_block_identity(
    *,
    call_id: str,
    result_payload: dict[str, Any],
) -> tuple[str, str]:
    artifact_ref = _extract_media_identity_value(result_payload, "artifact_ref", "artifactRef")
    if artifact_ref:
        fragment = _safe_media_identity_fragment(artifact_ref.removeprefix("artifact_ref:")) or _safe_media_identity_fragment(artifact_ref)
        return f"media-artifact-{fragment}", f"media:artifact:{artifact_ref}"
    task_id = _extract_media_identity_value(result_payload, "task_id", "taskId")
    if task_id:
        fragment = _safe_media_identity_fragment(task_id) or "unknown-task"
        return f"media-task-{fragment}", f"media:task:{task_id}"
    return f"media-{call_id}", f"media:call:{call_id}"


def build_media_card_for_tool(
    *,
    tool_name: str,
    call_id: str,
    result_payload: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    normalized_tool = str(tool_name or "").replace("lc_", "")
    analysis_text = (
        result_payload.get("text")
        or result_payload.get("analysis")
        or result_payload.get("summary")
        or ""
    )
    media_type = {
        "generate_image": "image_generation",
        "generate_video": "video_generation",
        "analyze_image": "image_analysis",
    }.get(normalized_tool, "media")
    title = {
        "image_generation": "图片生成",
        "video_generation": "视频生成",
        "image_analysis": "图片分析",
    }.get(media_type, "媒体结果")
    block_id, render_key = _canonical_media_block_identity(call_id=call_id, result_payload=result_payload)
    return _base_block(
        block_id=block_id,
        ui_kind="media_card",
        status=status,
        order=0,
        render_key=render_key,
        payload={
            "tool_name": normalized_tool,
            "call_id": call_id,
            "media_type": media_type,
            "title": title,
            "text": analysis_text,
            "analysis": result_payload.get("analysis"),
            "status": status,
            "artifact_ref": _extract_media_identity_value(result_payload, "artifact_ref", "artifactRef"),
            "task_id": _extract_media_identity_value(result_payload, "task_id", "taskId"),
            "result_url": result_payload.get("result_url") or result_payload.get("resultUrl"),
            "planned_result_url": result_payload.get("planned_result_url") or result_payload.get("plannedResultUrl"),
            "preview_url": (
                result_payload.get("preview_url")
                or result_payload.get("previewUrl")
                or result_payload.get("planned_result_url")
                or result_payload.get("plannedResultUrl")
            ),
            "canvas_revision": result_payload.get("canvas_revision") or result_payload.get("canvasRevision"),
            "canvas_item_deleted": bool(
                result_payload.get("canvas_item_deleted") or result_payload.get("canvasItemDeleted")
            ),
            "artifact": deepcopy(result_payload.get("artifact")) if isinstance(result_payload.get("artifact"), dict) else None,
            "canvas_item": deepcopy(result_payload.get("canvas_item")) if isinstance(result_payload.get("canvas_item"), dict) else None,
            "prompt": result_payload.get("prompt"),
            "provider_code": result_payload.get("provider_code"),
            "model_name": result_payload.get("model_name"),
            "model_label": result_payload.get("model_label"),
            "resolution": result_payload.get("resolution"),
            "aspect_ratio": result_payload.get("aspect_ratio"),
            "duration": result_payload.get("duration"),
            "quality": result_payload.get("quality"),
            "reference_diagnostics": deepcopy(result_payload.get("reference_diagnostics"))
            if isinstance(result_payload.get("reference_diagnostics"), dict)
            else None,
            "error_message": result_payload.get("error_message") or result_payload.get("errorMessage"),
        },
    )


def build_web_search_card_for_tool(
    *,
    call_id: str,
    result_payload: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    results = result_payload.get("ui_results")
    if not isinstance(results, list):
        results = result_payload.get("results")
    return _base_block(
        block_id=f"web-search-{call_id}",
        ui_kind="web_search_card",
        status=status,
        order=0,
        payload={
            "call_id": call_id,
            "query": result_payload.get("query") or "",
            "search_type": result_payload.get("search_type") or "text",
            "message": result_payload.get("message") or "",
            "results": deepcopy(results) if isinstance(results, list) else [],
            "status": status,
        },
    )


def normalize_plan_state(
    *,
    title: str,
    summary: str,
    steps: list[dict[str, Any]],
    current_item_id: str | None = None,
    status: str,
    previous_plan_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_steps = {
        str(step.get("id") or ""): step
        for step in list((previous_plan_state or {}).get("steps") or [])
        if isinstance(step, dict)
    }
    normalized_steps: list[dict[str, Any]] = []
    input_steps = normalize_execution_step_statuses(steps)
    now = _now_iso()

    for index, raw_step in enumerate(input_steps, start=1):
        step_id = str(raw_step.get("id") or f"step-{index}")
        previous = previous_steps.get(step_id, {})
        raw_status = str(raw_step.get("status") or "pending")

        started_at = previous.get("started_at")
        completed_at = previous.get("completed_at")
        elapsed_ms = previous.get("elapsed_ms")

        if raw_status in {"in_progress", "completed"} and not started_at:
            started_at = now
        if raw_status == "completed":
            completed_at = completed_at or now
            if elapsed_ms is None:
                elapsed_ms = _elapsed_ms(started_at, completed_at)
        else:
            completed_at = None
            if raw_status != "completed":
                elapsed_ms = previous.get("elapsed_ms")

        normalized_steps.append(
            {
                "id": step_id,
                "order": int(raw_step.get("order") or index),
                "title": str(raw_step.get("title") or "").strip(),
                "description": str(raw_step.get("description") or "").strip(),
                "status": raw_status,
                "started_at": started_at,
                "last_activity_at": now if raw_status in {"in_progress", "completed"} else previous.get("last_activity_at"),
                "completed_at": completed_at,
                "elapsed_ms": elapsed_ms,
            }
        )

    plan_status = status
    if normalized_steps and all(step["status"] == "completed" for step in normalized_steps):
        plan_status = "completed"
    elif any(step["status"] == "in_progress" for step in normalized_steps):
        plan_status = "in_progress"
    else:
        plan_status = "pending"

    return {
        "title": title,
        "summary": summary,
        "current_item_id": str(current_item_id or "").strip() or None,
        "status": plan_status,
        "steps": normalized_steps,
    }
