from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey
from app.services.agent_harness.runtime.context_projection import (
    get_projection_state,
    mark_projection_dirty,
)
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    append_message_record as append_message,
)


# The projection worker only owns recall sidecar refresh. Prompt-shaping
# projections are not part of the model context path.


def test_context_projection_worker_rebuilds_dirty_recall_and_clears_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection worker")
    append_message(7, conversation["id"], {"role": "user", "content": "worker should project backend/app/projection.py"})
    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=3,
        reason="message_appended",
    )

    from app.services.agent_harness.runtime.context_projection_worker import (
        process_next_context_projection,
    )

    completed = process_next_context_projection(worker_id="projection-worker")
    state = get_projection_state(7, conversation["id"])

    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["conversation_id"] == conversation["id"]
    assert "recall_sidecar_refresh" in completed["result"]["responsibilities"]
    assert state["dirty_responsibilities"] == []
    assert state["latest_processed_sequence"] == 3


def test_context_projection_worker_failure_keeps_dirty_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection worker failure")
    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=4,
        reason="message_appended",
    )

    from app.services.agent_harness.runtime import context_projection_worker

    monkeypatch.setattr(
        context_projection_worker,
        "rebuild_recall_sidecar",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic projection failure")),
    )

    failed = context_projection_worker.process_next_context_projection(worker_id="projection-worker")
    state = get_projection_state(7, conversation["id"])

    assert failed is not None
    assert failed["status"] == "failed"
    assert "synthetic projection failure" in failed["last_error_summary"]
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert state["lease_owner"] is None
    assert state["next_project_at"] is not None
    assert datetime.fromisoformat(state["next_project_at"]) > datetime.now(timezone.utc)

    retry = context_projection_worker.process_next_context_projection(worker_id="projection-worker")
    assert retry is None


def test_context_projection_database_claim_blocks_second_worker(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection claim contention")
    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=4,
        reason="message_appended",
    )

    from app.services.agent_harness.runtime.context_projection import claim_next_projection

    first = claim_next_projection(worker_id="worker-a", lease_seconds=60)
    second = claim_next_projection(worker_id="worker-b", lease_seconds=60)
    state = get_projection_state(7, conversation["id"])

    assert first is not None
    assert first["conversation_id"] == conversation["id"]
    assert second is None
    assert state["lease_owner"] == "worker-a"
    assert state["lease_token"] == first["lease_token"]


def test_context_projection_duplicate_rebuild_guard_keeps_dirty_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    conversation = create_conversation(7, title="Projection duplicate guard")
    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=4,
        reason="message_appended",
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=60)
    guard.start_sync(
        EphemeralTaskKey.build(
            domain="context-projection",
            kind="recall_sidecar_refresh",
            resource_parts=[7, conversation["id"], "recall_sidecar_refresh"],
            version=4,
        ),
        owner_prefix="test",
    )

    from app.services.agent_harness.runtime.context_projection_worker import (
        process_next_context_projection,
    )

    failed = process_next_context_projection(worker_id="projection-worker")
    state = get_projection_state(7, conversation["id"])

    assert failed is not None
    assert failed["status"] == "failed"
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]


def test_recall_sidecar_direct_rebuild_uses_ephemeral_guard(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    conversation = create_conversation(7, title="Recall direct guard")
    guard = EphemeralTaskCoordinator(ttl_seconds=60)
    guard.start_sync(
        EphemeralTaskKey.build(
            domain="context-projection",
            kind="recall_sidecar_refresh",
            resource_parts=[7, conversation["id"], "recall_sidecar_refresh"],
            version=4,
        ),
        owner_prefix="test",
    )
    calls = 0

    from app.services.agent_harness.runtime import recall_sidecar

    def fake_rebuild(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"path": str(tmp_path / "recall.sqlite"), "chunks": 1}

    monkeypatch.setattr(recall_sidecar, "rebuild_recall_sidecar", fake_rebuild)

    skipped = recall_sidecar.rebuild_recall_sidecar_with_guard(
        7,
        conversation["id"],
        target_sequence=4,
    )
    completed = recall_sidecar.rebuild_recall_sidecar_with_guard(
        7,
        conversation["id"],
        target_sequence=5,
    )

    assert skipped["status"] == "skipped_duplicate"
    assert completed["chunks"] == 1
    assert calls == 1


def test_context_projection_batch_respects_configured_concurrency_cap(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_RECALL_SIDECAR_WORKER_MAX_CONCURRENCY", 1)
    first = create_conversation(7, title="Projection cap one")
    second = create_conversation(7, title="Projection cap two")
    mark_projection_dirty(7, first["id"], responsibilities=["recall_sidecar_refresh"], latest_event_sequence=1, reason="message_appended")
    mark_projection_dirty(7, second["id"], responsibilities=["recall_sidecar_refresh"], latest_event_sequence=1, reason="message_appended")

    from app.services.agent_harness.runtime.context_projection_worker import (
        process_context_projection_batch,
    )

    processed = process_context_projection_batch(worker_id="projection-worker", batch_size=3)

    assert processed is not None
    assert len(processed) == 1


async def test_context_projection_worker_waits_on_redis_wakeup_between_database_sweeps(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS", 0.25)
    monkeypatch.setattr("app.core.config.settings.HARNESS_RECALL_SIDECAR_WORKER_BATCH_SIZE", 1)

    from app.services.agent_harness.runtime import context_projection_worker

    sweeps: list[int] = []
    waits: list[float] = []

    async def fake_wait(*, timeout_seconds: float):
        waits.append(timeout_seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(context_projection_worker, "process_context_projection_batch", lambda **_kwargs: sweeps.append(1) and None)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.context_projection_wakeup.wait_context_projection_wakeup",
        fake_wait,
    )

    try:
        await context_projection_worker._run_worker_loop()
    except asyncio.CancelledError:
        pass

    assert sweeps == [1]
    assert waits == [0.25]
