from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import mysql

from app.models.generation import GenerationTask
from app.models.user import User
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.generation_task_scheduler import GenerationTaskScheduler


@pytest.mark.asyncio
async def test_generation_task_scheduler_claims_due_tasks_once_by_database_lease(db_session):
    await db_session.execute(
        update(GenerationTask)
        .where(GenerationTask.status.in_(["pending", "processing"]))
        .values(status="completed")
    )
    await db_session.commit()

    user = User(
        email="generation-scheduler@example.test",
        username="generation-scheduler",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        external_task_id="provider-task-1",
        scheduler_next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    scheduler_a = GenerationTaskScheduler(db_session, worker_id="worker-a")
    scheduler_b = GenerationTaskScheduler(db_session, worker_id="worker-b")

    claimed = await scheduler_a.claim_due_tasks(limit=1, lease_seconds=30)
    blocked = await scheduler_b.claim_due_tasks(limit=1, lease_seconds=30)

    assert len(claimed) == 1
    assert claimed[0].task.id == task.id
    assert claimed[0].claim_token
    assert claimed[0].task.scheduler_attempt_count == 1
    assert blocked == []


@pytest.mark.asyncio
async def test_generation_task_scheduler_claims_earliest_due_task_across_statuses(db_session):
    await db_session.execute(
        update(GenerationTask)
        .where(GenerationTask.status.in_(["pending", "processing"]))
        .values(status="completed")
    )
    await db_session.commit()

    user = User(
        email="generation-scheduler-order@example.test",
        username="generation-scheduler-order",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    now = datetime.now(UTC)
    later_pending = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="later pending",
        params={},
        status="pending",
        scheduler_next_run_at=now - timedelta(seconds=10),
    )
    earlier_processing = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="earlier processing",
        params={},
        status="processing",
        external_task_id="provider-task-1",
        scheduler_next_run_at=now - timedelta(seconds=20),
    )
    db_session.add_all([later_pending, earlier_processing])
    await db_session.commit()
    await db_session.refresh(later_pending)
    await db_session.refresh(earlier_processing)

    scheduler = GenerationTaskScheduler(db_session, worker_id="worker-a")

    claimed = await scheduler.claim_due_tasks(limit=1, lease_seconds=30)

    assert len(claimed) == 1
    assert claimed[0].task.id == earlier_processing.id


def test_generation_task_scheduler_due_scan_selects_only_ids():
    repo = GenerationTaskRepository(None)
    stmt = repo.build_due_scheduler_task_ids_stmt(
        status="pending",
        now=datetime(2026, 5, 21, tzinfo=UTC),
        limit=10,
    )

    sql = str(stmt.compile(dialect=mysql.dialect()))

    assert sql.startswith(
        "SELECT generation_tasks.id, generation_tasks.scheduler_next_run_at, "
        "generation_tasks.created_at"
    )
    assert "generation_tasks.status = %s" in sql
    assert "generation_tasks.status IN" not in sql
    assert "generation_tasks.prompt" not in sql
    assert "generation_tasks.params" not in sql
    assert (
        "ORDER BY generation_tasks.scheduler_next_run_at ASC, "
        "generation_tasks.created_at ASC, generation_tasks.id ASC"
    ) in sql


@pytest.mark.asyncio
async def test_generation_task_scheduler_terminalization_is_idempotent_and_clears_claim(db_session):
    user = User(
        email="generation-terminal@example.test",
        username="generation-terminal",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    now = datetime.now(UTC)
    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        external_task_id="provider-task-1",
        scheduler_claim_token="claim-1",
        scheduler_claimed_at=now,
        scheduler_lease_expires_at=now + timedelta(seconds=60),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    scheduler = GenerationTaskScheduler(db_session, worker_id="worker-a")

    completed = await scheduler.complete(
        task.id,
        user_id=user.id,
        claim_token="claim-1",
        data={"result_url": "https://cdn.example/first.png"},
    )
    duplicate = await scheduler.complete(
        task.id,
        user_id=user.id,
        claim_token="claim-1",
        data={"result_url": "https://cdn.example/second.png"},
    )

    assert completed is not None
    assert completed.status == "completed"
    assert completed.result_url == "https://cdn.example/first.png"
    assert completed.terminalized_at is not None
    assert completed.scheduler_claim_token is None
    assert completed.scheduler_lease_expires_at is None
    assert duplicate is not None
    assert duplicate.result_url == "https://cdn.example/first.png"


@pytest.mark.asyncio
async def test_generation_task_scheduler_enqueue_persists_next_run_before_redis_wakeup(db_session, monkeypatch):
    user = User(
        email="generation-enqueue@example.test",
        username="generation-enqueue",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="pending",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    wakeups: list[str] = []

    class FakeKeys:
        def build(self, **_kwargs):
            return "generation:scheduler:wakeup"

    class FakeCoordinator:
        keys = FakeKeys()

        async def wakeup(self, key):
            wakeups.append(key)
            refreshed = await scheduler.repo.get(task.id)
            assert refreshed.scheduler_next_run_at is not None
            return {"woken": True}

    monkeypatch.setattr("app.services.generation_task_scheduler.get_redis_coordinator", lambda: FakeCoordinator())
    scheduler = GenerationTaskScheduler(db_session, worker_id="worker-a")

    updated = await scheduler.enqueue(task.id, workflow_stage="provider_query")

    assert updated is not None
    assert updated.workflow_stage == "provider_query"
    assert updated.scheduler_next_run_at is not None
    assert len(wakeups) == 1
    assert ":rt:v2:wakeup:generation.scheduler.wakeup:" in wakeups[0]
