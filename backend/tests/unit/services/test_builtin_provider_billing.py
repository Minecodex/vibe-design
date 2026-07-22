from types import SimpleNamespace
from datetime import UTC, datetime

import pytest

from app.services.billing_service import BillingService
from app.services.builtin_provider import (
    LingyaAiBillLookupResult,
    LingyaAiBuiltinProvider,
    calculate_lingyaai_amount_cents,
)


@pytest.fixture(autouse=True)
def _disable_provider_balance_sync_by_default(monkeypatch):
    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: False)


def test_calculate_lingyaai_amount_cents_uses_minimum_one_cent():
    assert calculate_lingyaai_amount_cents(quota=1011, billing_unit_per_yuan=500000) == 1


def test_calculate_lingyaai_amount_cents_rounds_up_to_next_cent():
    assert calculate_lingyaai_amount_cents(quota=500001, billing_unit_per_yuan=500000) == 101


def test_calculate_lingyaai_amount_cents_rejects_invalid_unit():
    with pytest.raises(ValueError, match="billing_unit_per_yuan"):
        calculate_lingyaai_amount_cents(quota=1000, billing_unit_per_yuan=0)


def test_lingyaai_bill_lookup_result_extracts_usage_fields():
    row = {
        "request_id": "req-1",
        "quota": 1011,
        "prompt_tokens": 19,
        "completion_tokens": 104,
    }

    result = LingyaAiBillLookupResult.from_row(
        row,
        billing_unit_per_yuan=500000,
        oneapi_request_id="req-1",
        request_id="chatcmpl-1",
    )

    assert result.amount_cents == 1
    assert result.prompt_tokens == 19
    assert result.completion_tokens == 104
    assert result.raw == row


def test_lingyaai_bill_lookup_matches_trace_id_when_request_header_id_differs():
    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    result = provider.match_bill_from_rows(
        [
            {
                "request_id": "image-response-1",
                "quota": 1011,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        ],
        provider_request_id="oneapi-header-1",
        provider_trace_id="image-response-1",
    )

    assert result is not None
    assert result.oneapi_request_id == "oneapi-header-1"
    assert result.request_id == "image-response-1"
    assert result.raw["request_id"] == "image-response-1"


def test_lingyaai_provider_base_url_uses_settings(monkeypatch):
    monkeypatch.setattr("app.services.builtin_provider.settings.LINGYAAI_BASE_URL", "https://example.test/")

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    assert provider.base_url == "https://example.test"


@pytest.mark.asyncio
async def test_lingyaai_bill_lookup_adds_video_task_adjustment_rows(monkeypatch):
    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    rows = [
        {
            "request_id": "oneapi-video-1",
            "quota": 1162500,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        },
        {
            "request_id": "adjustment-row",
            "quota": 11681,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "other": "{\"task_id\":\"task_video_1\",\"seconds\":4,\"size\":0.465}",
        },
    ]

    async def fake_request(method, path, **kwargs):
        assert method == "GET"
        assert path == "/api/log/token"
        return {"data": rows}, {}

    monkeypatch.setattr(provider, "_request", fake_request)

    result = await provider.lookup_bill(
        "oneapi-video-1",
        request_id=None,
        task_id="task_video_1",
    )

    assert result is not None
    assert result.quota == 1174181
    assert result.amount_cents == 235
    assert result.raw["primary"]["request_id"] == "oneapi-video-1"
    assert result.raw["task_rows"][0]["request_id"] == "adjustment-row"


@pytest.mark.asyncio
async def test_lingyaai_bill_lookup_keeps_request_id_as_required_anchor(monkeypatch):
    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)
    attempts = 0

    async def fake_request(method, path, **kwargs):
        nonlocal attempts
        attempts += 1
        return {
            "data": [
                {
                    "request_id": "adjustment-row",
                    "quota": 11681,
                    "other": "{\"task_id\":\"task_video_1\"}",
                }
            ]
        }, {}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr("app.services.builtin_provider.asyncio.sleep", fake_sleep)

    result = await provider.lookup_bill(
        "oneapi-video-1",
        request_id=None,
        task_id="task_video_1",
    )

    assert result is None
    assert attempts == 3


@pytest.mark.asyncio
async def test_finalize_lingyaai_generation_billing_creates_pending_reconcile_log(monkeypatch):
    service = BillingService(db=None)
    created_logs = []

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 88
            created_logs.append(log)
            return log

    async def fake_deduct(user_id, amount_cents):
        raise AssertionError("LingyaAI generation billing is reconciled asynchronously")

    service.usage_repo = FakeUsageRepo()
    monkeypatch.setattr(service, "deduct_balance", fake_deduct)

    task = SimpleNamespace(
        id=44,
        user_id=9,
        model_name="Gemini-3.1-flash-image-preview",
        task_type="text2image",
        status="completed",
        result_url="https://example.com/image.png",
        builtin_provider_code="lingyaai",
        provider_request_id="oneapi-1",
        provider_trace_id="trace-1",
        external_task_id="lingyaai-sync:oneapi-1",
        params={},
        created_at=datetime(2026, 6, 12, 1, 0, 0, tzinfo=UTC),
        terminalized_at=datetime(2026, 6, 12, 1, 0, 9, tzinfo=UTC),
        updated_at=datetime(2026, 6, 12, 1, 0, 8, tzinfo=UTC),
    )

    log = await service.finalize_lingyaai_generation_billing(task)

    assert log.id == 88
    assert log.status == "pending"
    assert log.amount_cents == 0
    assert log.provider_code == "lingyaai"
    assert log.provider_request_id == "oneapi-1"
    assert log.provider_trace_id == "trace-1"
    assert log.billing_mode == "provider_reconcile"
    assert log.elapsed_ms == 9000


@pytest.mark.asyncio
async def test_finalize_lingyaai_video_billing_stores_external_task_id_for_reconcile(monkeypatch):
    service = BillingService(db=None)

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 188
            return log

    service.usage_repo = FakeUsageRepo()

    async def fake_deduct(user_id, amount_cents):
        raise AssertionError("LingyaAI video billing is reconciled asynchronously")

    monkeypatch.setattr(service, "deduct_balance", fake_deduct)

    task = SimpleNamespace(
        id=144,
        user_id=9,
        model_name="doubao-seedance-2-0-260128",
        task_type="text2video",
        status="completed",
        external_task_id="task_video_1",
        result_url="https://example.com/video.mp4",
        builtin_provider_code="lingyaai",
        provider_request_id="oneapi-video-1",
        provider_trace_id="trace-video-1",
        params={},
        created_at=datetime(2026, 6, 12, 1, 0, 0, tzinfo=UTC),
        terminalized_at=None,
        updated_at=datetime(2026, 6, 12, 1, 0, 12, 500000, tzinfo=UTC),
    )

    log = await service.finalize_lingyaai_generation_billing(task)

    assert log.status == "pending"
    assert log.amount_cents == 0
    assert log.provider_request_id == "oneapi-video-1"
    assert log.provider_trace_id == "trace-video-1"
    assert log.provider_task_id == "task_video_1"
    assert log.elapsed_ms == 12500


@pytest.mark.asyncio
async def test_finalize_lingyaai_generation_billing_blocks_when_request_id_missing(monkeypatch):
    service = BillingService(db=None)

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 89
            return log

    async def fail_deduct(user_id, amount_cents):
        raise AssertionError("missing LingyaAI bill must not deduct balance")

    service.usage_repo = FakeUsageRepo()
    monkeypatch.setattr(service, "deduct_balance", fail_deduct)

    task = SimpleNamespace(
        id=45,
        user_id=9,
        model_name="kling-v3-video-generation",
        task_type="text2video",
        status="completed",
        external_task_id="task-video-missing",
        result_url="https://example.com/video.mp4",
        builtin_provider_code="lingyaai",
        provider_request_id=None,
        provider_trace_id=None,
        params={},
    )

    log = await service.finalize_lingyaai_generation_billing(task)

    assert log.status == "blocked"
    assert log.amount_cents == 0
    assert log.params["manual_review_required"] is True
    assert log.params["manual_review_reason"] == "lingyaai_missing_oneapi_request_id"


@pytest.mark.asyncio
async def test_finalize_lingyaai_generation_billing_links_agent_parent(monkeypatch):
    service = BillingService(db=None)
    refreshed: list[int] = []

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 90
            return log

    service.usage_repo = FakeUsageRepo()
    async def fake_refresh(parent_id, *, finished_at=None, params=None):
        refreshed.append(parent_id)
        return None

    monkeypatch.setattr(service, "refresh_parent_usage_log", fake_refresh)

    task = SimpleNamespace(
        id=46,
        user_id=9,
        model_name="Gemini-3.1-flash-image-preview",
        task_type="text2image",
        updated_at=None,
        result_url="https://example.com/image.png",
        status="completed",
        builtin_provider_code="lingyaai",
        provider_request_id="oneapi-parent",
        provider_trace_id=None,
        external_task_id="lingyaai-sync:oneapi-parent",
        params={
            "parent_usage_log_id": 123,
            "agent_run_id": "run-1",
        },
    )

    log = await service.finalize_lingyaai_generation_billing(task)

    assert log.parent_id == 123
    assert log.status == "pending"
    assert log.provider_request_id == "oneapi-parent"
    assert refreshed == [123]


@pytest.mark.asyncio
async def test_finalize_apimart_generation_billing_creates_postpaid_agent_child(monkeypatch):
    service = BillingService(db=None)
    created_logs = []
    deducted: list[tuple[int, int]] = []
    refreshed: list[int] = []

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 91
            created_logs.append(log)
            return log

    service.usage_repo = FakeUsageRepo()

    async def fake_get_balance(user_id):
        return 10000

    async def fake_deduct(user_id, amount_cents):
        deducted.append((user_id, amount_cents))
        return True

    async def fake_refresh(parent_id, *, finished_at=None, params=None):
        refreshed.append(parent_id)
        return None

    monkeypatch.setattr(service, "get_balance", fake_get_balance)
    monkeypatch.setattr(service, "deduct_balance", fake_deduct)
    monkeypatch.setattr(service, "refresh_parent_usage_log", fake_refresh)

    task = SimpleNamespace(
        id=47,
        user_id=9,
        model_name="gpt-image-2",
        task_type="text2image",
        status="completed",
        result_url="https://example.com/image.png",
        external_task_id="remote-image-task-47",
        created_at=datetime(2026, 6, 12, 2, 0, 0, tzinfo=UTC),
        terminalized_at=datetime(2026, 6, 12, 2, 0, 21, tzinfo=UTC),
        updated_at=datetime(2026, 6, 12, 2, 0, 20, tzinfo=UTC),
        params={
            "resolution": "1K",
            "parent_usage_log_id": 456,
            "agent_run_id": "run-2",
            "artifact_ref": "artifact_ref:image",
        },
    )

    log = await service.finalize_apimart_generation_billing(task)

    assert log.status == "success"
    assert log.parent_id == 456
    assert log.amount_cents > 0
    assert deducted == [(9, log.amount_cents)]
    assert refreshed == [456]
    assert log.elapsed_ms == 21000
    assert created_logs[0].params["provider_code"] == "apimart"
    assert created_logs[0].params["request_id"] == "remote-image-task-47"
    assert created_logs[0].params["generation_task"]["external_task_id"] == "remote-image-task-47"


@pytest.mark.asyncio
async def test_finalize_apimart_generation_billing_records_zero_in_provider_balance_sync_mode(monkeypatch):
    service = BillingService(db=None)
    deducted: list[tuple[int, int]] = []

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 192
            return log

    service.usage_repo = FakeUsageRepo()

    async def fake_deduct(user_id, amount_cents):
        deducted.append((user_id, amount_cents))
        return True

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: True)
    monkeypatch.setattr(service, "deduct_balance", fake_deduct)

    task = SimpleNamespace(
        id=48,
        user_id=9,
        model_name="gpt-image-2",
        task_type="text2image",
        status="completed",
        result_url="https://example.com/image.png",
        external_task_id="remote-image-task-48",
        updated_at=None,
        params={"resolution": "1K"},
    )

    log = await service.finalize_apimart_generation_billing(task)

    assert log.status == "success"
    assert log.amount_cents == 0
    assert log.amount_cents_original == 0
    assert log.billing_mode == "provider_balance_sync"
    assert deducted == []


@pytest.mark.asyncio
async def test_finalize_apimart_generation_billing_marks_reserved_log_success_without_second_charge(monkeypatch):
    service = BillingService(db=None)
    deducted: list[tuple[int, int]] = []
    refreshed: list[int] = []
    existing_log = SimpleNamespace(
        id=193,
        status="pending",
        parent_id=456,
        amount_cents=40,
        amount_cents_original=40,
        params={"provider_code": "apimart"},
        billing_locked_until=None,
        billing_lock_token=None,
        billing_finalized_at=None,
    )

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            assert task_id == 49
            return existing_log

        async def claim_log_lock(self, **_kwargs):
            return existing_log

    service.usage_repo = FakeUsageRepo()

    async def fake_get_balance(user_id):
        return 10000

    async def fake_deduct(user_id, amount_cents):
        deducted.append((user_id, amount_cents))
        return True

    async def fake_refresh(parent_id, *, finished_at=None, params=None):
        refreshed.append(parent_id)
        return None

    monkeypatch.setattr("app.services.billing_service.is_provider_balance_sync_enabled", lambda: False)
    monkeypatch.setattr(service, "get_balance", fake_get_balance)
    monkeypatch.setattr(service, "deduct_balance", fake_deduct)
    monkeypatch.setattr(service, "refresh_parent_usage_log", fake_refresh)

    task = SimpleNamespace(
        id=49,
        user_id=9,
        model_name="gpt-image-2",
        task_type="text2image",
        status="completed",
        result_url="https://example.com/image.png",
        external_task_id="remote-image-task-49",
        created_at=datetime(2026, 6, 12, 3, 0, 0, tzinfo=UTC),
        terminalized_at=datetime(2026, 6, 12, 3, 0, 7, tzinfo=UTC),
        updated_at=datetime(2026, 6, 12, 3, 0, 6, tzinfo=UTC),
        params={
            "resolution": "1K",
            "parent_usage_log_id": 456,
            "agent_run_id": "run-2",
            "artifact_ref": "artifact_ref:image",
        },
    )

    log = await service.finalize_apimart_generation_billing(task)

    assert log is existing_log
    assert log.status == "success"
    assert log.amount_cents == 40
    assert log.amount_cents_original == 40
    assert log.elapsed_ms == 7000
    assert log.params["generation_task"]["task_id"] == 49
    assert deducted == []
    assert refreshed == [456]


@pytest.mark.asyncio
async def test_finalize_apimart_generation_billing_skips_charge_when_claim_is_already_owned(monkeypatch):
    service = BillingService(db=None)
    deducted: list[tuple[int, int]] = []
    refreshed: list[int] = []
    existing_log = SimpleNamespace(
        id=191,
        status="pending",
        parent_id=456,
        amount_cents=0,
        amount_cents_original=0,
        params={},
    )

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            assert task_id == 47
            return existing_log

        async def claim_log_lock(self, **_kwargs):
            return None

    service.usage_repo = FakeUsageRepo()

    async def fake_get_balance(user_id):
        return 10000

    async def fake_deduct(user_id, amount_cents):
        deducted.append((user_id, amount_cents))
        return True

    async def fake_refresh(parent_id, *, finished_at=None, params=None):
        refreshed.append(parent_id)
        return None

    monkeypatch.setattr(service, "get_balance", fake_get_balance)
    monkeypatch.setattr(service, "deduct_balance", fake_deduct)
    monkeypatch.setattr(service, "refresh_parent_usage_log", fake_refresh)

    task = SimpleNamespace(
        id=47,
        user_id=9,
        model_name="gpt-image-2",
        task_type="text2image",
        status="completed",
        result_url="https://example.com/image.png",
        external_task_id="remote-image-task-47",
        updated_at=None,
        params={
            "resolution": "1K",
            "parent_usage_log_id": 456,
            "agent_run_id": "run-2",
            "artifact_ref": "artifact_ref:image",
        },
    )

    log = await service.finalize_apimart_generation_billing(task)

    assert log is existing_log
    assert deducted == []
    assert refreshed == [456]


@pytest.mark.asyncio
async def test_finalize_ollama_generation_billing_records_elapsed_ms(monkeypatch):
    service = BillingService(db=None)
    refreshed: list[int] = []

    class FakeUsageRepo:
        async def get_by_task_id(self, task_id):
            return None

        async def create(self, log):
            log.id = 777
            return log

    service.usage_repo = FakeUsageRepo()

    async def fake_refresh(parent_id, *, finished_at=None, params=None):
        refreshed.append(parent_id)
        return None

    monkeypatch.setattr(service, "refresh_parent_usage_log", fake_refresh)

    task = SimpleNamespace(
        id=77,
        user_id=9,
        provider_code="ollama",
        model_name="gpt-image-2",
        task_type="text2image",
        status="completed",
        result_url="/api/v1/uploads/generated/test.png",
        external_task_id="ollama-sync:77",
        created_at=datetime(2026, 6, 12, 4, 0, 0, tzinfo=UTC),
        terminalized_at=datetime(2026, 6, 12, 4, 0, 33, 250000, tzinfo=UTC),
        updated_at=datetime(2026, 6, 12, 4, 0, 34, tzinfo=UTC),
        params={"parent_usage_log_id": 900},
    )

    log = await service.finalize_ollama_generation_billing(task)

    assert log.status == "success"
    assert log.provider_code == "ollama"
    assert log.elapsed_ms == 33250
    assert refreshed == [900]
