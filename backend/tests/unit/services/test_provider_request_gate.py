from types import SimpleNamespace

import pytest

from app.services import provider_request_gate as gate_mod
from app.services.provider_request_gate import ProviderRequestGate, provider_rate_limit_for_operation


def test_provider_rate_limit_for_operation_uses_unified_settings(monkeypatch):
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_LIMIT", 11)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_WINDOW_SECONDS", 12)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_GENERATION_QUERY_LIMIT", 21)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_GENERATION_QUERY_WINDOW_SECONDS", 22)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_LIMIT", 31)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_WINDOW_SECONDS", 32)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_BALANCE_FETCH_LIMIT", 41)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_BALANCE_FETCH_WINDOW_SECONDS", 42)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT", 51)
    monkeypatch.setattr(gate_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS", 52)

    assert provider_rate_limit_for_operation("generation_submit") == (11, 12.0)
    assert provider_rate_limit_for_operation("generation_query") == (21, 22.0)
    assert provider_rate_limit_for_operation("result_download") == (31, 32.0)
    assert provider_rate_limit_for_operation("balance_fetch") == (41, 42.0)
    assert provider_rate_limit_for_operation("billing_fetch") == (51, 52.0)


def test_legacy_provider_rate_limit_settings_are_not_exposed():
    legacy_names = [
        "PROVIDER_REQUEST_SUBMIT_LIMIT",
        "PROVIDER_REQUEST_SUBMIT_WINDOW_SECONDS",
        "PROVIDER_REQUEST_QUERY_LIMIT",
        "PROVIDER_REQUEST_QUERY_WINDOW_SECONDS",
        "PROVIDER_BALANCE_SYNC_WINDOW_SECONDS",
        "PROVIDER_BALANCE_SYNC_MAX_FETCHES_PER_WINDOW",
        "LINGYAAI_BILLING_FETCH_WINDOW_SECONDS",
        "LINGYAAI_BILLING_MAX_FETCHES_PER_WINDOW",
    ]

    assert all(not hasattr(gate_mod.settings, name) for name in legacy_names)


@pytest.mark.asyncio
async def test_provider_request_gate_returns_deferred_decision_without_raising(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakePolicy:
        def __init__(self, *, namespace):
            calls.append({"namespace": namespace})

        async def allow(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(allowed=False, retry_after_seconds=7.5)

    monkeypatch.setattr(gate_mod, "ProviderRequestPolicy", FakePolicy)

    decision = await ProviderRequestGate(namespace="test-provider-ops").allow(
        provider="apimart",
        operation="result_download",
        priority="background",
    )

    assert decision.allowed is False
    assert decision.retry_after_seconds == 7.5
    assert decision.deferred_until is not None
    assert calls[0] == {"namespace": "test-provider-ops"}
    assert calls[1]["provider"] == "apimart"
    assert calls[1]["operation"] == "result_download"
    assert calls[1]["priority"] == "background"
    assert calls[1]["limit"] == gate_mod.settings.PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_LIMIT
