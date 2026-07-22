from __future__ import annotations

import json
from typing import Any

from app.schemas.harness import HarnessGenerationRetryRead
from app.services.agent_harness.core.context import create_context
from app.services.agent_harness.core.utils import generation_store
from app.services.agent_harness.generation_artifact_retry_coordinator import (
    GenerationArtifactRetryCoordinator,
)
from app.services.agent_harness.workspace.conversation import conversation_meta_store


class HarnessGenerationRetryNotFoundError(Exception):
    pass


class HarnessGenerationRetryValidationError(Exception):
    pass


def _load_retry_context(*, user_id: int, conversation_id: str):
    conversation = conversation_meta_store.get_conversation(user_id, conversation_id)
    if not conversation:
        raise HarnessGenerationRetryNotFoundError("Conversation not found")

    return create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id="_generation_retry",
        conversation=conversation,
    )


def _parse_tool_error(result_output: str) -> dict[str, Any]:
    try:
        data = json.loads(result_output or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _build_retry_read(
    *,
    task_id: str,
    artifact_ref: str,
    status: str,
    auto_retry_count: int,
    auto_retry_max: int,
    manual_retry_count: int,
    error_message: str | None = None,
    canvas_item: dict[str, Any] | None = None,
    result_url: str | None = None,
    model_name: str | None = None,
    model_label: str | None = None,
    prompt: str | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    duration: int | str | None = None,
) -> HarnessGenerationRetryRead:
    return HarnessGenerationRetryRead(
        task_id=task_id,
        artifact_ref=artifact_ref,
        auto_retry_count=auto_retry_count,
        auto_retry_max=auto_retry_max,
        manual_retry_count=manual_retry_count,
        status=status,
        error_message=error_message,
        canvas_item=canvas_item,
        result_url=result_url,
        model_name=model_name,
        model_label=model_label,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration=duration,
    )


async def retry_generation_artifact(
    *,
    user_id: int,
    conversation_id: str,
    artifact_ref: str,
) -> HarnessGenerationRetryRead:
    ctx = _load_retry_context(
        user_id=user_id,
        conversation_id=conversation_id,
    )

    artifact = generation_store.read_artifact(ctx, artifact_ref)
    if not artifact:
        raise HarnessGenerationRetryNotFoundError("Artifact not found")

    current_task_id = str(artifact.get("current_task_id") or "").strip()
    retry_coordinator = GenerationArtifactRetryCoordinator()
    guard = await retry_coordinator.start(
        conversation_id=conversation_id,
        artifact_ref=artifact_ref,
        current_task_id=current_task_id,
        source="manual",
    )
    if not guard.acquired:
        latest_artifact = generation_store.read_artifact(ctx, artifact_ref) or artifact
        status = guard.status or {}
        task_id = str(
            status.get("task_id")
            or status.get("current_task_id")
            or latest_artifact.get("current_task_id")
            or current_task_id
            or ""
        )
        return _build_retry_read(
            task_id=task_id,
            artifact_ref=artifact_ref,
            auto_retry_count=int(latest_artifact.get("auto_retry_count") or 0),
            auto_retry_max=int(latest_artifact.get("auto_retry_max") or 3),
            manual_retry_count=int(latest_artifact.get("manual_retry_count") or 0),
            status="already_running",
            error_message="generation_retry_already_running",
            canvas_item=latest_artifact.get("canvas_item") if isinstance(latest_artifact.get("canvas_item"), dict) else None,
            result_url=latest_artifact.get("result_url"),
            model_name=latest_artifact.get("model_name"),
            model_label=latest_artifact.get("model_label"),
            prompt=latest_artifact.get("prompt"),
            aspect_ratio=latest_artifact.get("aspect_ratio"),
            resolution=latest_artifact.get("resolution"),
            duration=latest_artifact.get("duration"),
        )

    try:
        result = await generation_store.retry_artifact(ctx, artifact_ref, source="manual")
    except KeyError as exc:
        await retry_coordinator.fail(guard, artifact_ref=artifact_ref, error_type="not_found")
        raise HarnessGenerationRetryNotFoundError("Artifact not found") from exc
    except (RuntimeError, ValueError) as exc:
        await retry_coordinator.fail(guard, artifact_ref=artifact_ref, error_type=type(exc).__name__)
        raise HarnessGenerationRetryValidationError(str(exc)) from exc

    if getattr(result, "is_error", False):
        data = _parse_tool_error(result.output)
        latest_artifact = generation_store.read_artifact(ctx, artifact_ref) or artifact
        await retry_coordinator.fail(guard, artifact_ref=artifact_ref, error_type=str(data.get("error") or "retry_failed"))
        return _build_retry_read(
            task_id=str(data.get("task_id") or ""),
            artifact_ref=str(data.get("artifact_ref") or artifact_ref),
            auto_retry_count=int(data.get("auto_retry_count") or latest_artifact.get("auto_retry_count") or 0),
            auto_retry_max=int(data.get("auto_retry_max") or latest_artifact.get("auto_retry_max") or 3),
            manual_retry_count=int(data.get("manual_retry_count") or latest_artifact.get("manual_retry_count") or 0),
            status="failed",
            error_message=(
                data.get("message")
                or data.get("error_message")
                or data.get("error")
                or "generation_failed"
            ),
            canvas_item=latest_artifact.get("canvas_item") if isinstance(latest_artifact.get("canvas_item"), dict) else None,
        )

    metadata = (result.metadata or {}) if hasattr(result, "metadata") else {}
    read = _build_retry_read(
        task_id=str(metadata.get("task_id") or ""),
        artifact_ref=str(metadata.get("artifact_ref") or artifact_ref),
        auto_retry_count=int(metadata.get("auto_retry_count") or 0),
        auto_retry_max=int(metadata.get("auto_retry_max") or 3),
        manual_retry_count=int(metadata.get("manual_retry_count") or 0),
        status=str(metadata.get("status") or "processing"),
        error_message=None,
        canvas_item=metadata.get("canvas_item") if isinstance(metadata.get("canvas_item"), dict) else None,
        result_url=metadata.get("result_url"),
        model_name=metadata.get("model_name"),
        model_label=metadata.get("model_label"),
        prompt=metadata.get("prompt"),
        aspect_ratio=metadata.get("aspect_ratio"),
        resolution=metadata.get("resolution"),
        duration=metadata.get("duration"),
    )
    await retry_coordinator.finish(
        guard,
        artifact_ref=read.artifact_ref,
        task_id=read.task_id,
        status=read.status,
    )
    return read
