from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.generation_result_materializer import GenerationResultMaterializer
from app.services.generation_terminalization import (
    GenerationTerminalizationService,
    build_generation_terminal_update,
)


@pytest.mark.asyncio
async def test_generation_result_materializer_uses_planned_url_for_first_result_only():
    downloads: list[dict] = []

    async def download(url, ext, target_url=None):
        downloads.append({"url": url, "ext": ext, "target_url": target_url})
        return target_url or f"/api/v1/uploads/generated/{len(downloads)}.{ext}"

    materializer = GenerationResultMaterializer(
        download_file_to_local=download,
        build_download_failure_error=lambda url, exc: f"failed:{url}:{exc}",
    )
    task = SimpleNamespace(
        task_type="text2image",
        params={"planned_result_url": "agent://generated/result.png"},
    )

    update = await materializer.store_builtin_result_urls(
        task,
        ["https://provider.example/signed-1.png", "https://provider.example/signed-2.png"],
    )

    assert update == {
        "status": "completed",
        "result_url": "agent://generated/result.png",
        "progress": 100,
        "result_urls": [
            "agent://generated/result.png",
            "/api/v1/uploads/generated/2.png",
        ],
    }
    assert downloads[0]["target_url"] == "agent://generated/result.png"
    assert downloads[1]["target_url"] is None


def test_generation_terminal_update_clears_scheduler_claim_fields_for_completed_result():
    update = build_generation_terminal_update(
        {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/result.png",
        }
    )

    assert update["workflow_stage"] == "terminal_completed"
    assert update["terminalized_at"] is not None
    assert update["scheduler_next_run_at"] is None
    assert update["scheduler_claim_token"] is None


@pytest.mark.asyncio
async def test_generation_terminalization_service_finalizes_from_task_contract_without_provider_raw_shape():
    billing_calls: list[tuple[str, int]] = []
    artifact_updates: list[int] = []
    agent_updates: list[int] = []

    class FakeBillingService:
        def __init__(self, db):
            assert db == "db"

        async def finalize_lingyaai_generation_billing(self, task):
            billing_calls.append(("lingyaai", task.id))

        async def finalize_apimart_generation_billing(self, task):
            billing_calls.append(("apimart", task.id))

        async def refund_generation_usage_log_if_pending(self, task_id, user_id):
            billing_calls.append(("refund", task_id))

    async def artifact_publisher(task):
        artifact_updates.append(task.id)

    async def agent_usage_log_updater(db, task):
        assert db == "db"
        agent_updates.append(task.id)

    task = SimpleNamespace(
        id=51,
        user_id=7,
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        task_type="text2image",
        status="completed",
        result_url="/api/v1/uploads/generated/image.png",
        error_message=None,
        params={},
    )

    terminalizer = GenerationTerminalizationService(
        "db",
        billing_service_factory=FakeBillingService,
        artifact_publisher=artifact_publisher,
        agent_usage_log_updater=agent_usage_log_updater,
    )

    finalized = await terminalizer.finalize_terminal_task(task)

    assert finalized is True
    assert billing_calls == [("lingyaai", 51)]
    assert artifact_updates == [51]
    assert agent_updates == [51]


@pytest.mark.asyncio
async def test_generation_terminalization_service_refunds_failed_builtin_task_once_via_usage_log_state():
    billing_calls: list[tuple[str, int, int]] = []

    class FakeBillingService:
        def __init__(self, _db):
            pass

        async def finalize_lingyaai_generation_billing(self, task):
            raise AssertionError("failed tasks must not run success finalization")

        async def finalize_apimart_generation_billing(self, task):
            raise AssertionError("failed tasks must not run success finalization")

        async def refund_generation_usage_log_if_pending(self, task_id, user_id):
            billing_calls.append(("refund", task_id, user_id))

    async def artifact_publisher(_task):
        return None

    task = SimpleNamespace(
        id=52,
        user_id=8,
        provider_code="builtin",
        builtin_provider_code="apimart",
        task_type="text2image",
        status="failed",
        result_url=None,
        error_message="provider failed",
        params={},
    )

    terminalizer = GenerationTerminalizationService(
        object(),
        billing_service_factory=FakeBillingService,
        artifact_publisher=artifact_publisher,
    )

    finalized = await terminalizer.finalize_terminal_task(task)

    assert finalized is True
    assert billing_calls == [("refund", 52, 8)]
