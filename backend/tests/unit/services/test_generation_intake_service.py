from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.billing import UsageLog
from app.models.generation import GenerationTask
from app.models.user import User
from app.models.user_apimart_credential import UserApimartCredential
from app.services import generation_service as generation_service_module
from app.services.generation_intake_service import GenerationIntakeRequest, GenerationIntakeService


@pytest.mark.asyncio
async def test_generation_intake_reuses_client_request_without_billing_or_resubmit(db_session, monkeypatch):
    user = User(
        email="generation-intake@example.test",
        username="generation-intake",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    existing = GenerationTask(
        user_id=user.id,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        client_request_id="req-1",
        external_task_id="provider-task-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    class BillingShouldNotRun:
        def __init__(self, _db):
            raise AssertionError("duplicate intake must not initialize billing")

    async def generate_should_not_run(*_args, **_kwargs):
        raise AssertionError("duplicate intake must not resubmit generation")

    enqueued: list[int] = []

    async def enqueue_task(task_id: int, **_kwargs):
        enqueued.append(task_id)

    monkeypatch.setattr("app.services.generation_intake_service.BillingService", BillingShouldNotRun)
    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "generate_image", generate_should_not_run)
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_task,
    )

    result = await intake.submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=5,
            prompt="new prompt",
            model_name="seedream",
            provider_code="builtin",
            aspect_ratio="1:1",
            resolution="1K",
            client_request_id="req-1",
        )
    )

    assert result.task.id == existing.id
    assert result.reused_existing is True
    assert result.amount_cents == 0
    assert enqueued == [existing.id]


@pytest.mark.asyncio
async def test_generation_intake_resumes_lingyaai_pending_image_at_submit_stage(db_session, monkeypatch):
    user = User(
        email="generation-intake-lingyaai-resume@example.test",
        username="generation-intake-lingyaai-resume",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    existing = GenerationTask(
        user_id=user.id,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="doubao-seedream-4-5-251128",
        model_label="Seedream 4.5",
        prompt="monkey eating grapes",
        params={"provider_submit": {"provider_code": "lingyaai"}},
        status="processing",
        client_request_id="req-lingyaai-pending",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}1",
        workflow_stage="lingyaai_image_submit",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    async def generate_should_not_run(*_args, **_kwargs):
        raise AssertionError("duplicate intake must not resubmit generation")

    enqueued: list[tuple[int, str | None]] = []

    async def enqueue_task(task_id: int, **kwargs):
        enqueued.append((task_id, kwargs.get("workflow_stage")))

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "generate_image", generate_should_not_run)
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_task,
    )

    result = await intake.submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=5,
            prompt="new prompt",
            model_name="doubao-seedream-4-5-251128",
            provider_code="builtin",
            aspect_ratio="auto",
            resolution="4K",
            client_request_id="req-lingyaai-pending",
        )
    )

    assert result.task.id == existing.id
    assert result.reused_existing is True
    assert enqueued == [(existing.id, "lingyaai_image_submit")]


@pytest.mark.asyncio
async def test_generation_intake_does_not_resume_provider_operation_task(monkeypatch):
    task = SimpleNamespace(
        id=404,
        status="processing",
        workflow_stage="provider_operation",
        provider_code="builtin",
        task_type="text2image",
        external_task_id=None,
    )

    async def enqueue_should_not_run(*_args, **_kwargs):
        raise AssertionError("provider_operation tasks must stay on provider_operations queue")

    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_should_not_run,
    )

    await GenerationIntakeService._resume_processing(task)


@pytest.mark.asyncio
async def test_generation_intake_refunds_reserved_balance_when_scheduler_enqueue_fails(db_session, monkeypatch):
    user = User(
        email="generation-intake-enqueue@example.test",
        username="generation-intake-enqueue",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    billing_events: list[tuple[str, int]] = []
    usage_logs: list[int] = []

    class FakeBillingService:
        def __init__(self, _db):
            pass

        def calculate_amount(self, *_args, **_kwargs):
            return 25

        async def get_balance(self, _user_id: int):
            return 100

        async def deduct_balance(self, user_id: int, amount_cents: int):
            billing_events.append(("deduct", amount_cents))
            assert user_id == user.id
            return True

        async def refund_balance(self, user_id: int, amount_cents: int):
            billing_events.append(("refund", amount_cents))
            assert user_id == user.id

        async def create_usage_log(self, **kwargs):
            usage_logs.append(kwargs["task_id"])

    async def fake_generate_image(**kwargs):
        assert kwargs["client_request_id"] == "req-enqueue-fails"
        return GenerationTask(
            id=321,
            user_id=user.id,
            project_id=7,
            task_type="text2image",
            provider_code="builtin",
            model_name=kwargs["model_name"],
            model_label="Seedream",
            prompt=kwargs["prompt"],
            params={},
            status="processing",
            client_request_id=kwargs["client_request_id"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def enqueue_fails(*_args, **_kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr("app.services.generation_intake_service.BillingService", FakeBillingService)
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_fails,
    )

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "generate_image", fake_generate_image)

    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        await intake.submit_image(
            GenerationIntakeRequest(
                user_id=user.id,
                project_id=7,
                prompt="blue banana",
                model_name="gpt-image-2",
                provider_code="builtin",
                aspect_ratio="1:1",
                resolution="1K",
                client_request_id="req-enqueue-fails",
            )
        )

    assert billing_events == [("deduct", 25), ("refund", 25)]
    assert usage_logs == [321]


@pytest.mark.asyncio
async def test_generation_intake_forwards_planned_result_url_to_image_submission(db_session, monkeypatch):
    user = User(
        email="generation-intake-planned-url@example.test",
        username="generation-intake-planned-url",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    captured: dict[str, object] = {}

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return GenerationTask(
            id=322,
            user_id=user.id,
            project_id=None,
            task_type="text2image",
            provider_code="builtin",
            model_name=kwargs["model_name"],
            model_label="Seedream",
            prompt=kwargs["prompt"],
            params={},
            status="processing",
            client_request_id=kwargs["client_request_id"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def enqueue_task(*_args, **_kwargs):
        return None

    async def no_charge(*_args, **_kwargs):
        return 0

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake, "_reserve_builtin_billing", no_charge)
    monkeypatch.setattr(intake.generation_service, "generate_image", fake_generate_image)
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_task,
    )

    await intake.submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=None,
            prompt="planned url",
            model_name="gpt-image-2",
            provider_code="builtin",
            aspect_ratio="1:1",
            resolution="1K",
            client_request_id="req-planned-url",
            planned_result_url="references/generated/image-001.png",
        )
    )

    assert captured["planned_result_url"] == "references/generated/image-001.png"


@pytest.mark.asyncio
async def test_generation_intake_provider_balance_sync_creates_zero_amount_usage_log(
    db_session,
    monkeypatch,
):
    user = User(
        email="generation-intake-provider-balance@example.test",
        username="generation-intake-provider-balance",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    db_session.add(
        UserApimartCredential(
            user_id=user.id,
            api_key="sk-generation-intake-balance",
            status="active",
            is_current=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    balance_checks: list[str] = []

    async def synced_provider_balance(api_key):
        assert api_key == "sk-generation-intake-balance"
        balance_checks.append("checked")
        return 500

    async def fake_generate_image(**kwargs):
        task = GenerationTask(
            user_id=user.id,
            project_id=9,
            task_type="text2image",
            provider_code="builtin",
            builtin_provider_code="lingyaai",
            model_name=kwargs["model_name"],
            model_label="GPT-Image 2",
            prompt=kwargs["prompt"],
            params={"resolution": kwargs["resolution"]},
            status="processing",
            client_request_id=kwargs["client_request_id"],
            external_task_id="lingyaai-image-pending:1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        return task

    async def enqueue_task(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.generation_intake_service.get_active_builtin_provider_code",
        lambda: "lingyaai",
    )
    monkeypatch.setattr(
        "app.services.billing_service.is_provider_balance_sync_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.is_provider_balance_sync_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.billing_service.provider_balance_sync_service.get_balance_cents",
        synced_provider_balance,
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_task,
    )

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "generate_image", fake_generate_image)

    result = await intake.submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=9,
            prompt="provider balance image",
            model_name="gpt-image-2",
            provider_code="builtin",
            aspect_ratio="1:1",
            resolution="1K",
            client_request_id="provider-balance-sync-1",
        )
    )

    logs = (
        await db_session.execute(
            select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.task_id == result.task.id)
        )
    ).scalars().all()

    assert balance_checks == ["checked"]
    assert result.amount_cents == 0
    assert len(logs) == 1
    assert logs[0].amount_cents == 0
    assert logs[0].amount_cents_original == 0
    assert logs[0].billing_mode == "provider_balance_sync"
    assert logs[0].provider_code == "lingyaai"
    assert logs[0].status == "pending"


@pytest.mark.asyncio
async def test_generation_intake_provider_balance_sync_finalizes_completed_lingyaai_usage_log(
    db_session,
    monkeypatch,
):
    user = User(
        email="generation-intake-provider-balance-completed@example.test",
        username="generation-intake-provider-balance-completed",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    db_session.add(
        UserApimartCredential(
            user_id=user.id,
            api_key="sk-generation-intake-completed",
            status="active",
            is_current=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    async def synced_provider_balance(api_key):
        assert api_key == "sk-generation-intake-completed"
        return 500

    async def fake_generate_image(**kwargs):
        task = GenerationTask(
            user_id=user.id,
            project_id=9,
            task_type="text2image",
            provider_code="builtin",
            builtin_provider_code="lingyaai",
            model_name=kwargs["model_name"],
            model_label="GPT-Image 2",
            prompt=kwargs["prompt"],
            params={"resolution": kwargs["resolution"]},
            status="completed",
            client_request_id=kwargs["client_request_id"],
            external_task_id="lingyaai-sync:oneapi-provider-balance-1",
            provider_request_id="oneapi-provider-balance-1",
            provider_trace_id="trace-provider-balance-1",
            result_url="https://cdn.example.test/generated.png",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        return task

    async def enqueue_task(*_args, **_kwargs):
        raise AssertionError("completed LingyaAI task should not be resumed")

    monkeypatch.setattr(
        "app.services.generation_intake_service.get_active_builtin_provider_code",
        lambda: "lingyaai",
    )
    monkeypatch.setattr(
        "app.services.billing_service.is_provider_balance_sync_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.is_provider_balance_sync_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.billing_service.provider_balance_sync_service.get_balance_cents",
        synced_provider_balance,
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        enqueue_task,
    )

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "generate_image", fake_generate_image)

    result = await intake.submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=9,
            prompt="completed provider balance image",
            model_name="gpt-image-2",
            provider_code="builtin",
            aspect_ratio="1:1",
            resolution="1K",
            client_request_id="provider-balance-sync-completed-1",
        )
    )

    logs = (
        await db_session.execute(
            select(UsageLog).where(UsageLog.user_id == user.id, UsageLog.task_id == result.task.id)
        )
    ).scalars().all()

    assert result.amount_cents == 0
    assert len(logs) == 1
    assert logs[0].amount_cents == 0
    assert logs[0].amount_cents_original == 0
    assert logs[0].billing_mode == "provider_balance_sync"
    assert logs[0].provider_code == "lingyaai"
    assert logs[0].provider_request_id == "oneapi-provider-balance-1"
    assert logs[0].provider_trace_id == "trace-provider-balance-1"
    assert logs[0].status == "success"
    assert logs[0].billing_finalized_at is not None


@pytest.mark.asyncio
async def test_generation_intake_rejects_unknown_provider_before_task_or_usage_log(db_session):
    user = User(
        email="generation-intake-invalid-provider@example.test",
        username="generation-intake-invalid-provider",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    intake = GenerationIntakeService(db_session)

    with pytest.raises(HTTPException) as exc:
        await intake.submit_image(
            GenerationIntakeRequest(
                user_id=user.id,
                project_id=None,
                prompt="invalid provider",
                model_name="gpt-image-2",
                provider_code="missing-provider",
                aspect_ratio="1:1",
                resolution="1K",
                client_request_id="invalid-provider-1",
            )
        )

    task_count = await db_session.scalar(
        select(func.count()).select_from(GenerationTask).where(GenerationTask.user_id == user.id)
    )
    usage_count = await db_session.scalar(
        select(func.count()).select_from(UsageLog).where(UsageLog.user_id == user.id)
    )

    assert exc.value.status_code == 400
    assert task_count == 0
    assert usage_count == 0


@pytest.mark.asyncio
async def test_generation_intake_rejects_unknown_builtin_model_before_task_or_usage_log(
    db_session,
    monkeypatch,
):
    user = User(
        email="generation-intake-invalid-model@example.test",
        username="generation-intake-invalid-model",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    async def credentials_should_not_run(*_args, **_kwargs):
        raise AssertionError("validation must run before provider credentials are loaded")

    intake = GenerationIntakeService(db_session)
    monkeypatch.setattr(intake.generation_service, "_get_credentials", credentials_should_not_run)

    with pytest.raises(HTTPException) as exc:
        await intake.submit_image(
            GenerationIntakeRequest(
                user_id=user.id,
                project_id=None,
                prompt="invalid model",
                model_name="not-a-real-image-model",
                provider_code="builtin",
                aspect_ratio="1:1",
                resolution="1K",
                client_request_id="invalid-model-1",
            )
        )

    task_count = await db_session.scalar(
        select(func.count()).select_from(GenerationTask).where(GenerationTask.user_id == user.id)
    )
    usage_count = await db_session.scalar(
        select(func.count()).select_from(UsageLog).where(UsageLog.user_id == user.id)
    )

    assert exc.value.status_code == 400
    assert task_count == 0
    assert usage_count == 0
