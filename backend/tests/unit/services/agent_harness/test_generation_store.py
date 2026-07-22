from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.agent_harness.core.utils import generation_store


def _ctx(tmp_path, **kwargs):
    conversation_dir = tmp_path / "conversation"
    conversation_dir.mkdir()
    return SimpleNamespace(
        conversation_dir=conversation_dir,
        user_id=kwargs.get("user_id", 7),
        conversation_id=kwargs.get("conversation_id", "conv-generation-store"),
    )


def _task(
    task_id: str,
    *,
    status: str,
    artifact_ref: str,
    result_url: str | None = None,
    internal_result_url: str | None = None,
    error: str | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "kind": "image",
        "status": status,
        "artifact_ref": artifact_ref,
        "result_url": result_url,
        "internal_result_url": internal_result_url,
        "error": error,
    }


async def _fake_task_reader(tasks: dict[str, dict], _ctx, task_id):
    return tasks.get(str(task_id))


def test_artifacts_are_stored_without_local_task_history(tmp_path):
    ctx = _ctx(tmp_path)

    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )

    assert artifact["status"] == "planned"
    assert (ctx.conversation_dir / ".meta" / "generation_artifacts").exists()
    assert not (ctx.conversation_dir / ".meta" / "generation_tasks").exists()


@pytest.mark.asyncio
async def test_artifact_dependency_resolves_completed_generation_task(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {"current_task_id": "1", "status": "processing"},
    )
    tasks = {
        "1": _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            result_url="assets/references/generated_image_abc/original.png",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {"reference_image_url": "assets/references/generated_image_abc/original.png"}


@pytest.mark.asyncio
async def test_wait_for_pending_conversation_media_artifacts_waits_active_media_only(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    current = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/current/original.png",
    )
    other_run = generation_store.create_or_read_artifact(
        ctx,
        kind="video",
        planned_result_url="assets/references/other/original.mp4",
    )
    completed = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/completed/original.png",
    )
    generation_store.update_artifact(ctx, current["artifact_ref"], {"current_task_id": "1", "status": "processing"})
    generation_store.update_artifact(ctx, other_run["artifact_ref"], {"current_task_id": "2", "status": "running"})
    generation_store.update_artifact(
        ctx,
        completed["artifact_ref"],
        {"current_task_id": "3", "status": "completed", "run_id": "run-current"},
    )
    waited_refs = []

    async def fake_resolve_artifact_dependencies(_ctx, args, **_kwargs):
        waited_refs.extend(args["pending_media_artifacts"])
        return args, None

    monkeypatch.setattr(generation_store, "resolve_artifact_dependencies", fake_resolve_artifact_dependencies)

    error = await generation_store.wait_for_pending_conversation_media_artifacts(
        ctx,
        poll_interval_seconds=0,
    )

    assert error is None
    assert set(waited_refs) == {current["artifact_ref"], other_run["artifact_ref"]}


@pytest.mark.asyncio
async def test_artifact_dependency_resolves_reference_image_urls_list(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "processing",
            "canvas_item": {"id": "canvas-image-1", "task_id": "1", "status": "generating", "url": ""},
        },
    )
    tasks = {
        "1": _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            internal_result_url="assets/references/generated_image_abc/original.png",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_urls": [artifact["artifact_ref"], "https://example.com/ref.png"]},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {
        "reference_image_urls": [
            "assets/references/generated_image_abc/original.png",
            "https://example.com/ref.png",
        ]
    }
    updated_artifact = generation_store.read_artifact(ctx, artifact["artifact_ref"])
    assert updated_artifact["canvas_item"]["status"] == "completed"
    assert updated_artifact["canvas_item"]["url"] == "assets/references/generated_image_abc/original.png"


@pytest.mark.asyncio
async def test_effective_generation_task_includes_artifact_canvas_revision(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "completed",
            "result_url": "assets/references/generated_image_abc/original.png",
            "canvas_revision": 24,
            "canvas_item_deleted": False,
            "canvas_item": {
                "id": "canvas-image-1",
                "task_id": "1",
                "status": "completed",
                "url": "assets/references/generated_image_abc/original.png",
            },
        },
    )
    tasks = {
        "1": _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            result_url="assets/references/generated_image_abc/original.png",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    effective = await generation_store.read_effective_generation_task(ctx, "1")

    assert effective is not None
    assert effective["canvas_revision"] == 24
    assert effective["canvas_item_deleted"] is False
    assert effective["canvas_item"]["id"] == "canvas-image-1"


@pytest.mark.asyncio
async def test_effective_generation_task_does_not_overlay_stale_processing_artifact_on_failed_task(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_failed/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "processing",
            "canvas_revision": 24,
            "canvas_item_deleted": False,
            "canvas_item": {
                "id": "canvas-image-1",
                "task_id": "1",
                "status": "generating",
                "url": "",
            },
        },
    )
    tasks = {
        "1": _task(
            "1",
            status="failed",
            artifact_ref=artifact["artifact_ref"],
            error="generation_reference_upload_failed",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    effective = await generation_store.read_effective_generation_task(ctx, "1")

    assert effective is not None
    assert effective["status"] == "failed"
    assert effective["error"] == "generation_reference_upload_failed"
    assert effective["canvas_item"]["id"] == "canvas-image-1"
    assert effective["canvas_item"]["status"] == "failed"
    assert effective["canvas_item"]["error_message"] == "generation_reference_upload_failed"


@pytest.mark.asyncio
async def test_artifact_dependency_prefers_internal_result_url(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "processing",
            "result_url": "/api/v1/uploads/canvas/64/published-image.png",
            "internal_result_url": "assets/references/generated_image_abc/original.png",
            "canvas_item": {"id": "canvas-image-1", "task_id": "1", "status": "generating", "url": ""},
        },
    )
    tasks = {
        "1": _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            result_url="/api/v1/uploads/canvas/64/published-image.png",
            internal_result_url="assets/references/generated_image_abc/original.png",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {"reference_image_url": "assets/references/generated_image_abc/original.png"}
    updated_artifact = generation_store.read_artifact(ctx, artifact["artifact_ref"])
    assert updated_artifact["canvas_item"]["status"] == "completed"
    assert updated_artifact["canvas_item"]["url"] == "/api/v1/uploads/canvas/64/published-image.png"


@pytest.mark.asyncio
async def test_artifact_dependency_resolves_bare_artifact_id(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "processing",
            "internal_result_url": "assets/references/generated_image_abc/original.png",
        },
    )
    tasks = {
        "1": _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            internal_result_url="assets/references/generated_image_abc/original.png",
        )
    }
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"].removeprefix("artifact_ref:")},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {"reference_image_url": "assets/references/generated_image_abc/original.png"}


@pytest.mark.asyncio
async def test_artifact_dependency_wait_touches_runtime_activity_while_blocked(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, conversation_id="conv-wait-1")
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_wait/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {"current_task_id": "1", "status": "processing"},
    )
    tasks = {"1": _task("1", status="processing", artifact_ref=artifact["artifact_ref"])}
    runtime_updates: list[dict[str, object]] = []

    def _set_runtime(user_id: int, conversation_id: str, **updates):
        runtime_updates.append({"user_id": user_id, "conversation_id": conversation_id, **updates})

    async def _complete_after_first_wait(_: float) -> None:
        tasks["1"] = _task(
            "1",
            status="completed",
            artifact_ref=artifact["artifact_ref"],
            internal_result_url="assets/references/generated_image_wait/original.png",
        )
        generation_store.update_artifact(
            ctx,
            artifact["artifact_ref"],
            {
                "status": "completed",
                "internal_result_url": "assets/references/generated_image_wait/original.png",
            },
        )

    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))
    monkeypatch.setattr(generation_store, "set_runtime", _set_runtime)
    monkeypatch.setattr(generation_store.asyncio, "sleep", _complete_after_first_wait)

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {"reference_image_url": "assets/references/generated_image_wait/original.png"}
    assert runtime_updates[0]["run_state"] == "waiting_tool"
    assert runtime_updates[0]["last_activity_source"] == "artifact_dependency_wait"


@pytest.mark.asyncio
async def test_artifact_dependency_failed_generation_returns_retry_metadata(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "failed",
            "auto_retry_count": 3,
            "auto_retry_max": 3,
        },
    )
    tasks = {"1": _task("1", status="failed", artifact_ref=artifact["artifact_ref"], error="boom")}
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert resolved is None
    assert error["error"] == "generation_artifact_failed"
    assert error["artifact_ref"] == artifact["artifact_ref"]
    assert error["auto_retry_count"] == 3
    assert error["auto_retry_max"] == 3


@pytest.mark.asyncio
async def test_artifact_dependency_auto_retries_failed_generation_once(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_retry/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {"current_task_id": "1", "status": "failed", "auto_retry_count": 0, "auto_retry_max": 3},
    )
    tasks = {"1": _task("1", status="failed", artifact_ref=artifact["artifact_ref"], error="boom")}

    async def _retry_artifact(*, ctx, artifact_ref, source):
        tasks["2"] = _task(
            "2",
            status="completed",
            artifact_ref=artifact_ref,
            internal_result_url="assets/references/generated_image_retry/original.png",
        )
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "status": "completed",
                "current_task_id": "2",
                "auto_retry_count": 1,
                "last_retry_source": source,
                "internal_result_url": "assets/references/generated_image_retry/original.png",
            },
        )
        return tasks["2"]

    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))
    monkeypatch.setattr(generation_store, "retry_artifact", _retry_artifact)

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert error is None
    assert resolved == {"reference_image_url": "assets/references/generated_image_retry/original.png"}
    updated_artifact = generation_store.read_artifact(ctx, artifact["artifact_ref"])
    assert updated_artifact["auto_retry_count"] == 1
    assert updated_artifact["last_retry_source"] == "auto"


@pytest.mark.asyncio
async def test_auto_retry_uses_distributed_guard_to_suppress_duplicate_submissions(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_retry/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {"current_task_id": "1", "status": "failed", "auto_retry_count": 0, "auto_retry_max": 3},
    )
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    retry_calls = 0

    async def fake_retry_artifact(ctx, artifact_ref, *, source):
        nonlocal retry_calls
        retry_calls += 1
        await asyncio.sleep(0.02)
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "current_task_id": "2",
                "status": "processing",
                "auto_retry_count": 1,
                "last_retry_source": source,
            },
        )
        return {"task_id": "2", "status": "processing", "artifact_ref": artifact_ref}

    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(generation_store, "retry_artifact", fake_retry_artifact)

    first, second = await asyncio.gather(
        generation_store.retry_artifact_with_distributed_guard(ctx, artifact["artifact_ref"], source="auto"),
        generation_store.retry_artifact_with_distributed_guard(ctx, artifact["artifact_ref"], source="auto"),
    )

    assert retry_calls == 1
    assert {first.get("status"), second.get("status")} == {"processing", "running"}
    updated_artifact = generation_store.read_artifact(ctx, artifact["artifact_ref"])
    assert updated_artifact["auto_retry_count"] == 1
    assert updated_artifact["last_retry_source"] == "auto"


@pytest.mark.asyncio
async def test_artifact_dependency_timeout_uses_image_task_timeout_setting(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_abc/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {"current_task_id": "1", "status": "processing"},
    )
    tasks = {"1": _task("1", status="processing", artifact_ref=artifact["artifact_ref"])}
    monotonic_values = iter([0.0, 2.0, 2.0])

    async def _unexpected_sleep(_: float) -> None:
        raise AssertionError("dependency wait should time out before sleeping")

    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))
    monkeypatch.setattr(generation_store.settings, "TASK_TIMEOUT_IMAGE_SECONDS", 1)
    monkeypatch.setattr(generation_store.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(generation_store.asyncio, "sleep", _unexpected_sleep)

    resolved, error = await generation_store.resolve_artifact_dependencies(
        ctx,
        {"reference_image_url": artifact["artifact_ref"]},
        poll_interval_seconds=0,
    )

    assert resolved is None
    assert error == {
        "error": "generation_artifact_timeout",
        "artifact_ref": artifact["artifact_ref"],
        "auto_retry_count": 0,
        "auto_retry_max": 3,
        "manual_retry_count": 0,
    }


@pytest.mark.asyncio
async def test_retry_artifact_submits_only_one_replacement_under_parallel_attempts(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    artifact = generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_image_retry/original.png",
    )
    generation_store.update_artifact(
        ctx,
        artifact["artifact_ref"],
        {
            "current_task_id": "1",
            "status": "failed",
            "manual_retry_count": 0,
        },
    )
    tasks = {"1": _task("1", status="failed", artifact_ref=artifact["artifact_ref"], error="boom")}
    submissions: list[str] = []

    monkeypatch.setattr(generation_store, "_retry_lock", lambda *_args, **_kwargs: asyncio.Lock())
    monkeypatch.setattr(generation_store, "read_generation_task", lambda ctx, task_id: _fake_task_reader(tasks, ctx, task_id))

    async def fake_submit_image_generation(*, params, ctx, artifact_ref, retry_source):
        submissions.append(retry_source)
        await asyncio.sleep(0.02)
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "current_task_id": "2",
                "status": "processing",
                "manual_retry_count": 1,
                "last_retry_source": retry_source,
            },
        )
        return {"task_id": "2", "status": "processing", "artifact_ref": artifact_ref}

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.submit_image_generation",
        fake_submit_image_generation,
    )

    first, second = await asyncio.gather(
        generation_store.retry_artifact(ctx, artifact["artifact_ref"], source="manual"),
        generation_store.retry_artifact(ctx, artifact["artifact_ref"], source="manual"),
        return_exceptions=True,
    )

    results = [first, second]
    assert submissions == ["manual"]
    assert sum(1 for result in results if isinstance(result, dict)) == 1
    assert any(isinstance(result, RuntimeError) and "already in progress" in str(result) for result in results)
    updated_artifact = generation_store.read_artifact(ctx, artifact["artifact_ref"])
    assert updated_artifact["manual_retry_count"] == 1
    assert updated_artifact["last_retry_source"] == "manual"
