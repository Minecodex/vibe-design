"""Filesystem-backed generation artifact metadata for harness tools.

Generation task state lives in the shared ``generation_tasks`` table.  This
module only persists lightweight artifact metadata under each conversation so
artifact refs, retry counters, and canvas projections can survive process
restarts without reintroducing a second task store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

DEFAULT_AUTO_RETRY_MAX = 3
_ACTIVE_STATUSES = {"processing", "running", "pending"}
_RETRY_LOCKS: dict[str, asyncio.Lock] = {}
_RETRY_LOCK_STALE_SECONDS = 300.0


def set_runtime(user_id: int, conversation_id: str, **updates: Any) -> None:
    patch_runtime_state(int(user_id), str(conversation_id), dict(updates))


def _artifact_dir(ctx) -> Path:
    d = ctx.conversation_dir / ".meta" / "generation_artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _artifact_path(ctx, artifact_ref: str) -> Path:
    safe_name = _safe_file_stem(artifact_ref.removeprefix("artifact_ref:"))
    return _artifact_dir(ctx) / f"{safe_name}.json"


def _safe_file_stem(value: str) -> str:
    stem = str(value or "").strip()
    if stem and all(ch.isalnum() or ch in ("-", "_") for ch in stem):
        return stem
    return hashlib.sha256(stem.encode("utf-8")).hexdigest()


def _retry_lock_key(ctx, artifact_ref: str) -> str:
    return f"{ctx.conversation_dir.resolve()}::{artifact_ref}"


def _retry_lock(ctx, artifact_ref: str) -> asyncio.Lock:
    key = _retry_lock_key(ctx, artifact_ref)
    lock = _RETRY_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _RETRY_LOCKS[key] = lock
    return lock


def _retry_lock_path(ctx, artifact_ref: str) -> Path:
    return _artifact_path(ctx, artifact_ref).with_suffix(".retry.lock")


def _acquire_retry_file_lock(ctx, artifact_ref: str) -> tuple[int, Path] | None:
    path = _retry_lock_path(ctx, artifact_ref)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = max(0.0, time.time() - path.stat().st_mtime)
        except FileNotFoundError:
            return _acquire_retry_file_lock(ctx, artifact_ref)
        if age >= _RETRY_LOCK_STALE_SECONDS:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return _acquire_retry_file_lock(ctx, artifact_ref)
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(time.time()))
    held_fd = os.open(path, os.O_RDONLY)
    return held_fd, path


def _release_retry_file_lock(lock_handle: tuple[int, Path] | None) -> None:
    if lock_handle is None:
        return
    fd, path = lock_handle
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def new_artifact_ref() -> str:
    return f"artifact_ref:{uuid.uuid4().hex}"


def _retry_state(data: dict[str, Any] | None) -> dict[str, int | str | None]:
    payload = data or {}
    return {
        "auto_retry_count": int(payload.get("auto_retry_count") or payload.get("retry_count") or 0),
        "auto_retry_max": int(payload.get("auto_retry_max") or payload.get("max_retry") or DEFAULT_AUTO_RETRY_MAX),
        "manual_retry_count": int(payload.get("manual_retry_count") or 0),
        "last_retry_source": payload.get("last_retry_source"),
    }


def _retry_payload(data: dict[str, Any] | None) -> dict[str, Any]:
    state = _retry_state(data)
    return {
        "auto_retry_count": state["auto_retry_count"],
        "auto_retry_max": state["auto_retry_max"],
        "manual_retry_count": state["manual_retry_count"],
        "last_retry_source": state["last_retry_source"],
    }


def _touch_dependency_wait_activity(ctx) -> None:
    user_id = getattr(ctx, "user_id", None)
    conversation_id = getattr(ctx, "conversation_id", None)
    if user_id is None or conversation_id is None:
        return
    try:
        set_runtime(
            int(user_id),
            str(conversation_id),
            run_state="waiting_tool",
            last_activity_source="artifact_dependency_wait",
        )
    except Exception:
        return


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _kind_from_task_type(task_type: str | None) -> str:
    return "video" if task_type in {"text2video", "image2video"} else "image"


def generation_task_to_dict(task: Any) -> dict[str, Any]:
    params = task.params if isinstance(getattr(task, "params", None), dict) else {}
    data: dict[str, Any] = {
        "id": task.id,
        "task_id": str(task.id),
        "kind": _kind_from_task_type(getattr(task, "task_type", None)),
        "task_type": getattr(task, "task_type", None),
        "status": getattr(task, "status", None),
        "progress": getattr(task, "progress", None),
        "provider_code": getattr(task, "provider_code", None),
        "model_name": getattr(task, "model_name", None),
        "model_label": getattr(task, "model_label", None),
        "prompt": getattr(task, "prompt", None),
        "result_url": getattr(task, "result_url", None),
        "result_urls": getattr(task, "result_urls", None),
        "error": getattr(task, "error_message", None),
        "error_message": getattr(task, "error_message", None),
        "created_at": _iso(getattr(task, "created_at", None)),
        "updated_at": _iso(getattr(task, "updated_at", None)),
    }
    for field in (
        "artifact_ref",
        "asset_id",
        "tool_call_id",
        "planned_result_url",
        "internal_result_url",
        "canvas_item",
        "canvas_revision",
        "canvas_item_deleted",
        "aspect_ratio",
        "resolution",
        "duration",
        "quality",
        "reference_image_urls",
        "reference_diagnostics",
        "first_frame_image",
        "tail_frame_image",
        "output",
        "input",
        "model_options",
        "retry_source",
        "negative_prompt",
        "watermark",
        "auto_retry_count",
        "auto_retry_max",
        "manual_retry_count",
        "last_retry_source",
        "presentation_scope",
        "presentation_message_key",
        "presentation_parent_block_key",
        "presentation_order",
        "suppress_standard_media_card",
        "presentation_surface",
    ):
        if field in params:
            data[field] = params[field]
    return data


async def read_generation_task(ctx, task_id: str | int | None) -> dict[str, Any] | None:
    if task_id is None:
        return None
    try:
        numeric_task_id = int(str(task_id).strip())
    except (TypeError, ValueError):
        return None

    from app.repositories.generation_repository import GenerationTaskRepository
    from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory

    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        task = await GenerationTaskRepository(db).get_by_id_and_user(
            numeric_task_id,
            int(ctx.user_id),
        )
        return generation_task_to_dict(task) if task else None


async def read_effective_generation_task(ctx, task_id: str | int) -> dict[str, Any] | None:
    task = await read_generation_task(ctx, task_id)
    if not task:
        return None

    artifact_ref = str(task.get("artifact_ref") or "").strip()
    if not artifact_ref:
        return task

    artifact = read_artifact(ctx, artifact_ref)
    if not artifact:
        return task

    current_task_id = str(artifact.get("current_task_id") or "").strip()
    current_task = await read_generation_task(ctx, current_task_id) if current_task_id else None
    effective = dict(current_task or task)

    effective_status = str(
        (current_task or {}).get("status")
        or artifact.get("status")
        or task.get("status")
        or "",
    ).strip()
    if effective_status:
        effective["status"] = effective_status

    for field in (
        "artifact_ref",
        "result_url",
        "result_urls",
        "internal_result_url",
        "progress",
        "error",
        "canvas_item",
        "canvas_revision",
        "canvas_item_deleted",
        "auto_retry_count",
        "auto_retry_max",
        "manual_retry_count",
        "last_retry_source",
        "planned_result_url",
        "suppress_standard_media_card",
    ):
        artifact_value = artifact.get(field)
        if artifact_value is not None and artifact_value != "":
            effective[field] = artifact_value

    if current_task_id:
        effective["task_id"] = current_task_id

    _reconcile_terminal_canvas_item(effective)
    return effective


async def read_effective_generation_task_by_artifact_ref(ctx, artifact_ref: str) -> dict[str, Any] | None:
    normalized_ref = str(artifact_ref or "").strip()
    if not normalized_ref:
        return None
    if not normalized_ref.startswith("artifact_ref:"):
        normalized_ref = f"artifact_ref:{normalized_ref}"

    artifact = read_artifact(ctx, normalized_ref)
    current_task_id = str((artifact or {}).get("current_task_id") or "").strip()
    if current_task_id:
        effective = await read_effective_generation_task(ctx, current_task_id)
        if effective:
            return effective

    from app.repositories.generation_repository import GenerationTaskRepository
    from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory

    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        latest_task = await GenerationTaskRepository(db).get_latest_by_artifact_ref(
            int(ctx.user_id),
            normalized_ref,
        )
    latest_params = latest_task.params if latest_task and isinstance(latest_task.params, dict) else {}
    latest_conversation_id = str(
        latest_params.get("agent_conversation_id")
        or latest_params.get("conversation_id")
        or "",
    ).strip()
    if latest_task and latest_conversation_id and latest_conversation_id != str(ctx.conversation_id):
        latest_task = None
    task = generation_task_to_dict(latest_task) if latest_task else None
    if task:
        task_id = task.get("task_id") or task.get("id")
        return await read_effective_generation_task(ctx, task_id) or task

    if artifact:
        return {
            "task_id": current_task_id or normalized_ref,
            "artifact_ref": normalized_ref,
            "status": artifact.get("status") or "planned",
            "kind": artifact.get("kind"),
            "progress": artifact.get("progress"),
            "result_url": artifact.get("result_url"),
            "result_urls": artifact.get("result_urls"),
            "artifact": artifact.get("artifact"),
            "error": artifact.get("error"),
            "canvas_item": artifact.get("canvas_item"),
            "canvas_revision": artifact.get("canvas_revision"),
            "canvas_item_deleted": artifact.get("canvas_item_deleted"),
            "planned_result_url": artifact.get("planned_result_url"),
            "suppress_standard_media_card": artifact.get("suppress_standard_media_card"),
            "presentation_surface": artifact.get("presentation_surface"),
            "created_at": artifact.get("created_at"),
            "updated_at": artifact.get("updated_at"),
        }

    return None


def create_or_read_artifact(
    ctx,
    *,
    kind: str,
    planned_result_url: str,
    artifact_ref: str | None = None,
    auto_retry_max: int = DEFAULT_AUTO_RETRY_MAX,
) -> dict[str, Any]:
    ref = str(artifact_ref or "").strip() or new_artifact_ref()
    existing = read_artifact(ctx, ref)
    if existing:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "artifact_ref": ref,
        "kind": kind,
        "planned_result_url": planned_result_url,
        "status": "planned",
        "auto_retry_count": 0,
        "auto_retry_max": auto_retry_max,
        "manual_retry_count": 0,
        "last_retry_source": None,
        "created_at": now,
        "updated_at": now,
    }
    data = sanitize_persistent_payload(data)
    _artifact_path(ctx, ref).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def update_artifact(ctx, artifact_ref: str, patch: dict[str, Any]) -> dict[str, Any]:
    p = _artifact_path(ctx, artifact_ref)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"artifact_ref": artifact_ref}
    if "auto_retry_count" not in data or "auto_retry_max" not in data or "manual_retry_count" not in data:
        data.update(_retry_payload(data))
        data.pop("retry_count", None)
        data.pop("max_retry", None)
    data.update(patch)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data = sanitize_persistent_payload(data)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def completed_canvas_item(
    canvas_item: dict[str, Any] | None,
    *,
    result_url: str,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(canvas_item, dict):
        return None
    next_item = dict(canvas_item)
    if task_id:
        next_item["task_id"] = task_id
    next_item["status"] = "completed"
    next_item["url"] = result_url or ""
    next_item.pop("error_message", None)
    next_item.pop("failure_kind", None)
    return next_item


def _reconcile_terminal_canvas_item(task: dict[str, Any]) -> None:
    status = str(task.get("status") or "").strip().lower()
    if status not in {"completed", "failed", "cancelled"}:
        return
    canvas_item = task.get("canvas_item")
    if not isinstance(canvas_item, dict):
        return

    next_item = dict(canvas_item)
    next_item["status"] = "failed" if status == "failed" else status
    task_id = str(task.get("task_id") or task.get("id") or "").strip()
    if task_id:
        next_item["task_id"] = task_id

    if status == "completed":
        result_url = str(task.get("result_url") or next_item.get("url") or "").strip()
        if result_url:
            next_item["url"] = result_url
        next_item.pop("error_message", None)
        next_item.pop("failure_kind", None)
    elif status == "failed":
        error_message = str(task.get("error_message") or task.get("error") or "").strip()
        if error_message:
            next_item["error_message"] = error_message
        next_item["failure_kind"] = next_item.get("failure_kind") or "task_failed"

    task["canvas_item"] = next_item


def read_artifact(ctx, artifact_ref: str) -> dict[str, Any] | None:
    p = _artifact_path(ctx, artifact_ref)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if "auto_retry_count" not in data or "auto_retry_max" not in data or "manual_retry_count" not in data:
        data.update(_retry_payload(data))
    return data


def _read_all_artifacts(ctx) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in _artifact_dir(ctx).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            if "auto_retry_count" not in data or "auto_retry_max" not in data or "manual_retry_count" not in data:
                data.update(_retry_payload(data))
            artifacts.append(data)
    return artifacts


def _is_pending_conversation_media_artifact(artifact: dict[str, Any]) -> bool:
    kind = str(artifact.get("kind") or "").strip().lower()
    if kind not in {"image", "video"}:
        return False
    status = str(artifact.get("status") or "").strip().lower()
    return status in _ACTIVE_STATUSES


async def wait_for_pending_conversation_media_artifacts(
    ctx,
    *,
    poll_interval_seconds: float = 3.0,
) -> dict[str, Any] | None:
    refs = [
        str(artifact.get("artifact_ref") or "").strip()
        for artifact in _read_all_artifacts(ctx)
        if _is_pending_conversation_media_artifact(artifact)
    ]
    refs = [ref for ref in refs if ref.startswith("artifact_ref:")]
    if not refs:
        return None

    _, error = await resolve_artifact_dependencies(
        ctx,
        {"pending_media_artifacts": refs},
        poll_interval_seconds=poll_interval_seconds,
    )
    return error


def mark_artifact_failed(
    ctx,
    artifact_ref: str,
    *,
    error: str | None = None,
    current_task_id: str | None = None,
    canvas_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "status": "failed",
        "error": error,
    }
    if current_task_id is not None:
        patch["current_task_id"] = current_task_id
    if canvas_item is not None:
        patch["canvas_item"] = canvas_item
    return update_artifact(ctx, artifact_ref, patch)


def collect_artifact_refs(value: Any, *, skip_key: str | None = None) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str) and value.startswith("artifact_ref:"):
        refs.add(value)
    elif isinstance(value, list):
        for item in value:
            refs.update(collect_artifact_refs(item, skip_key=skip_key))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == skip_key:
                continue
            refs.update(collect_artifact_refs(item, skip_key=skip_key))
    return refs


def _coerce_existing_artifact_ref(ctx, value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith("artifact_ref:"):
        return raw if raw.startswith("artifact_ref:") else None
    if any(token in raw for token in ("/", "\\", "://", "data:", "?", "#", " ", "\n", "\t")):
        return None
    candidate = f"artifact_ref:{raw}"
    return candidate if _artifact_path(ctx, candidate).exists() else None


def normalize_dependency_artifact_refs(ctx, value: Any, *, skip_key: str | None = None) -> Any:
    if isinstance(value, str):
        return _coerce_existing_artifact_ref(ctx, value) or value
    if isinstance(value, list):
        return [normalize_dependency_artifact_refs(ctx, item, skip_key=skip_key) for item in value]
    if isinstance(value, dict):
        return {
            key: item if key == skip_key else normalize_dependency_artifact_refs(ctx, item, skip_key=skip_key)
            for key, item in value.items()
        }
    return value


def replace_artifact_refs(value: Any, resolved: dict[str, str], *, skip_key: str | None = None) -> Any:
    if isinstance(value, str):
        return resolved.get(value, value)
    if isinstance(value, list):
        return [replace_artifact_refs(item, resolved, skip_key=skip_key) for item in value]
    if isinstance(value, dict):
        return {
            key: item if key == skip_key else replace_artifact_refs(item, resolved, skip_key=skip_key)
            for key, item in value.items()
        }
    return value


def _retry_error_payload(
    artifact: dict[str, Any],
    *,
    error: str,
    task_id: str | None,
) -> dict[str, Any]:
    retry_state = _retry_state(artifact)
    return {
        "error": "generation_artifact_failed",
        "artifact_ref": artifact["artifact_ref"],
        "task_id": task_id,
        "auto_retry_count": retry_state["auto_retry_count"],
        "auto_retry_max": retry_state["auto_retry_max"],
        "manual_retry_count": retry_state["manual_retry_count"],
        "message": error or "Generation failed.",
    }


async def retry_artifact(ctx, artifact_ref: str, *, source: str) -> Any:
    if source not in {"auto", "manual"}:
        raise ValueError("Unsupported retry source")

    async with _retry_lock(ctx, artifact_ref):
        file_lock = _acquire_retry_file_lock(ctx, artifact_ref)
        if file_lock is None:
            artifact = read_artifact(ctx, artifact_ref)
            if artifact is not None:
                current_task_id = str(artifact.get("current_task_id") or "").strip()
                current_task = await read_generation_task(ctx, current_task_id) if current_task_id else None
                effective = current_task or artifact
                effective_status = str(effective.get("status") or "").strip().lower()
                if effective_status in (_ACTIVE_STATUSES | {"completed"}):
                    return current_task or artifact
            raise RuntimeError("Generation retry already in progress")
        try:
            artifact = read_artifact(ctx, artifact_ref)
            if not artifact:
                raise KeyError("Artifact not found")

            current_task_id = str(artifact.get("current_task_id") or "").strip()
            task = await read_generation_task(ctx, current_task_id) if current_task_id else None
            effective = task or artifact
            status = str(effective.get("status") or "").strip().lower()

            if source == "auto" and status in (_ACTIVE_STATUSES | {"completed"}):
                return task or artifact
            if status != "failed":
                raise RuntimeError("Only failed generation artifacts can be retried")

            retry_state = _retry_state(artifact)
            if source == "auto" and retry_state["auto_retry_count"] >= retry_state["auto_retry_max"]:
                raise RuntimeError("Generation auto retry limit reached")

            patch = {
                "last_retry_source": source,
                "error": None,
            }
            if source == "auto":
                patch["auto_retry_count"] = int(retry_state["auto_retry_count"]) + 1
            else:
                patch["manual_retry_count"] = int(retry_state["manual_retry_count"]) + 1
            update_artifact(ctx, artifact_ref, patch)

            current_task = task or {}
            kind = str(current_task.get("kind") or artifact.get("kind") or "").strip().lower()
            if kind == "image":
                from app.services.agent_harness.capabilities.tools.generate_image import (
                    GenerateImageParams,
                    submit_image_generation,
                )

                result = await submit_image_generation(
                    params=GenerateImageParams(
                        prompt=str(current_task.get("prompt") or ""),
                        aspect_ratio=current_task.get("aspect_ratio"),
                        resolution=current_task.get("resolution"),
                        reference_image_urls=current_task.get("reference_image_urls"),
                    ),
                    ctx=ctx,
                    artifact_ref=artifact_ref,
                    retry_source=source,
                )
            elif kind == "video":
                from app.services.agent_harness.capabilities.tools.generate_video import (
                    GenerateVideoParams,
                    submit_video_generation,
                )

                duration = current_task.get("duration")
                result = await submit_video_generation(
                    params=GenerateVideoParams(
                        prompt=current_task.get("prompt"),
                        aspect_ratio=current_task.get("aspect_ratio"),
                        duration=int(duration) if duration is not None else None,
                        output=current_task.get("output"),
                        input=current_task.get("input"),
                        model_options=current_task.get("model_options"),
                        negative_prompt=current_task.get("negative_prompt"),
                        watermark=current_task.get("watermark"),
                    ),
                    ctx=ctx,
                    artifact_ref=artifact_ref,
                    retry_source=source,
                )
            else:
                raise RuntimeError("Unsupported generation artifact kind")

            return result
        finally:
            _release_retry_file_lock(file_lock)


async def retry_artifact_with_distributed_guard(ctx, artifact_ref: str, *, source: str) -> Any:
    if source != "auto":
        return await retry_artifact(ctx=ctx, artifact_ref=artifact_ref, source=source)

    artifact = read_artifact(ctx, artifact_ref)
    if not artifact:
        raise KeyError("Artifact not found")

    current_task_id = str(artifact.get("current_task_id") or "").strip() or None
    from app.services.agent_harness.generation_artifact_retry_coordinator import (
        GenerationArtifactRetryCoordinator,
    )

    coordinator = GenerationArtifactRetryCoordinator()
    handle = await coordinator.start(
        conversation_id=str(getattr(ctx, "conversation_id", "") or ""),
        artifact_ref=artifact_ref,
        current_task_id=current_task_id,
        source=source,
    )
    if not handle.acquired:
        status = dict(handle.status or {})
        status.setdefault("status", "running")
        status.setdefault("artifact_ref", artifact_ref)
        status.setdefault("current_task_id", current_task_id or "")
        return status

    try:
        result = await retry_artifact(ctx=ctx, artifact_ref=artifact_ref, source=source)
    except Exception as exc:
        await coordinator.fail(handle, artifact_ref=artifact_ref, error_type=type(exc).__name__)
        raise

    result_payload = getattr(result, "metadata", None)
    if not isinstance(result_payload, dict) and isinstance(result, dict):
        result_payload = result
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    await coordinator.finish(
        handle,
        artifact_ref=artifact_ref,
        task_id=str(result_payload.get("task_id") or result_payload.get("id") or ""),
        status=str(result_payload.get("status") or "processing"),
    )
    return result


async def resolve_artifact_dependencies(
    ctx,
    args: dict[str, Any],
    *,
    poll_interval_seconds: float = 3.0,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_args = normalize_dependency_artifact_refs(ctx, args, skip_key="artifact_ref")
    refs = collect_artifact_refs(normalized_args, skip_key="artifact_ref")
    if not refs:
        return normalized_args, None

    resolved: dict[str, str] = {}
    for ref in refs:
        artifact = read_artifact(ctx, ref)
        if not artifact:
            return None, {"error": "unknown_artifact_ref", "artifact_ref": ref}

        kind = str(artifact.get("kind") or "image").lower()
        timeout_seconds = (
            settings.TASK_TIMEOUT_VIDEO_SECONDS
            if kind == "video"
            else settings.TASK_TIMEOUT_IMAGE_SECONDS
        )
        deadline = time.monotonic() + timeout_seconds

        while True:
            artifact = read_artifact(ctx, ref)
            if not artifact:
                return None, {"error": "unknown_artifact_ref", "artifact_ref": ref}

            task_id = str(artifact.get("current_task_id") or "").strip()
            task = await read_generation_task(ctx, task_id) if task_id else None
            effective = task or artifact
            status = str(effective.get("status") or "").strip().lower()

            if status == "completed":
                result_url = (
                    (task or {}).get("internal_result_url")
                    or artifact.get("internal_result_url")
                    or (task or {}).get("result_url")
                    or artifact.get("result_url")
                    or artifact.get("planned_result_url")
                )
                if result_url:
                    public_result_url = artifact.get("result_url") or (task or {}).get("result_url") or result_url
                    internal_result_url = (task or {}).get("internal_result_url") or artifact.get("internal_result_url") or result_url
                    canvas_item = completed_canvas_item(
                        artifact.get("canvas_item")
                        if isinstance(artifact.get("canvas_item"), dict)
                        else (task or {}).get("canvas_item"),
                        result_url=str(public_result_url or result_url),
                        task_id=task_id or None,
                    )
                    patch = {
                        "status": "completed",
                        "result_url": public_result_url,
                        "internal_result_url": internal_result_url,
                    }
                    if canvas_item is not None:
                        patch["canvas_item"] = canvas_item
                    update_artifact(
                        ctx,
                        ref,
                        patch,
                    )
                    resolved[ref] = str(result_url)
                    break

            if status == "failed":
                retry_state = _retry_state(artifact)
                if int(retry_state["auto_retry_count"]) < int(retry_state["auto_retry_max"]):
                    try:
                        await retry_artifact_with_distributed_guard(ctx, ref, source="auto")
                    except RuntimeError:
                        artifact = read_artifact(ctx, ref) or artifact
                        task_id = str(artifact.get("current_task_id") or "").strip()
                        task = await read_generation_task(ctx, task_id) if task_id else None
                        current_status = str((task or artifact).get("status") or "").strip().lower()
                        if current_status in _ACTIVE_STATUSES:
                            continue
                    else:
                        continue

                failed = mark_artifact_failed(
                    ctx,
                    ref,
                    error=str((task or artifact).get("error") or ""),
                )
                return None, _retry_error_payload(
                    failed,
                    error=str(failed.get("error") or ""),
                    task_id=task_id or None,
                )

            if time.monotonic() >= deadline:
                retry_state = _retry_state(artifact)
                return None, {
                    "error": "generation_artifact_timeout",
                    "artifact_ref": ref,
                    "auto_retry_count": retry_state["auto_retry_count"],
                    "auto_retry_max": retry_state["auto_retry_max"],
                    "manual_retry_count": retry_state["manual_retry_count"],
                }

            _touch_dependency_wait_activity(ctx)
            await asyncio.sleep(poll_interval_seconds)

    return replace_artifact_refs(normalized_args, resolved, skip_key="artifact_ref"), None

