from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.models.generation import GenerationTask
from app.models.provider_operation import ProviderOperation
from app.models.user import User
from app.repositories.provider_operation_repository import ProviderOperationRepository


async def _clear_provider_operations(db_session) -> None:
    await db_session.execute(delete(ProviderOperation))
    await db_session.commit()


async def _create_generation_task(db_session, *, user_id: int = 91_001) -> GenerationTask:
    user = User(
        id=user_id,
        email=f"provider-op-{user_id}@example.com",
        username=f"provider-op-{user_id}",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=user_id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="test-model",
        model_label="Test Model",
        prompt="test prompt",
        params={},
        status="processing",
        workflow_stage="provider_operation",
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_enqueue_once_is_idempotent_for_active_operation(db_session):
    await _clear_provider_operations(db_session)
    task = await _create_generation_task(db_session)
    repo = ProviderOperationRepository(db_session)

    first = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        operation_key="image",
        priority="foreground",
        payload={"task_kind": "image"},
    )
    second = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        operation_key="image",
        priority="foreground",
        payload={"task_kind": "image", "ignored": True},
    )

    assert second.id == first.id
    assert second.status == "queued"
    assert second.payload == {"task_kind": "image"}


@pytest.mark.asyncio
async def test_claim_due_skips_future_due_and_active_lease_then_reclaims_after_expiry(db_session):
    await _clear_provider_operations(db_session)
    task = await _create_generation_task(db_session, user_id=91_002)
    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0)

    due = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_query",
        due_at=now - timedelta(seconds=1),
    )
    await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="result_download",
        due_at=now + timedelta(minutes=5),
    )
    assert await repo.list_due_operation_ids(now=now, limit=10) == [due.id]

    claimed = await repo.claim_due(
        now=now,
        worker_id="worker-a",
        claim_token="token-a",
        lease_seconds=60,
        limit=10,
    )
    assert [operation.id for operation in claimed] == [due.id]
    assert claimed[0].status == "running"
    assert claimed[0].attempt_count == 1

    assert await repo.claim_due(
        now=now + timedelta(seconds=30),
        worker_id="worker-b",
        claim_token="token-b",
        lease_seconds=60,
        limit=10,
    ) == []

    reclaimed = await repo.claim_due(
        now=now + timedelta(seconds=61),
        worker_id="worker-b",
        claim_token="token-b",
        lease_seconds=60,
        limit=10,
    )
    assert [operation.id for operation in reclaimed] == [due.id]
    assert reclaimed[0].lease_owner == "worker-b"
    assert reclaimed[0].attempt_count == 2


@pytest.mark.asyncio
async def test_defer_rate_limited_operation_keeps_queue_state_claimable_later(db_session):
    await _clear_provider_operations(db_session)
    task = await _create_generation_task(db_session, user_id=91_003)
    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        due_at=now,
    )

    deferred = await repo.defer_rate_limited(operation, retry_after_seconds=12, now=now)

    assert deferred.status == "rate_limited"
    assert deferred.retry_after_seconds == 12
    assert deferred.due_at == now + timedelta(seconds=12)
    assert deferred.lease_token is None
    assert deferred.last_error_type == "provider_rate_limited"


@pytest.mark.asyncio
async def test_stale_lease_owner_cannot_complete_reclaimed_operation(db_session):
    await _clear_provider_operations(db_session)
    task = await _create_generation_task(db_session, user_id=91_004)
    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        due_at=now,
    )

    first_claim = await repo.claim_due(
        now=now,
        worker_id="worker-a",
        claim_token="token-a",
        lease_seconds=30,
        limit=10,
    )
    stale_claim = first_claim[0]
    db_session.expunge(stale_claim)
    reclaimed = await repo.claim_due(
        now=now + timedelta(seconds=31),
        worker_id="worker-b",
        claim_token="token-b",
        lease_seconds=30,
        limit=10,
    )

    assert [item.id for item in first_claim] == [operation.id]
    assert [item.id for item in reclaimed] == [operation.id]

    completed = await repo.mark_succeeded(
        stale_claim,
        result_payload={"external_task_id": "stale-result"},
    )

    assert completed.status == "running"
    assert completed.lease_token == "token-b"
    assert completed.result_payload is None
