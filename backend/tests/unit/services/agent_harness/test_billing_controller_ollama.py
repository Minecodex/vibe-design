from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent_harness.runtime.execution_support import billing_controller


class _AsyncSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_record_model_usage_billing_records_ollama_as_zero_cost(monkeypatch):
    created_logs: list[dict] = []
    refreshed_parent_ids: list[int] = []
    charge_calls: list[dict] = []

    class FakeBillingService:
        def __init__(self, _db):
            pass

        async def create_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            log = SimpleNamespace(id=123)
            if kwargs.get("return_created"):
                return log, True
            return log

        async def refresh_parent_usage_log(self, parent_id):
            refreshed_parent_ids.append(parent_id)

    async def fake_charge_harness_amount(**kwargs):
        charge_calls.append(kwargs)
        return 99

    monkeypatch.setattr(billing_controller, "get_db_session_factory", lambda: _AsyncSession)
    monkeypatch.setattr(
        "app.services.billing_service.BillingService",
        FakeBillingService,
    )
    monkeypatch.setattr(billing_controller, "charge_harness_amount", fake_charge_harness_amount)

    ctx = SimpleNamespace(
        run_id="run-1",
        conversation_id="conv-1",
        parent_run_id=None,
        parent_usage_log_id=55,
        is_subagent=False,
        record_billing=lambda **kwargs: created_logs.append({"ctx_record_billing": kwargs}),
    )

    recorded = await billing_controller.record_model_usage_billing(
        user_id=7,
        ctx=ctx,
        model_name="local-vision",
        usage={"input_tokens": 12, "output_tokens": 3, "provider_code": "ollama"},
        elapsed_ms=42,
        kind="home_turn_router",
        billing_key="preflight:ollama",
    )

    assert recorded is True
    assert charge_calls == []
    assert refreshed_parent_ids == [55]
    usage_log = next(item for item in created_logs if "ctx_record_billing" not in item)
    assert usage_log["amount_cents"] == 0
    assert usage_log["provider_code"] == "ollama"
    assert usage_log["billing_mode"] == "local_zero_cost"
    assert usage_log["billing_key"] == "preflight:ollama"
