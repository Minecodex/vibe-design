from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.generation import GenerationTask
from app.models.user import User
from app.services import generation_service as generation_service_module
from app.services.generation_service import GenerationService
from app.services.generation_task_executor import GenerationTaskExecutor


@pytest.mark.asyncio
async def test_generation_task_executor_submits_internal_lingyaai_image_without_provider_query(
    db_session,
    monkeypatch,
):
    user = User(
        email="lingyaai-executor@example.test",
        username="lingyaai-executor",
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
        model_name="nano-banana-2",
        model_label="NanoBanana2",
        prompt="blue banana",
        params={"provider_submit": {"provider_code": "lingyaai"}},
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        builtin_provider_code="lingyaai",
        workflow_stage="lingyaai_image_submit",
        scheduler_claim_token="claim-1",
        scheduler_claimed_at=now,
        scheduler_lease_expires_at=now + timedelta(seconds=30),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    async def fail_query_task_status(self, task_id, user_id, *, scheduler_claim_token=None):
        raise AssertionError("LingyaAI image submit stage must not use provider query")

    async def fake_complete_lingyaai_image_task(self, *, task_id, user_id, scheduler_claim_token=None):
        updated = await self.task_repo.update_for_scheduler_claim(
            task_id=task_id,
            user_id=user_id,
            claim_token=scheduler_claim_token,
            data={
                "status": "completed",
                "result_url": "/api/v1/uploads/generated/lingyaai.png",
                "result_urls": ["/api/v1/uploads/generated/lingyaai.png"],
                "workflow_stage": "terminal_completed",
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            },
        )
        assert updated is not None

    monkeypatch.setattr(GenerationService, "query_task_status", fail_query_task_status)
    monkeypatch.setattr(GenerationService, "complete_lingyaai_image_task", fake_complete_lingyaai_image_task)

    executor = GenerationTaskExecutor(db_session)

    result = await executor.execute_once(
        task_id=task.id,
        user_id=user.id,
        scheduler_claim_token="claim-1",
    )

    assert result.status == "completed"
    assert result.result_url == "/api/v1/uploads/generated/lingyaai.png"


@pytest.mark.asyncio
async def test_generation_task_executor_submits_legacy_lingyaai_pending_image_without_stage(
    db_session,
    monkeypatch,
):
    user = User(
        email="lingyaai-legacy-executor@example.test",
        username="lingyaai-legacy-executor",
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
        model_name="nano-banana-2",
        model_label="NanoBanana2",
        prompt="blue banana",
        params={"provider_submit": {"provider_code": "lingyaai"}},
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}304",
        builtin_provider_code="lingyaai",
        workflow_stage=None,
        scheduler_claim_token="claim-legacy",
        scheduler_claimed_at=now,
        scheduler_lease_expires_at=now + timedelta(seconds=30),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    async def fail_query_task_status(self, task_id, user_id, *, scheduler_claim_token=None):
        raise AssertionError("Legacy LingyaAI pending image tasks must not fall back to provider query")

    async def fake_complete_lingyaai_image_task(self, *, task_id, user_id, scheduler_claim_token=None):
        updated = await self.task_repo.update_for_scheduler_claim(
            task_id=task_id,
            user_id=user_id,
            claim_token=scheduler_claim_token,
            data={
                "status": "completed",
                "result_url": "/api/v1/uploads/generated/legacy-lingyaai.png",
                "workflow_stage": "terminal_completed",
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            },
        )
        assert updated is not None

    monkeypatch.setattr(GenerationService, "query_task_status", fail_query_task_status)
    monkeypatch.setattr(GenerationService, "complete_lingyaai_image_task", fake_complete_lingyaai_image_task)

    executor = GenerationTaskExecutor(db_session)

    result = await executor.execute_once(
        task_id=task.id,
        user_id=user.id,
        scheduler_claim_token="claim-legacy",
    )

    assert result.status == "completed"
    assert result.result_url == "/api/v1/uploads/generated/legacy-lingyaai.png"


@pytest.mark.asyncio
async def test_generation_task_executor_recovers_lingyaai_pending_image_with_provider_query_stage(
    db_session,
    monkeypatch,
):
    user = User(
        email="lingyaai-recover-provider-query@example.test",
        username="lingyaai-recover-provider-query",
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
        model_name="doubao-seedream-4-5-251128",
        model_label="Seedream 4.5",
        prompt="monkey eating grapes",
        params={"provider_submit": {"provider_code": "lingyaai"}},
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}305",
        builtin_provider_code="lingyaai",
        workflow_stage="provider_query",
        scheduler_claim_token="claim-recover",
        scheduler_claimed_at=now,
        scheduler_lease_expires_at=now + timedelta(seconds=30),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    async def fail_query_task_status(self, task_id, user_id, *, scheduler_claim_token=None):
        raise AssertionError("LingyaAI pending image tasks must not use provider query")

    async def fake_complete_lingyaai_image_task(self, *, task_id, user_id, scheduler_claim_token=None):
        updated = await self.task_repo.update_for_scheduler_claim(
            task_id=task_id,
            user_id=user_id,
            claim_token=scheduler_claim_token,
            data={
                "status": "completed",
                "result_url": "/api/v1/uploads/generated/recovered-lingyaai.png",
                "result_urls": ["/api/v1/uploads/generated/recovered-lingyaai.png"],
                "workflow_stage": "terminal_completed",
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            },
        )
        assert updated is not None

    monkeypatch.setattr(GenerationService, "query_task_status", fail_query_task_status)
    monkeypatch.setattr(GenerationService, "complete_lingyaai_image_task", fake_complete_lingyaai_image_task)

    executor = GenerationTaskExecutor(db_session)

    result = await executor.execute_once(
        task_id=task.id,
        user_id=user.id,
        scheduler_claim_token="claim-recover",
    )

    assert result.status == "completed"
    assert result.result_url == "/api/v1/uploads/generated/recovered-lingyaai.png"


@pytest.mark.asyncio
async def test_generation_task_executor_submits_internal_ollama_image_without_provider_query(
    db_session,
    monkeypatch,
):
    user = User(
        email="ollama-executor@example.test",
        username="ollama-executor",
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
        provider_code="ollama",
        model_name="gpt-image-2",
        model_label="Ollama Image (gpt-image-2)",
        prompt="blue banana",
        params={"provider_submit": {"provider_code": "ollama"}},
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}403",
        workflow_stage="ollama_image_submit",
        scheduler_claim_token="claim-ollama",
        scheduler_claimed_at=now,
        scheduler_lease_expires_at=now + timedelta(seconds=30),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    async def fail_query_task_status(self, task_id, user_id, *, scheduler_claim_token=None):
        raise AssertionError("Ollama image submit stage must not use provider query")

    async def fake_complete_ollama_image_task(self, *, task_id, user_id, scheduler_claim_token=None):
        updated = await self.task_repo.update_for_scheduler_claim(
            task_id=task_id,
            user_id=user_id,
            claim_token=scheduler_claim_token,
            data={
                "status": "completed",
                "result_url": "/api/v1/uploads/generated/ollama.png",
                "result_urls": ["/api/v1/uploads/generated/ollama.png"],
                "workflow_stage": "terminal_completed",
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            },
        )
        assert updated is not None

    monkeypatch.setattr(GenerationService, "query_task_status", fail_query_task_status)
    monkeypatch.setattr(GenerationService, "complete_ollama_image_task", fake_complete_ollama_image_task)

    executor = GenerationTaskExecutor(db_session)

    result = await executor.execute_once(
        task_id=task.id,
        user_id=user.id,
        scheduler_claim_token="claim-ollama",
    )

    assert result.status == "completed"
    assert result.result_url == "/api/v1/uploads/generated/ollama.png"


@pytest.mark.asyncio
async def test_generation_task_executor_queries_external_provider_tasks(db_session, monkeypatch):
    user = User(
        email="provider-query-executor@example.test",
        username="provider-query-executor",
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
        builtin_provider_code="apimart",
        workflow_stage="provider_query",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    calls: list[tuple[int, int, str | None]] = []

    async def fake_query_task_status(self, task_id, user_id, *, scheduler_claim_token=None):
        calls.append((task_id, user_id, scheduler_claim_token))
        return task

    async def fail_complete_lingyaai_image_task(self, **kwargs):
        raise AssertionError("External provider query stage must not submit LingyaAI image")

    monkeypatch.setattr(GenerationService, "query_task_status", fake_query_task_status)
    monkeypatch.setattr(GenerationService, "complete_lingyaai_image_task", fail_complete_lingyaai_image_task)

    executor = GenerationTaskExecutor(db_session)

    result = await executor.execute_once(
        task_id=task.id,
        user_id=user.id,
        scheduler_claim_token="claim-2",
    )

    assert result is task
    assert calls == [(task.id, user.id, "claim-2")]
