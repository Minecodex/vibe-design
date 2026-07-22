from __future__ import annotations

from typing import Any

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.core.utils.artifacts import build_artifact_metadata
from app.services.agent_harness.core.utils.media_download import download_media_to_workspace
from app.services.agent_harness.canvas.project_media_sync import publish_canvas_generated_media
from app.services.agent_harness.runtime.eventing.presentation import build_media_card_for_tool
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.publisher import publish_presentation_event


def tool_name_for_generation_kind(kind: str) -> str:
    return "generate_video" if str(kind or "").lower() == "video" else "generate_image"


def updated_canvas_item(
    canvas_item: dict[str, Any] | None,
    *,
    result_url: str,
    status: str,
) -> dict[str, Any] | None:
    if not isinstance(canvas_item, dict):
        return None
    next_item = dict(canvas_item)
    next_item["url"] = result_url or ""
    next_item["status"] = status
    return next_item


def result_payload_for_generation_task(
    ctx: HarnessContext,
    *,
    task_id: str,
    task: dict[str, Any],
    artifact: dict[str, Any] | None,
    status: str,
    result_url: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    artifact_result_url = (
        result_url
        or (artifact or {}).get("result_url")
        or task.get("result_url")
        or (artifact or {}).get("planned_result_url")
        or task.get("planned_result_url")
    )
    return {
        "artifact_ref": (artifact or {}).get("artifact_ref") or task.get("artifact_ref"),
        "task_id": task_id,
        "status": status,
        "result_url": artifact_result_url,
        "artifact": build_artifact_metadata(artifact_result_url, ctx),
        "canvas_item": task.get("canvas_item") or (artifact or {}).get("canvas_item"),
        "canvas_revision": task.get("canvas_revision") or (artifact or {}).get("canvas_revision"),
        "canvas_item_deleted": bool(task.get("canvas_item_deleted") or (artifact or {}).get("canvas_item_deleted")),
        "prompt": task.get("prompt"),
        "provider_code": task.get("provider_code"),
        "model_name": task.get("model_name"),
        "model_label": task.get("model_label"),
        "resolution": task.get("resolution"),
        "aspect_ratio": task.get("aspect_ratio"),
        "duration": task.get("duration"),
        "reference_diagnostics": task.get("reference_diagnostics") or (artifact or {}).get("reference_diagnostics"),
        "error_message": error,
    }


def _presentation_scope_from_generation_task(task: dict[str, Any], artifact: dict[str, Any] | None) -> dict[str, str | None]:
    for source in (task.get("presentation_scope"), (artifact or {}).get("presentation_scope")):
        if not isinstance(source, dict):
            continue
        message_key = str(source.get("message_key") or source.get("messageKey") or "").strip()
        parent_block_key = str(source.get("parent_block_key") or source.get("parentBlockKey") or "").strip()
        if message_key or parent_block_key:
            return {
                "message_key": message_key or None,
                "parent_block_key": parent_block_key or None,
            }
    message_key = str(task.get("presentation_message_key") or (artifact or {}).get("presentation_message_key") or "").strip()
    parent_block_key = str(
        task.get("presentation_parent_block_key")
        or (artifact or {}).get("presentation_parent_block_key")
        or ""
    ).strip()
    if message_key or parent_block_key:
        return {
            "message_key": message_key or None,
            "parent_block_key": parent_block_key or None,
        }
    return {}


def publish_generation_media_update(
    ctx: HarnessContext,
    *,
    task_id: str,
    task: dict[str, Any],
    artifact: dict[str, Any] | None,
    status: str,
    result_url: str | None = None,
    error: str | None = None,
) -> None:
    payload = result_payload_for_generation_task(
        ctx,
        task_id=task_id,
        task=task,
        artifact=artifact,
        status=status,
        result_url=result_url,
        error=error,
    )
    block = build_media_card_for_tool(
        tool_name=tool_name_for_generation_kind(str(task.get("kind") or "")),
        call_id=str(task.get("tool_call_id") or task_id),
        result_payload=payload,
        status=status,
    )
    block_key = str(block.get("block_key") or block.get("id") or f"media-task-{task_id}")
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    presentation_scope = _presentation_scope_from_generation_task(task, artifact)
    op_payload = presentation_v2.content_block_upsert(
        conversation_id=ctx.conversation_id,
        run_id=ctx.run_id,
        block_key=block_key,
        ui_kind=str(block.get("ui_kind") or block.get("uiKind") or "media_card"),
        status=status,
        payload=payload,
        message_key=presentation_scope.get("message_key"),
        parent_block_key=presentation_scope.get("parent_block_key"),
        order=int(task.get("presentation_order") or (artifact or {}).get("presentation_order") or block.get("order") or 0),
        kind=str(block.get("kind") or "content"),
        complete=str(status or "").strip().lower() in {"completed", "failed", "cancelled"},
    )
    op_payload["block"] = {**block, **op_payload["block"], "payload": payload}
    publish_presentation_event(
        ctx.user_id,
        ctx.conversation_id,
        run_id=ctx.run_id,
        draft=presentation_v2.event_draft(
            op_payload,
            block_id=block_key,
            tool_call_id=str(task.get("tool_call_id") or task_id),
        ),
    )


