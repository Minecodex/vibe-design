from __future__ import annotations

import pytest

from app.services.provider_request_policy import ProviderRequestPolicy


@pytest.mark.asyncio
async def test_provider_request_policy_rate_limits_by_provider_operation_namespace_and_priority(monkeypatch):
    calls: list[tuple[str, int, float]] = []

    class FakeKeys:
        def build(self, *, domain, purpose, resource_parts=()):
            return ":".join([domain, purpose, *resource_parts])

    class FakeCoordinator:
        keys = FakeKeys()

        async def rate_limit(self, bucket, *, limit, window_seconds):
            calls.append((bucket, limit, window_seconds))
            return {"allowed": len(calls) == 1, "retry_after_seconds": 3.5 if len(calls) > 1 else 0.0}

    monkeypatch.setattr("app.services.provider_request_policy.get_redis_coordinator", lambda: FakeCoordinator())

    policy = ProviderRequestPolicy(namespace="private-a")

    first = await policy.allow(provider="lingyaai", operation="generation_submit", priority="normal", limit=1, window_seconds=30)
    second = await policy.allow(provider="lingyaai", operation="generation_submit", priority="normal", limit=1, window_seconds=30)

    assert first.allowed is True
    assert first.retry_after_seconds == 0.0
    assert second.allowed is False
    assert second.retry_after_seconds == 3.5
    assert calls == [
        ("provider-request:rate-limit:private-a:lingyaai:generation_submit:normal", 1, 30),
        ("provider-request:rate-limit:private-a:lingyaai:generation_submit:normal", 1, 30),
    ]
