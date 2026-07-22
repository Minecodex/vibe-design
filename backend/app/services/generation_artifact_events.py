from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

TERMINAL_PROJECTION_FINALIZED_AT = "terminal_projection_finalized_at"
SUPPRESS_STANDARD_MEDIA_CARD_PARAM = "suppress_standard_media_card"


async def publish_generation_task_artifact_progress_update(task) -> None:
    task_params = getattr(task, "params", None) or {}
    if not isinstance(task_params, dict):
        return
    artifact_ref = str(getattr(task, "artifact_ref", None) or task_params.get("artifact_ref") or "").strip()
    conversation_id = str(
        task_params.get("conversation_id") or task_params.get("agent_conversation_id") or ""
    ).strip()
    if not artifact_ref or not conversation_id:
        return

    try:
        from app.services.agent_harness.core.context import HarnessContext
        from app.services.agent_harness.core.utils import generation_store
        from app.services.agent_harness.core.utils.generation_item_events import (
            emit_generation_item_updated,
        )
        from app.services.agent_harness.core.utils.harness_generation_projection import (
            updated_canvas_item,
        )

        ctx = HarnessContext(
            user_id=task.user_id,
            conversation_id=conversation_id,
            run_id=str(task_params.get("agent_run_id") or "generation-task-poller"),
            runtime_profile="canvas" if task.project_id is not None else "home",
            project_id=task.project_id,
        )
        existing_artifact = generation_store.read_artifact(ctx, artifact_ref) or {}
        status = str(getattr(task, "status", None) or "processing")
        canvas_item = updated_canvas_item(
            task_params.get("canvas_item")
            if isinstance(task_params.get("canvas_item"), dict)
            else existing_artifact.get("canvas_item"),
            result_url=str(existing_artifact.get("result_url") or ""),
            status=status,
        )
        canvas_item, canvas_revision, canvas_item_deleted = await _persist_agent_canvas_item_safely(
            ctx,
            task,
            canvas_item,
            status,
            result_url=str(existing_artifact.get("result_url") or "") or None,
        )
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "status": status,
                "current_task_id": str(task.id),
                "progress": getattr(task, "progress", None),
                "error": None,
                "canvas_item": canvas_item,
                "canvas_revision": canvas_revision,
                "canvas_item_deleted": canvas_item_deleted,
            },
        )
        await emit_generation_item_updated(
            ctx,
            task,
            artifact_ref=artifact_ref,
            canvas_item=canvas_item,
            kind="video" if task.task_type in {"text2video", "image2video"} else "image",
            canvas_revision=canvas_revision,
            canvas_item_deleted=canvas_item_deleted,
        )
    except Exception:
        logger.exception("Failed to update harness generation progress for task %s", task.id)


async def publish_generation_task_artifact_update(task) -> None:
    task_params = getattr(task, "params", None) or {}
    if not isinstance(task_params, dict):
        return
    artifact_ref = str(getattr(task, "artifact_ref", None) or task_params.get("artifact_ref") or "").strip()
    conversation_id = str(
        task_params.get("conversation_id") or task_params.get("agent_conversation_id") or ""
    ).strip()
    if not artifact_ref or not conversation_id:
        return

    try:
        from app.services.agent_harness.core.context import HarnessContext
        from app.services.agent_harness.core.utils import generation_store
        from app.services.agent_harness.core.utils.generation_item_events import (
            emit_generation_item_completed,
        )
        from app.services.agent_harness.core.utils.harness_generation_projection import (
            download_media_to_workspace,
            publish_canvas_generated_media,
            publish_generation_media_update,
            updated_canvas_item,
        )

        ctx = HarnessContext(
            user_id=task.user_id,
            conversation_id=conversation_id,
            run_id=str(task_params.get("agent_run_id") or "generation-task-poller"),
            runtime_profile="canvas" if task.project_id is not None else "home",
            project_id=task.project_id,
        )
        existing_artifact = generation_store.read_artifact(ctx, artifact_ref) or {}
        status = task.status
        if _is_duplicate_terminal_update(existing_artifact, task):
            return

        result_url = None
        internal_result_url = None
        task_result_url = str(getattr(task, "result_url", None) or "").strip()
        existing_result_url = str(existing_artifact.get("result_url") or "").strip()
        existing_internal_result_url = str(existing_artifact.get("internal_result_url") or "").strip()
        if status == "completed" and existing_result_url and existing_internal_result_url:
            result_url = existing_result_url
            internal_result_url = existing_internal_result_url
        elif status == "completed" and task_result_url:
            kind = "video" if task.task_type in {"text2video", "image2video"} else "image"
            ext = "mp4" if kind == "video" else "png"
            internal_result_url = await download_media_to_workspace(
                ctx,
                task_result_url,
                ext_hint=ext,
                media_kind=kind,
                asset_id=str(task_params.get("asset_id") or "").strip() or None,
            )
            result_url = publish_canvas_generated_media(ctx, internal_result_url) or internal_result_url
        elif status == "completed" and existing_result_url:
            result_url = existing_result_url

        canvas_item = updated_canvas_item(
            task_params.get("canvas_item")
            if isinstance(task_params.get("canvas_item"), dict)
            else existing_artifact.get("canvas_item"),
            result_url=result_url or "",
            status=status,
        )
        if status == "failed" and isinstance(canvas_item, dict):
            canvas_item = {
                **canvas_item,
                "error_message": task.error_message,
            }
        canvas_item, canvas_revision, canvas_item_deleted = await _persist_agent_canvas_item_safely(
            ctx,
            task,
            canvas_item,
            status,
            result_url=result_url,
        )
        update = {
            "status": status,
            "current_task_id": str(task.id),
            "result_url": result_url,
            "internal_result_url": internal_result_url,
            "error": task.error_message if status == "failed" else None,
            "canvas_item": canvas_item,
            "canvas_revision": canvas_revision,
            "canvas_item_deleted": canvas_item_deleted,
        }
        artifact = generation_store.update_artifact(ctx, artifact_ref, update)
        resolution = task_params.get("resolution") or (canvas_item or {}).get("resolution")
        aspect_ratio = task_params.get("aspect_ratio") or (canvas_item or {}).get("aspect_ratio")
        projection_task = {
            "task_id": str(task.id),
            "kind": "video" if task.task_type in {"text2video", "image2video"} else "image",
            "artifact_ref": artifact_ref,
            "tool_call_id": task_params.get("tool_call_id"),
            "status": status,
            "result_url": result_url,
            "canvas_item": canvas_item,
            "prompt": getattr(task, "prompt", None)
            or task_params.get("prompt")
            or (canvas_item or {}).get("prompt"),
            "provider_code": getattr(task, "provider_code", None)
            or (canvas_item or {}).get("provider_code"),
            "model_name": getattr(task, "model_name", None)
            or (canvas_item or {}).get("model_name"),
            "model_label": getattr(task, "model_label", None)
            or (canvas_item or {}).get("model_label"),
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration": task_params.get("duration") or (canvas_item or {}).get("duration"),
            "quality": task_params.get("quality") or (canvas_item or {}).get("quality"),
            "presentation_scope": task_params.get("presentation_scope"),
            "presentation_message_key": task_params.get("presentation_message_key"),
            "presentation_parent_block_key": task_params.get("presentation_parent_block_key"),
            "presentation_order": task_params.get("presentation_order"),
            "reference_diagnostics": task_params.get("reference_diagnostics"),
        }
        await emit_generation_item_completed(
            ctx,
            task,
            artifact_ref=artifact_ref,
            canvas_item=canvas_item,
            kind=projection_task["kind"],
            status=status,
            result_url=result_url,
            result_urls=getattr(task, "result_urls", None),
            error=task.error_message if status == "failed" else None,
            canvas_revision=canvas_revision,
            canvas_item_deleted=canvas_item_deleted,
        )
        if not _should_suppress_standard_media_card(task_params, artifact):
            publish_generation_media_update(
                ctx,
                task_id=str(task.id),
                task=projection_task,
                artifact=artifact,
                status=status,
                result_url=result_url,
                error=task.error_message if status == "failed" else None,
            )
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {TERMINAL_PROJECTION_FINALIZED_AT: datetime.now(UTC).isoformat()},
        )
    except Exception:
        logger.exception("Failed to update harness artifact for generation task %s", task.id)


def _is_duplicate_terminal_update(existing_artifact: dict, task) -> bool:
    if not isinstance(existing_artifact, dict):
        return False
    status = getattr(task, "status", None)
    if status not in {"completed", "failed"}:
        return False
    if str(existing_artifact.get("current_task_id") or "") != str(getattr(task, "id", "")):
        return False
    if str(existing_artifact.get("status") or "") != str(status):
        return False
    if not existing_artifact.get(TERMINAL_PROJECTION_FINALIZED_AT):
        return False
    if status == "completed":
        canvas_item = existing_artifact.get("canvas_item")
        if canvas_item is None:
            return bool(existing_artifact.get("result_url"))
        canvas_item_done = (
            isinstance(canvas_item, dict)
            and str(canvas_item.get("status") or "").strip().lower() == "completed"
            and bool(str(canvas_item.get("url") or "").strip())
        )
        return bool(existing_artifact.get("result_url")) and canvas_item_done
    return existing_artifact.get("error") == getattr(task, "error_message", None)


def _should_suppress_standard_media_card(task_params: dict, artifact: dict | None) -> bool:
    if task_params.get(SUPPRESS_STANDARD_MEDIA_CARD_PARAM) is True:
        return True
    return isinstance(artifact, dict) and artifact.get(SUPPRESS_STANDARD_MEDIA_CARD_PARAM) is True


async def _persist_agent_canvas_item_safely(
    ctx,
    task,
    canvas_item: dict | None,
    status: str,
    *,
    result_url: str | None = None,
) -> tuple[dict | None, int | None, bool]:
    try:
        from app.services.agent_harness.canvas.agent_item_persistence import persist_agent_canvas_item_patch

        result = await persist_agent_canvas_item_patch(
            ctx,
            canvas_item,
            status,
            result_url=result_url,
        )
        if result is None:
            return canvas_item, None, False
        return result.canvas_item, result.canvas_revision, result.canvas_item is None
    except Exception:
        logger.exception("Failed to persist agent canvas item for generation task %s", getattr(task, "id", None))
        return canvas_item, None, False
