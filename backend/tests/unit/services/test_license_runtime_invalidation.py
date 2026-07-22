from __future__ import annotations

import pytest

from app.core.config import Settings, settings
from app.core.license_runtime import LicenseRuntimeState
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.license_runtime_invalidation import (
    publish_license_runtime_invalidation,
    start_license_runtime_invalidation_listener,
)


@pytest.mark.asyncio
async def test_license_runtime_invalidation_listener_clears_local_cache(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.license_runtime_invalidation.get_redis_coordinator",
        lambda: coordinator,
    )
    runtime = LicenseRuntimeState(ttl_seconds=3600)
    runtime._last_refresh_monotonic = 123.0

    unsubscribe = await start_license_runtime_invalidation_listener(runtime_state=runtime)
    await publish_license_runtime_invalidation(reason="license_activation")
    unsubscribe()

    assert runtime._last_refresh_monotonic is None


@pytest.mark.asyncio
async def test_license_runtime_invalidation_payload_omits_license_secrets(monkeypatch):
    published: list[dict] = []

    class FakeKeys:
        def build(self, *, domain, purpose, resource_parts=()):
            return f"{domain}:{purpose}:active"

    class FakeCoordinator:
        keys = FakeKeys()

        async def publish(self, topic, envelope):
            published.append(dict(envelope))
            return {"published": True, "delivered": 1}

    monkeypatch.setattr(
        "app.services.license_runtime_invalidation.get_redis_coordinator",
        lambda: FakeCoordinator(),
    )

    await publish_license_runtime_invalidation(reason="license_activation")

    assert published
    payload_text = repr(published[0]).lower()
    assert "license_token" not in payload_text
    assert "api_key" not in payload_text
    assert "sk-" not in payload_text


@pytest.mark.asyncio
async def test_license_runtime_non_private_refresh_remains_active_without_schema_or_redis_state(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_API_KEY", "sk-default-provider")
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_CODE", "apimart")
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN", 10000)
    runtime = LicenseRuntimeState(ttl_seconds=3600)
    runtime.invalidate()

    class FailingDb:
        def __getattr__(self, name):
            raise AssertionError(f"non-private runtime must not read license DB: {name}")

    status = await runtime.get_status(FailingDb())

    assert status.status == "active"
    assert status.expired is False
    assert status.edition is None
    assert settings.BUILTIN_PROVIDER_API_KEY == "sk-default-provider"
    assert settings.BUILTIN_PROVIDER_CODE == "apimart"
    assert settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN == 10000
