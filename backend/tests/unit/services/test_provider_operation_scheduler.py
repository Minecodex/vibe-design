import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete

from app.models.generation import GenerationTask
from app.models.provider_operation import ProviderOperation
from app.models.user import User
from app.repositories.provider_operation_repository import ProviderOperationRepository
from app.services import provider_operation_scheduler as scheduler_mod
from app.services.generation_media_resolver import GenerationMediaResolveError
from app.services.provider_operation_scheduler import ProviderOperationExecutor, ProviderOperationScheduler
from app.services.provider_request_gate import ProviderGateDecision


@pytest.mark.asyncio
async def test_provider_operation_scheduler_idle_wait_uses_idle_setting(monkeypatch):
    scheduler = ProviderOperationScheduler()
    waits: list[float] = []

    async def fake_run_once():
        return 0

    async def fake_wait(*, timeout_seconds: float):
        waits.append(timeout_seconds)
        scheduler._shutdown_event.set()

    monkeypatch.setattr(scheduler, "run_once", fake_run_once)
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.wait_provider_operation_wakeup",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.PROVIDER_OPERATION_SCHEDULER_IDLE_WAIT_SECONDS",
        19.0,
        raising=False,
    )

    await scheduler._run_loop()

    assert waits == [19.0]


@pytest.mark.asyncio
async def test_provider_operation_retry_delay_uses_retry_delay_setting(monkeypatch):
    requeues: list[dict] = []

    class FakeOperationRepo:
        async def requeue(self, operation, **kwargs):
            requeues.append(kwargs)

    executor = object.__new__(ProviderOperationExecutor)
    executor.operation_repo = FakeOperationRepo()
    operation = SimpleNamespace(id=11, operation="generation_submit")
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.PROVIDER_OPERATION_RETRY_DELAY_SECONDS",
        4.0,
        raising=False,
    )
    before = datetime.now(UTC)

    requeued = await executor._requeue_retryable_error(operation, TimeoutError("provider timeout"))

    assert requeued is True
    assert requeues
    due_at = requeues[0]["due_at"]
    assert before + timedelta(seconds=3.9) <= due_at <= datetime.now(UTC) + timedelta(seconds=4.1)
    assert requeues[0]["error_type"] == "retryable_timeout"


@pytest.mark.asyncio
async def test_generation_query_retryable_error_uses_query_poll_setting(monkeypatch):
    requeues: list[dict] = []

    class FakeOperationRepo:
        async def requeue(self, operation, **kwargs):
            requeues.append(kwargs)

    executor = object.__new__(ProviderOperationExecutor)
    executor.operation_repo = FakeOperationRepo()
    operation = SimpleNamespace(id=12, operation="generation_query")
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.PROVIDER_OPERATION_GENERATION_QUERY_POLL_SECONDS",
        3.0,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.PROVIDER_OPERATION_RETRY_DELAY_SECONDS",
        1.0,
        raising=False,
    )
    before = datetime.now(UTC)

    requeued = await executor._requeue_retryable_error(operation, TimeoutError("provider timeout"))

    assert requeued is True
    assert requeues
    due_at = requeues[0]["due_at"]
    assert before + timedelta(seconds=2.9) <= due_at <= datetime.now(UTC) + timedelta(seconds=3.1)
    assert requeues[0]["error_type"] == "retryable_timeout"


@pytest.mark.asyncio
async def test_generation_query_poll_delay_uses_query_poll_setting(monkeypatch):
    requeues: list[dict] = []

    class FakeOperationRepo:
        async def requeue(self, operation, **kwargs):
            requeues.append(kwargs)

    class FakeGenerationService:
        async def query_builtin_task_for_operation(self, task):
            return None

    executor = object.__new__(ProviderOperationExecutor)
    executor.db = object()
    executor.operation_repo = FakeOperationRepo()
    operation = SimpleNamespace(id=12, operation="generation_query")
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.PROVIDER_OPERATION_GENERATION_QUERY_POLL_SECONDS",
        3.0,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.generation_service.GenerationService",
        lambda _db: FakeGenerationService(),
    )
    before = datetime.now(UTC)

    await executor._execute_generation_query(operation, SimpleNamespace(id=33))

    assert requeues
    due_at = requeues[0]["due_at"]
    assert before + timedelta(seconds=2.9) <= due_at <= datetime.now(UTC) + timedelta(seconds=3.1)


@pytest.mark.asyncio
async def test_executor_defers_rate_limited_operation_without_terminalizing_task(db_session):
    await _clear_provider_operations(db_session)
    user = User(
        id=77,
        email="provider-op-executor@example.com",
        username="provider-op-executor",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=77,
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

    repo = ProviderOperationRepository(db_session)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        due_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "lease_token": "lease",
            "lease_owner": "worker",
        },
    )

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(
        allow=lambda **kwargs: _rate_limited_decision(),
    )

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert task.status == "processing"
    assert task.workflow_stage == "provider_operation"
    assert operation.status == "rate_limited"
    assert operation.retry_after_seconds == 13
    assert operation.lease_token is None


@pytest.mark.asyncio
async def test_executor_renews_operation_lease_while_provider_call_is_running(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=78,
        email="provider-op-renew@example.com",
        username="provider-op-renew",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=78,
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

    repo = ProviderOperationRepository(db_session)
    now = datetime.now(UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=1),
        },
    )

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(
        "app.services.provider_operation_scheduler.TASK_POLL_CLAIM_LEASE_SECONDS",
        3,
    )
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))

    async def _slow_submit(_operation, _task):
        await asyncio.sleep(1.8)

    executor._execute_generation_submit = _slow_submit

    await executor.execute(operation)

    await db_session.refresh(operation)
    assert operation.lease_expires_at is not None
    assert operation.lease_expires_at > (now + timedelta(seconds=2)).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_executor_requeues_retryable_provider_error_without_terminalizing_task(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=79,
        email="provider-op-retry@example.com",
        username="provider-op-retry",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=79,
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

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_query",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod.settings, "TASK_TIMEOUT_IMAGE_SECONDS", 24 * 60 * 60)

    async def _transient_query(_operation, _task):
        raise TimeoutError("provider query timed out")

    executor._execute_generation_query = _transient_query

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert task.status == "processing"
    assert task.workflow_stage == "provider_operation"
    assert task.terminalized_at is None
    assert operation.status == "queued"
    assert operation.lease_token is None
    assert operation.last_error_type == "retryable_timeout"


@pytest.mark.asyncio
async def test_executor_requeues_apimart_connect_error_without_terminalizing_task(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=82,
        email="provider-op-connect-retry@example.com",
        username="provider-op-connect-retry",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=82,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="apimart",
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        prompt="test prompt",
        params={},
        status="processing",
        workflow_stage="provider_operation",
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_query",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod.settings, "TASK_TIMEOUT_IMAGE_SECONDS", 24 * 60 * 60)

    async def _connect_failure_query(_operation, _task):
        raise httpx.ConnectError("all connection attempts failed")

    executor._execute_generation_query = _connect_failure_query

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert task.status == "processing"
    assert task.terminalized_at is None
    assert operation.status == "queued"
    assert operation.last_error_type == "retryable_network"


@pytest.mark.asyncio
async def test_generation_query_retryable_error_ignores_poll_attempt_count(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=84,
        email="provider-op-query-high-attempt@example.com",
        username="provider-op-query-high-attempt",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=84,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="apimart",
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        prompt="test prompt",
        params={},
        status="processing",
        workflow_stage="provider_operation",
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_query",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "attempt_count": 10,
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod, "PROVIDER_OPERATION_RETRYABLE_MAX_ATTEMPTS", 6)
    monkeypatch.setattr(scheduler_mod.settings, "TASK_TIMEOUT_IMAGE_SECONDS", 24 * 60 * 60)

    async def _connect_failure_query(_operation, _task):
        raise httpx.ConnectError("all connection attempts failed")

    executor._execute_generation_query = _connect_failure_query

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert task.status == "processing"
    assert task.workflow_stage == "provider_operation"
    assert task.terminalized_at is None
    assert operation.status == "queued"
    assert operation.last_error_type == "retryable_network"


@pytest.mark.asyncio
async def test_generation_query_terminalizes_at_task_timeout(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=85,
        email="provider-op-query-timeout@example.com",
        username="provider-op-query-timeout",
        hashed_password="test",
    )
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    task = GenerationTask(
        user_id=85,
        project_id=None,
        task_type="text2video",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="seedance-video",
        model_label="Seedance Video",
        prompt="test prompt",
        params={},
        status="processing",
        workflow_stage="provider_operation",
        created_at=now - timedelta(seconds=11),
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="lingyaai",
        operation="generation_query",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    finalized: list[int] = []

    class FakeTerminalizationService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def finalize_terminal_task(self, terminal_task, *, user_id=None):
            finalized.append(terminal_task.id)
            return True

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod.settings, "TASK_TIMEOUT_VIDEO_SECONDS", 10)
    monkeypatch.setattr(scheduler_mod, "GenerationTerminalizationService", FakeTerminalizationService)

    async def _query_should_not_run(_operation, _task):
        raise AssertionError("expired generation_query tasks should time out before querying provider")

    executor._execute_generation_query = _query_should_not_run

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert operation.status == "failed"
    assert operation.last_error_type == "generation_task_timeout"
    assert task.status == "failed"
    assert task.workflow_stage == "terminal_failed"
    assert task.last_error_type == "generation_task_timeout"
    assert task.error_message == "任务超时"
    assert task.terminalized_at is not None
    assert task.terminal_side_effects_finalized_at is not None
    assert finalized == [task.id]


@pytest.mark.asyncio
async def test_executor_terminalizes_generation_after_retryable_submit_attempts_exhausted(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=83,
        email="provider-op-retry-exhausted@example.com",
        username="provider-op-retry-exhausted",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=83,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="apimart",
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        prompt="test prompt",
        params={"artifact_ref": "artifact_ref:retry_exhausted"},
        status="processing",
        workflow_stage="provider_operation",
        artifact_ref="artifact_ref:retry_exhausted",
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        operation_key="image",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "attempt_count": 2,
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    finalized: list[int] = []

    class FakeTerminalizationService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def finalize_terminal_task(self, terminal_task, *, user_id=None):
            finalized.append(terminal_task.id)
            return True

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod, "PROVIDER_OPERATION_RETRYABLE_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(scheduler_mod, "GenerationTerminalizationService", FakeTerminalizationService)

    async def _read_failure_submit(_operation, _task):
        raise httpx.ReadError("")

    executor._execute_generation_submit = _read_failure_submit

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert operation.status == "failed"
    assert operation.last_error_type == "retryable_network"
    assert operation.last_error_message
    assert "attempts=2/2" in operation.last_error_message
    assert "ReadError" in operation.last_error_message
    assert task.status == "failed"
    assert task.workflow_stage == "terminal_failed"
    assert task.last_error_type == "retryable_network"
    assert task.error_message == operation.last_error_message
    assert task.terminalized_at is not None
    assert task.terminal_side_effects_finalized_at is not None
    assert finalized == [task.id]


@pytest.mark.asyncio
async def test_executor_terminalizes_reference_upload_failure_without_retrying(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=86,
        email="provider-op-reference-upload@example.com",
        username="provider-op-reference-upload",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=86,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="apimart",
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        prompt="test prompt",
        params={
            "artifact_ref": "artifact_ref:reference_upload_failed",
            "conversation_id": "conv-reference-upload-failed",
            "canvas_item": {
                "id": "agent-generated-reference-upload-failed",
                "type": "image_generator",
                "status": "generating",
                "artifact_ref": "artifact_ref:reference_upload_failed",
                "task_id": "pending",
            },
        },
        status="processing",
        workflow_stage="provider_operation",
        artifact_ref="artifact_ref:reference_upload_failed",
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 6, 26, 14, 29, 15, tzinfo=UTC)
    operation = await repo.enqueue_once(
        generation_task_id=task.id,
        user_id=task.user_id,
        provider_code="apimart",
        operation="generation_submit",
        operation_key="image",
        due_at=now,
    )
    operation = await repo.update(
        operation,
        {
            "status": "running",
            "attempt_count": 1,
            "lease_token": "lease",
            "lease_owner": "worker",
            "lease_expires_at": now + timedelta(seconds=30),
        },
    )

    finalized: list[tuple[int, str, str | None]] = []

    class FakeTerminalizationService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def finalize_terminal_task(self, terminal_task, *, user_id=None):
            finalized.append((terminal_task.id, terminal_task.status, terminal_task.error_message))
            return True

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))
    monkeypatch.setattr(scheduler_mod, "GenerationTerminalizationService", FakeTerminalizationService)

    async def _reference_upload_failure(_operation, _task):
        raise GenerationMediaResolveError("generation_reference_upload_failed")

    executor._execute_generation_submit = _reference_upload_failure

    await executor.execute(operation)

    await db_session.refresh(task)
    await db_session.refresh(operation)
    assert operation.status == "failed"
    assert operation.last_error_type == "GenerationMediaResolveError"
    assert operation.last_error_message == "generation_reference_upload_failed"
    assert operation.attempt_count == 1
    assert task.status == "failed"
    assert task.workflow_stage == "terminal_failed"
    assert task.last_error_type == "GenerationMediaResolveError"
    assert task.error_message == "generation_reference_upload_failed"
    assert task.terminalized_at is not None
    assert task.terminal_side_effects_finalized_at is not None
    assert finalized == [(task.id, "failed", "generation_reference_upload_failed")]


@pytest.mark.asyncio
async def test_stale_executor_failure_does_not_terminalize_task_after_lease_reclaimed(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=80,
        email="provider-op-stale@example.com",
        username="provider-op-stale",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=80,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="test-model",
        model_label="Test Model",
        prompt="test prompt",
        params={},
        status="processing",
        workflow_stage="provider_operation",
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
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
    stale_operation = first_claim[0]
    db_session.expunge(stale_operation)
    reclaimed = await repo.claim_due(
        now=now + timedelta(seconds=31),
        worker_id="worker-b",
        claim_token="token-b",
        lease_seconds=30,
        limit=10,
    )
    assert [item.id for item in reclaimed] == [operation.id]

    executor = ProviderOperationExecutor(db_session)
    executor.gate = SimpleNamespace(allow=lambda **kwargs: _allowed_decision())
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))

    async def _terminal_submit(_operation, _task):
        raise ValueError("bad request")

    executor._execute_generation_submit = _terminal_submit

    await executor.execute(stale_operation)

    await db_session.refresh(task)
    current_operation = await repo.get(operation.id)
    assert task.status == "processing"
    assert task.terminalized_at is None
    assert current_operation.status == "running"
    assert current_operation.lease_token == "token-b"


@pytest.mark.asyncio
async def test_scheduler_skips_claim_when_lease_token_was_reclaimed_before_execution(db_session, monkeypatch):
    await _clear_provider_operations(db_session)
    user = User(
        id=81,
        email="provider-op-scheduler-stale@example.com",
        username="provider-op-scheduler-stale",
        hashed_password="test",
    )
    task = GenerationTask(
        user_id=81,
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

    repo = ProviderOperationRepository(db_session)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
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
    reclaimed = await repo.claim_due(
        now=now + timedelta(seconds=31),
        worker_id="worker-b",
        claim_token="token-b",
        lease_seconds=30,
        limit=10,
    )
    assert [item.id for item in first_claim] == [operation.id]
    assert [item.id for item in reclaimed] == [operation.id]

    executed: list[int] = []

    async def _execute(self, operation):
        executed.append(operation.id)

    monkeypatch.setattr(ProviderOperationExecutor, "execute", _execute)
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", lambda: _SessionContext(db_session))

    scheduler = ProviderOperationScheduler()
    await scheduler._execute_claim(operation.id, claim_token="token-a")

    current_operation = await repo.get(operation.id)
    assert executed == []
    assert current_operation.lease_token == "token-b"


async def _rate_limited_decision():
    return ProviderGateDecision(allowed=False, retry_after_seconds=13)


async def _allowed_decision():
    return ProviderGateDecision(allowed=True)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _clear_provider_operations(db_session) -> None:
    await db_session.execute(delete(ProviderOperation))
    await db_session.commit()
