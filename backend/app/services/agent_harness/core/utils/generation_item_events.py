from __future__ import annotations

import logging
from typing import Any

from app.services.agent_harness.runtime.eventing.event_log import append_event_async
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    ITEM_COMPLETED,
    ITEM_STARTED,
    ITEM_UPDATED,
    build_item_completed_payload,
    build_item_started_payload,
    build_item_updated_payload,
    build_turn_error,
)

logger = logging.getLogger(__name__)


def _get(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _params(source: Any) -> dict[str, Any]:
    params = _get(source, "params", {})
    return params if isinstance(params, dict) else {}


def generation_task_item_id(*, task_id: str | int | None, artifact_ref: str | None = None) -> str:
    ref = str(artifact_ref or "").strip()
    if ref:
        return ref
    return f"generation_task:{str(task_id or '').strip()}"


def _kind_from_task(source: Any, fallback: str | None = None) -> str:
    kind = str(_get(source, "kind", "") or fallback or "").strip().lower()
    if kind in {"image", "video"}:
        return kind
    task_type = str(_get(source, "task_type", "") or "").strip().lower()
    return "video" if task_type in {"text2video", "image2video"} else "image"


def build_generation_task_item_payload(
    source: Any,
    *,
    artifact_ref: str | None = None,
    canvas_item: dict[str, Any] | None = None,
    kind: str | None = None,
    result_url: str | None = None,
    result_urls: list[str] | None = None,
    error: str | None = None,
    canvas_revision: int | None = None,
    canvas_item_deleted: bool = False,
) -> dict[str, Any]:
    params = _params(source)
    resolved_artifact_ref = str(
        artifact_ref
        or _get(source, "artifact_ref", None)
        or params.get("artifact_ref")
        or ""
    ).strip() or None
    resolved_canvas_item = (
        canvas_item
        if isinstance(canvas_item, dict)
        else params.get("canvas_item")
        if isinstance(params.get("canvas_item"), dict)
        else _get(source, "canvas_item", None)
    )
    if not isinstance(resolved_canvas_item, dict):
        resolved_canvas_item = None

    task_id = str(_get(source, "task_id", None) or _get(source, "id", "") or "").strip()
    payload: dict[str, Any] = {
        "task_id": task_id,
        "artifact_ref": resolved_artifact_ref,
        "kind": _kind_from_task(source, kind),
        "provider_code": _get(source, "provider_code", None) or params.get("provider_code"),
        "model_name": _get(source, "model_name", None) or params.get("model_name"),
        "model_label": _get(source, "model_label", None) or params.get("model_label"),
        "canvas_item": resolved_canvas_item,
        "progress": _get(source, "progress", None),
    }
    for key in (
        "prompt",
        "aspect_ratio",
        "resolution",
        "duration",
        "quality",
        "planned_result_url",
        "reference_diagnostics",
        "suppress_standard_media_card",
        "presentation_surface",
        "presentation_scope",
        "presentation_message_key",
        "presentation_parent_block_key",
        "presentation_order",
    ):
        value = _get(source, key, None) or params.get(key)
        if value is not None:
            payload[key] = value

    resolved_result_url = result_url if result_url is not None else _get(source, "result_url", None)
    if resolved_result_url is not None:
        payload["result_url"] = resolved_result_url
    resolved_result_urls = result_urls if result_urls is not None else _get(source, "result_urls", None)
    if resolved_result_urls is not None:
        payload["result_urls"] = resolved_result_urls
    resolved_error = error if error is not None else _get(source, "error", None) or _get(source, "error_message", None)
    if resolved_error is not None:
        payload["error"] = resolved_error
    if canvas_revision is not None:
        payload["canvas_revision"] = canvas_revision
    if canvas_item_deleted:
        payload["canvas_item_deleted"] = True

    return payload


async def emit_generation_item_started(
    ctx: Any,
    source: Any,
    *,
    artifact_ref: str | None = None,
    canvas_item: dict[str, Any] | None = None,
    kind: str | None = None,
    canvas_revision: int | None = None,
    canvas_item_deleted: bool = False,
) -> dict[str, Any] | None:
    task_id = str(_get(source, "task_id", None) or _get(source, "id", "") or "").strip()
    item_id = generation_task_item_id(task_id=task_id, artifact_ref=artifact_ref or _params(source).get("artifact_ref"))
    payload = build_generation_task_item_payload(
        source,
        artifact_ref=artifact_ref,
        canvas_item=canvas_item,
        kind=kind,
        canvas_revision=canvas_revision,
        canvas_item_deleted=canvas_item_deleted,
    )
    return await _append_generation_item_event(
        ctx,
        event_type=ITEM_STARTED,
        item_id=item_id,
        status="running",
        payload=build_item_started_payload(
            conversation_id=str(ctx.conversation_id),
            run_id=str(ctx.run_id),
            item_id=item_id,
            item_type="generation_task",
            status="running",
            payload=payload,
        ),
        idempotency_key=f"run:{ctx.run_id}:generation:{item_id}:started",
    )


async def emit_generation_item_updated(
    ctx: Any,
    source: Any,
    *,
    artifact_ref: str | None = None,
    canvas_item: dict[str, Any] | None = None,
    kind: str | None = None,
    canvas_revision: int | None = None,
    canvas_item_deleted: bool = False,
) -> dict[str, Any] | None:
    task_id = str(_get(source, "task_id", None) or _get(source, "id", "") or "").strip()
    params = _params(source)
    item_id = generation_task_item_id(task_id=task_id, artifact_ref=artifact_ref or params.get("artifact_ref"))
    status = str(_get(source, "status", None) or params.get("status") or "running").strip().lower()
    if status == "processing":
        status = "running"
    progress = _get(source, "progress", None)
    payload = build_generation_task_item_payload(
        source,
        artifact_ref=artifact_ref,
        canvas_item=canvas_item,
        kind=kind,
        canvas_revision=canvas_revision,
        canvas_item_deleted=canvas_item_deleted,
    )
    return await _append_generation_item_event(
        ctx,
        event_type=ITEM_UPDATED,
        item_id=item_id,
        status=status or "running",
        payload=build_item_updated_payload(
            conversation_id=str(ctx.conversation_id),
            run_id=str(ctx.run_id),
            item_id=item_id,
            item_type="generation_task",
            status=status or "running",
            payload=payload,
        ),
        idempotency_key=f"run:{ctx.run_id}:generation:{item_id}:status:{status or 'running'}:{progress}",
    )


async def emit_generation_item_completed(
    ctx: Any,
    source: Any,
    *,
    artifact_ref: str | None = None,
    canvas_item: dict[str, Any] | None = None,
    kind: str | None = None,
    status: str | None = None,
    result_url: str | None = None,
    result_urls: list[str] | None = None,
    error: str | None = None,
    canvas_revision: int | None = None,
    canvas_item_deleted: bool = False,
) -> dict[str, Any] | None:
    task_id = str(_get(source, "task_id", None) or _get(source, "id", "") or "").strip()
    params = _params(source)
    item_id = generation_task_item_id(task_id=task_id, artifact_ref=artifact_ref or params.get("artifact_ref"))
    resolved_status = str(status or _get(source, "status", None) or "completed").strip().lower()
    if resolved_status not in {"completed", "failed", "cancelled"}:
        resolved_status = "completed"
    summary = error if error is not None else _get(source, "error", None) or _get(source, "error_message", None)
    payload = build_generation_task_item_payload(
        source,
        artifact_ref=artifact_ref,
        canvas_item=canvas_item,
        kind=kind,
        result_url=result_url,
        result_urls=result_urls,
        error=str(summary) if summary else None,
        canvas_revision=canvas_revision,
        canvas_item_deleted=canvas_item_deleted,
    )
    return await _append_generation_item_event(
        ctx,
        event_type=ITEM_COMPLETED,
        item_id=item_id,
        status=resolved_status,
        payload=build_item_completed_payload(
            conversation_id=str(ctx.conversation_id),
            run_id=str(ctx.run_id),
            item_id=item_id,
            item_type="generation_task",
            status=resolved_status,
            payload=payload,
            error=build_turn_error("generation_task_failed", str(summary or "Generation failed."))
            if resolved_status == "failed"
            else None,
        ),
        idempotency_key=f"run:{ctx.run_id}:generation:{item_id}:completed:{resolved_status}",
    )


async def _append_generation_item_event(
    ctx: Any,
    *,
    event_type: str,
    item_id: str,
    status: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any] | None:
    try:
        return await append_event_async(
            int(ctx.user_id),
            str(ctx.conversation_id),
            run_id=str(ctx.run_id),
            event_type=event_type,
            payload=payload,
            lane="user",
            artifact_id=item_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception(
            "Failed to append generation item event %s for task item %s with status %s",
            event_type,
            item_id,
            status,
        )
        return None
