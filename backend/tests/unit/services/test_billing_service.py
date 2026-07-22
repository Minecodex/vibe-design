from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import UsageLog
from app.models.generation import GenerationTask
from app.models.user import User
from app.models.user_apimart_credential import UserApimartCredential
from app.repositories.billing_repository import UsageLogRepository
from app.services.billing_service import BillingService
from app.services.builtin_provider import LingyaAiBillLookupResult


def _duplicate_usage_log_primary_key_error() -> IntegrityError:
    class _Orig:
        args = (1062, "Duplicate entry '1931' for key 'usage_logs.PRIMARY'")

    return IntegrityError("insert usage_logs", {}, _Orig())


@pytest.mark.asyncio
async def test_deduct_balance_uses_provider_balance_gate_without_local_mutation(
    db_session: AsyncSession,
    monkeypatch,
):
    user = User(
        email="provider-gate@example.com",
        username="provider-gate",
        hashed_password="x",
        balance_cents=0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    db_session.add(
        UserApimartCredential(
            user_id=user.id,
            api_key="sk-provider-gate",
            status="active",
            is_current=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "saas")
    async def positive_provider_balance(api_key):
        assert api_key == "sk-provider-gate"
        return 1

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)
    from app.services import billing_service

    monkeypatch.setattr(
        billing_service.provider_balance_sync_service,
        "get_balance_cents",
        positive_provider_balance,
    )

    ok = await BillingService(db_session).deduct_balance(user.id, 9999)
    await db_session.refresh(user)

    assert ok is True
    assert user.balance_cents == 0


@pytest.mark.asyncio
async def test_deduct_balance_blocks_when_provider_balance_is_zero(
    db_session: AsyncSession,
    monkeypatch,
):
    user = User(
        email="provider-gate-zero@example.com",
        username="provider-gate-zero",
        hashed_password="x",
        balance_cents=9999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    db_session.add(
        UserApimartCredential(
            user_id=user.id,
            api_key="sk-provider-gate-zero",
            status="active",
            is_current=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "saas")
    async def zero_provider_balance(api_key):
        assert api_key == "sk-provider-gate-zero"
        return 0

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)
    from app.services import billing_service

    monkeypatch.setattr(
        billing_service.provider_balance_sync_service,
        "get_balance_cents",
        zero_provider_balance,
    )

    ok = await BillingService(db_session).deduct_balance(user.id, 1)
    await db_session.refresh(user)

    assert ok is False
    assert user.balance_cents == 9999


@pytest.mark.asyncio
async def test_create_usage_log_forces_zero_amounts_in_provider_balance_sync_mode(
    db_session: AsyncSession,
    monkeypatch,
):
    user = User(
        email="zero-usage@example.com",
        username="zero-usage",
        hashed_password="x",
        balance_cents=9999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)

    log = await BillingService(db_session).create_usage_log(
        user_id=user.id,
        task_id=123,
        model_name="imagen-4.0-apimart",
        task_type="text2image",
        amount_cents=9999,
        task_status="success",
        billing_mode="local_price",
    )

    assert log.amount_cents == 0
    assert log.amount_cents_original == 0
    assert log.billing_mode == "provider_balance_sync"


@pytest.mark.asyncio
async def test_provider_reconcile_usage_log_becomes_success_zero_in_provider_balance_sync_mode(
    db_session: AsyncSession,
    monkeypatch,
):
    user = User(
        email="zero-reconcile@example.com",
        username="zero-reconcile",
        hashed_password="x",
        balance_cents=9999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)

    log = await BillingService(db_session).create_provider_reconcile_usage_log(
        user_id=user.id,
        task_id=456,
        model_name="gpt-image-2",
        task_type="text2image",
        provider_code="lingyaai",
        provider_request_id="oneapi-1",
        billing_label="billing.labels.image_generate",
    )

    assert log.status == "success"
    assert log.amount_cents == 0
    assert log.amount_cents_original == 0
    assert log.billing_mode == "provider_balance_sync"
    assert log.billing_finalized_at is not None


@pytest.mark.asyncio
async def test_get_usage_logs_recovers_completed_lingyaai_provider_balance_sync_log(
    db_session: AsyncSession,
    monkeypatch,
):
    user = User(
        email="recover-lingyaai-provider-balance@example.com",
        username="recover-lingyaai-provider-balance",
        hashed_password="x",
        balance_cents=9999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=9,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        prompt="recover completed image",
        params={"resolution": "1K"},
        status="completed",
        external_task_id="lingyaai-sync:oneapi-recover-1",
        provider_request_id="oneapi-recover-1",
        provider_trace_id="trace-recover-1",
        result_url="https://cdn.example.test/recovered.png",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    log = UsageLog(
        user_id=user.id,
        task_id=task.id,
        model_name="gpt-image-2",
        model_label="GPT-Image 2",
        task_type="text2image",
        amount_cents=0,
        amount_cents_original=0,
        status="pending",
        provider_code="lingyaai",
        billing_mode="provider_balance_sync",
        billing_label="billing.labels.image_generate",
        params={"resolution": "1K"},
    )
    db_session.add(log)
    await db_session.commit()

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)

    items, total = await BillingService(db_session).get_usage_logs(user_id=user.id)

    assert total == 1
    assert items[0]["status"] == "success"
    assert items[0]["billing_mode"] == "provider_balance_sync"
    assert items[0]["provider_request_id"] == "oneapi-recover-1"
    assert items[0]["provider_trace_id"] == "trace-recover-1"

    refreshed = await db_session.scalar(select(UsageLog).where(UsageLog.id == log.id))
    assert refreshed is not None
    assert refreshed.status == "success"
    assert refreshed.billing_finalized_at is not None


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_sums_successful_children_and_stays_pending_with_active_children(monkeypatch):
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=11,
        user_id=7,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={"agent_started_at": "2026-03-25T00:00:00+00:00"},
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )
    children = [
        SimpleNamespace(
            id=21,
            parent_id=11,
            amount_cents=3,
            amount_cents_original=3,
            status="success",
            elapsed_ms=1200,
            updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=22,
            parent_id=11,
            amount_cents=0,
            amount_cents_original=4,
            status="refunded",
            elapsed_ms=2500,
            updated_at=datetime(2026, 3, 25, 0, 0, 3, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=23,
            parent_id=11,
            amount_cents=5,
            amount_cents_original=5,
            status="pending",
            elapsed_ms=0,
            updated_at=datetime(2026, 3, 25, 0, 0, 4, tzinfo=UTC),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 11
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 11
            return children

        async def update(self, obj, data: dict):
            updated["obj"] = obj
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=11,
        finished_at=datetime(2026, 3, 25, 0, 0, 6, tzinfo=UTC),
    )

    assert updated["obj"] is parent
    assert updated["data"]["amount_cents"] == 3
    assert updated["data"]["amount_cents_original"] == 3
    assert updated["data"]["status"] == "pending"
    assert updated["data"]["elapsed_ms"] == 6000


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_marks_success_when_all_children_are_terminal():
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=12,
        user_id=9,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={"agent_started_at": "2026-03-25T00:00:00+00:00"},
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )
    children = [
        SimpleNamespace(
            id=31,
            parent_id=12,
            amount_cents=2,
            amount_cents_original=2,
            status="success",
            elapsed_ms=800,
            updated_at=datetime(2026, 3, 25, 0, 0, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=32,
            parent_id=12,
            amount_cents=0,
            amount_cents_original=4,
            status="refunded",
            elapsed_ms=1400,
            updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 12
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 12
            return children

        async def update(self, obj, data: dict):
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=12,
        finished_at=datetime(2026, 3, 25, 0, 0, 4, tzinfo=UTC),
    )

    assert updated["data"]["amount_cents"] == 2
    assert updated["data"]["amount_cents_original"] == 2
    assert updated["data"]["status"] == "success"
    assert updated["data"]["elapsed_ms"] == 4000


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_treats_naive_finished_at_as_app_timezone(monkeypatch):
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=13,
        user_id=9,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={"agent_started_at": "2026-03-25T08:47:36+00:00"},
        created_at=datetime(2026, 3, 25, 16, 47, 36),
        updated_at=datetime(2026, 3, 25, 16, 47, 36),
    )
    children = [
        SimpleNamespace(
            id=41,
            parent_id=13,
            amount_cents=42,
            amount_cents_original=42,
            status="success",
            elapsed_ms=45000,
            updated_at=datetime(2026, 3, 25, 16, 48, 21),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 13
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 13
            return children

        async def update(self, obj, data: dict):
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=13,
        finished_at=datetime(2026, 3, 25, 16, 48, 21),
    )

    assert updated["data"]["status"] == "success"
    assert updated["data"]["amount_cents"] == 42
    assert updated["data"]["elapsed_ms"] == 45000


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_keeps_cancelled_status_terminal():
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=14,
        parent_id=None,
        user_id=9,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="cancelled",
        params={"agent_started_at": "2026-03-25T00:00:00+00:00"},
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )
    children = [
        SimpleNamespace(
            id=51,
            parent_id=14,
            amount_cents=8,
            amount_cents_original=8,
            status="success",
            elapsed_ms=1200,
            updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 14
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 14
            return children

        async def update(self, obj, data: dict):
            updated["obj"] = obj
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=14,
        finished_at=datetime(2026, 3, 25, 0, 0, 3, tzinfo=UTC),
    )

    assert updated["data"]["amount_cents"] == 8
    assert updated["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_rebuilds_agent_summary_from_child_usage_logs():
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=15,
        parent_id=None,
        user_id=9,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={
            "engine": "agent_harness",
            "conversation_id": "conv-agent-summary",
            "agent_run_id": "run-agent-summary",
            "billing_summary": {
                "mode": "image",
                "mode_label": "智能设计师",
                "multimodal_calls": 0,
                "image_analysis_calls": 0,
                "image_generation_calls": 0,
                "video_generation_calls": 0,
                "context_compression_calls": 0,
                "multimodal_models": [],
                "image_analysis_models": [],
                "image_models": [],
                "video_models": [],
                "context_compression_models": [],
                "multimodal_model_stats": [],
                "image_analysis_model_stats": [],
                "image_model_stats": [],
                "video_model_stats": [],
                "context_compression_model_stats": [],
                "total_elapsed_ms": 0,
            },
        },
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )
    children = [
        SimpleNamespace(
            id=61,
            parent_id=15,
            task_type="multimodal",
            model_name="kimi-k2.5",
            amount_cents=3,
            amount_cents_original=3,
            status="success",
            elapsed_ms=100,
            params={"kind": "agent_llm"},
            updated_at=datetime(2026, 3, 25, 0, 0, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=62,
            parent_id=15,
            task_type="text2image",
            model_name="doubao-seedream-4-5",
            amount_cents=20,
            amount_cents_original=20,
            status="success",
            elapsed_ms=200,
            params={"generation_task": {"task_type": "text2image"}},
            updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=63,
            parent_id=15,
            task_type="image_analysis",
            model_name="gemini-3.1-pro-preview",
            amount_cents=4,
            amount_cents_original=4,
            status="success",
            elapsed_ms=300,
            params={"kind": "analyze_image"},
            updated_at=datetime(2026, 3, 25, 0, 0, 3, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=64,
            parent_id=15,
            task_type="context_compression",
            model_name="kimi-k2.5",
            amount_cents=1,
            amount_cents_original=1,
            status="success",
            elapsed_ms=400,
            params={"kind": "context_compaction"},
            updated_at=datetime(2026, 3, 25, 0, 0, 4, tzinfo=UTC),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 15
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 15
            return children

        async def update(self, obj, data: dict):
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=15,
        finished_at=datetime(2026, 3, 25, 0, 0, 5, tzinfo=UTC),
    )

    summary = updated["data"]["params"]["billing_summary"]
    assert updated["data"]["amount_cents"] == 28
    assert summary["mode"] == "image"
    assert summary["mode_label"] == "智能设计师"
    assert summary["multimodal_calls"] == 1
    assert summary["image_generation_calls"] == 1
    assert summary["image_analysis_calls"] == 1
    assert summary["context_compression_calls"] == 1
    assert summary["image_models"] == ["doubao-seedream-4-5"]
    assert summary["image_analysis_models"] == ["gemini-3.1-pro-preview"]
    assert summary["context_compression_models"] == ["kimi-k2.5"]
    assert summary["total_elapsed_ms"] == 1000


@pytest.mark.asyncio
async def test_refresh_parent_usage_log_uses_agent_model_summary_elapsed_not_wall_clock():
    service = BillingService(db=object())
    parent = SimpleNamespace(
        id=16,
        parent_id=None,
        user_id=9,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={
            "engine": "agent_harness",
            "conversation_id": "conv-agent-wall-clock",
            "agent_run_id": "run-agent-wall-clock",
            "billing_summary": {
                "mode": "spreadsheet",
                "mode_label": "表格生成",
                "multimodal_calls": 0,
                "image_analysis_calls": 0,
                "image_generation_calls": 0,
                "video_generation_calls": 0,
                "context_compression_calls": 0,
                "multimodal_models": [],
                "image_analysis_models": [],
                "image_models": [],
                "video_models": [],
                "context_compression_models": [],
                "multimodal_model_stats": [],
                "image_analysis_model_stats": [],
                "image_model_stats": [],
                "video_model_stats": [],
                "context_compression_model_stats": [],
                "total_elapsed_ms": 0,
            },
        },
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )
    children = [
        SimpleNamespace(
            id=71,
            parent_id=16,
            task_type="multimodal",
            model_name="GPT-5.4",
            amount_cents=0,
            amount_cents_original=0,
            status="success",
            elapsed_ms=2_000,
            params={"kind": "agent_llm"},
            updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=72,
            parent_id=16,
            task_type="multimodal",
            model_name="GPT-5.4",
            amount_cents=0,
            amount_cents_original=0,
            status="success",
            elapsed_ms=18_000,
            params={"kind": "agent_llm"},
            updated_at=datetime(2026, 3, 25, 0, 0, 20, tzinfo=UTC),
        ),
    ]
    updated: dict = {}

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 16
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 16
            return children

        async def update(self, obj, data: dict):
            updated["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()

    await service.refresh_parent_usage_log(
        log_id=16,
        finished_at=datetime(2026, 3, 25, 0, 10, 0, tzinfo=UTC),
    )

    summary = updated["data"]["params"]["billing_summary"]
    assert updated["data"]["elapsed_ms"] == 20_000
    assert summary["total_elapsed_ms"] == 20_000


@pytest.mark.asyncio
async def test_apply_provider_reconcile_plan_batches_mixed_outcomes_and_refreshes_each_parent_once(
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "saas")

    user = User(
        email="billing-batch@example.com",
        username="billing_batch",
        hashed_password="hashed",
        role="user",
        balance_cents=200,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = BillingService(db_session)
    parent = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="agent_harness",
        task_type="agent",
        amount_cents=0,
        task_status="pending",
    )
    settle_log = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="kimi-k2.6",
        task_type="multimodal",
        amount_cents=0,
        parent_id=parent.id,
        task_status="pending",
        provider_code="lingyaai",
        provider_request_id="req-settle",
        billing_mode="provider_reconcile",
        billing_next_run_at=datetime.now(UTC),
    )
    retry_log = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="kimi-k2.6",
        task_type="multimodal",
        amount_cents=0,
        parent_id=parent.id,
        task_status="pending",
        provider_code="lingyaai",
        provider_request_id="req-retry",
        billing_mode="provider_reconcile",
        billing_next_run_at=datetime.now(UTC),
    )
    block_log = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="kimi-k2.6",
        task_type="multimodal",
        amount_cents=0,
        parent_id=parent.id,
        task_status="pending",
        provider_code="lingyaai",
        provider_request_id="req-block",
        billing_mode="provider_reconcile",
        billing_next_run_at=datetime.now(UTC),
    )
    for log in (settle_log, retry_log, block_log):
        log.billing_lock_token = "lock-token"
    await db_session.commit()

    refresh_calls: list[int] = []
    original_refresh = service.refresh_parent_usage_log

    async def wrapped_refresh(parent_id: int, **kwargs):
        refresh_calls.append(parent_id)
        return await original_refresh(parent_id, **kwargs)

    monkeypatch.setattr(service, "refresh_parent_usage_log", wrapped_refresh)

    commit_calls = 0
    original_commit = db_session.commit

    async def counted_commit():
        nonlocal commit_calls
        commit_calls += 1
        return await original_commit()

    monkeypatch.setattr(db_session, "commit", counted_commit)

    bill = LingyaAiBillLookupResult.from_row(
        {"request_id": "req-settle", "quota": 1011, "prompt_tokens": 1, "completion_tokens": 2},
        billing_unit_per_yuan=500000,
        oneapi_request_id="req-settle",
    )
    plan = SimpleNamespace(
        settles=[SimpleNamespace(log_id=settle_log.id, bill=bill)],
        retries=[SimpleNamespace(log_id=retry_log.id, next_run_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC))],
        blocks=[SimpleNamespace(log_id=block_log.id, reason="lingyaai_bill_not_found")],
    )

    await service.apply_provider_reconcile_plan(plan, lock_token="lock-token")

    rows = (
        await db_session.execute(
            select(UsageLog).where(UsageLog.id.in_([settle_log.id, retry_log.id, block_log.id, parent.id]))
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}

    assert by_id[settle_log.id].status == "success"
    assert by_id[retry_log.id].status == "pending"
    assert by_id[retry_log.id].billing_attempt_count == 1
    assert by_id[block_log.id].status == "blocked"
    assert by_id[parent.id].amount_cents == by_id[settle_log.id].amount_cents
    assert refresh_calls == [parent.id]
    assert commit_calls == 2


@pytest.mark.asyncio
async def test_apply_provider_reconcile_plan_preserves_order_against_shared_private_balance(
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "private")

    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password="hashed",
        role="admin",
        balance_cents=300,
    )
    user = User(
        email="billing-private@example.com",
        username="billing_private",
        hashed_password="hashed",
        role="user",
        balance_cents=0,
    )
    db_session.add_all([admin, user])
    await db_session.commit()
    await db_session.refresh(admin)
    await db_session.refresh(user)

    service = BillingService(db_session)
    first = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="kimi-k2.6",
        task_type="multimodal",
        amount_cents=0,
        task_status="pending",
        provider_code="lingyaai",
        provider_request_id="req-first",
        billing_mode="provider_reconcile",
        billing_next_run_at=datetime.now(UTC),
    )
    second = await service.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="kimi-k2.6",
        task_type="multimodal",
        amount_cents=0,
        task_status="pending",
        provider_code="lingyaai",
        provider_request_id="req-second",
        billing_mode="provider_reconcile",
        billing_next_run_at=datetime.now(UTC),
    )
    first.billing_lock_token = "lock-token"
    second.billing_lock_token = "lock-token"
    await db_session.commit()

    first_bill = LingyaAiBillLookupResult.from_row(
        {"request_id": "req-first", "quota": 1_000_000, "prompt_tokens": 1, "completion_tokens": 1},
        billing_unit_per_yuan=500000,
        oneapi_request_id="req-first",
    )
    second_bill = LingyaAiBillLookupResult.from_row(
        {"request_id": "req-second", "quota": 1_000_000, "prompt_tokens": 1, "completion_tokens": 1},
        billing_unit_per_yuan=500000,
        oneapi_request_id="req-second",
    )
    plan = SimpleNamespace(
        settles=[
            SimpleNamespace(log_id=first.id, bill=first_bill),
            SimpleNamespace(log_id=second.id, bill=second_bill),
        ],
        retries=[],
        blocks=[],
    )

    await service.apply_provider_reconcile_plan(plan, lock_token="lock-token")

    await db_session.refresh(admin)
    await db_session.refresh(first)
    await db_session.refresh(second)

    assert first.status == "success"
    assert second.status == "blocked"
    assert second.params["manual_review_reason"] == "insufficient_balance_after_provider_success"
    assert admin.balance_cents == 100


@pytest.mark.asyncio
async def test_create_usage_log_is_idempotent_by_billing_key(db_session: AsyncSession):
    user = User(
        email="billing-key@example.com",
        username="billing_key",
        hashed_password="hashed",
        role="user",
        balance_cents=100,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user_id = user.id

    service = BillingService(db_session)
    first = await service.create_usage_log(
        user_id=user_id,
        task_id=None,
        model_name="gemini-3.1-pro-preview",
        task_type="image_analysis",
        amount_cents=4,
        task_status="success",
        billing_key="harness:image_analysis:conv-1:run-1:functions.analyze_image:1",
        params={"kind": "analyze_image"},
    )
    second = await service.create_usage_log(
        user_id=user_id,
        task_id=None,
        model_name="gemini-3.1-pro-preview",
        task_type="image_analysis",
        amount_cents=4,
        task_status="success",
        billing_key="harness:image_analysis:conv-1:run-1:functions.analyze_image:1",
        params={"kind": "analyze_image"},
    )

    rows = (
        await db_session.execute(
            select(UsageLog).where(
                UsageLog.user_id == user_id,
                UsageLog.task_type == "image_analysis",
            )
        )
    ).scalars().all()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0].billing_key == "harness:image_analysis:conv-1:run-1:functions.analyze_image:1"


@pytest.mark.asyncio
async def test_usage_log_billing_key_create_repairs_primary_key_collision(
    db_session: AsyncSession,
    monkeypatch,
):
    repo = UsageLogRepository(db_session)
    repairs: list[str] = []
    create_calls: list[UsageLog] = []

    async def fake_create(log: UsageLog):
        create_calls.append(log)
        if len(create_calls) == 1:
            log.id = 1931
            raise _duplicate_usage_log_primary_key_error()
        log.id = 1938
        return log

    async def fake_get_by_billing_key(_billing_key: str):
        return None

    async def fake_repair_auto_increment():
        repairs.append("repair")

    monkeypatch.setattr(repo, "create", fake_create)
    monkeypatch.setattr(repo, "get_by_billing_key", fake_get_by_billing_key)
    monkeypatch.setattr(repo, "_repair_mysql_auto_increment", fake_repair_auto_increment)

    log = UsageLog(
        user_id=1,
        parent_id=1920,
        task_id=None,
        model_name="gpt-5.5",
        model_label="Ollama (gpt-5.5)",
        task_type="image_analysis",
        billing_key="agent_harness:image_analysis:221c5b5e9b4e4c34acf6315031b7d968",
        amount_cents=0,
        amount_cents_original=0,
        status="success",
        billing_mode="provider_balance_sync",
        params={"input_tokens": 6198},
    )

    created, was_created = await repo.create_or_get_by_billing_key_with_created(log)

    assert was_created is True
    assert created.id == 1938
    assert repairs == ["repair"]
    assert len(create_calls) == 2
    assert create_calls[0] is log
    assert create_calls[1] is not log
    assert create_calls[1].billing_key == log.billing_key
