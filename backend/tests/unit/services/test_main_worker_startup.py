from __future__ import annotations

import importlib
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_lifespan_warms_agent_catalog(monkeypatch):
    scheduler_owner_calls: list[str] = []
    reconciler_calls: list[str] = []
    balance_calls: list[str] = []
    catalog_calls: list[str] = []

    class FakeWorker:
        def __init__(self, bucket: list[tuple[str, dict]]):
            self.bucket = bucket

        def start(self, **kwargs):
            self.bucket.append(("start", kwargs))

        async def warmup(self, **kwargs):
            self.bucket.append(("warmup", kwargs))

        def shutdown(self):
            self.bucket.append(("shutdown", {}))

    fake_reconciler = SimpleNamespace(
        start=lambda: reconciler_calls.append("start"),
        shutdown=_async_recorder(reconciler_calls, "shutdown"),
    )
    fake_balance_sync = SimpleNamespace(
        start=lambda: balance_calls.append("start"),
        shutdown=_async_recorder(balance_calls, "shutdown"),
    )
    fake_realtime_listener = SimpleNamespace(
        start=_async_noop(),
        stop=_async_noop(),
    )

    monkeypatch.setitem(
        sys.modules,
        "app.services.lingyaai_billing_reconciler",
        SimpleNamespace(lingyaai_billing_reconciler=fake_reconciler),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.provider_balance_sync",
        SimpleNamespace(provider_balance_sync_worker=fake_balance_sync),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.realtime_listener_manager",
        SimpleNamespace(RealtimeListenerManager=lambda: fake_realtime_listener),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.core.provider_balance_mode",
        SimpleNamespace(is_provider_balance_sync_enabled=lambda: False),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.background_scheduler_owner",
        SimpleNamespace(
            background_scheduler_owner=SimpleNamespace(
                start=lambda: scheduler_owner_calls.append("start"),
                shutdown=_async_recorder(scheduler_owner_calls, "shutdown"),
            )
        ),
    )

    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    main = importlib.import_module("app.main")

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.warmup_agent_catalog",
        _async_recorder(catalog_calls, "warmup"),
    )
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _fake_session())
    monkeypatch.setattr(main.app, "state", SimpleNamespace())
    async with main.lifespan(main.app):
        pass

    assert catalog_calls == ["warmup"]


@asynccontextmanager
async def _fake_session():
    yield object()


def _async_recorder(bucket: list[str], marker: str):
    async def _wrapped():
        bucket.append(marker)

    return _wrapped


def _async_noop():
    async def _wrapped(*args, **kwargs):
        return None

    return _wrapped


def test_app_does_not_expose_legacy_workspace_static_mount(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "app.services.lingyaai_billing_reconciler",
        SimpleNamespace(lingyaai_billing_reconciler=SimpleNamespace(start=lambda: None, shutdown=_async_noop())),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.provider_balance_sync",
        SimpleNamespace(provider_balance_sync_worker=SimpleNamespace(start=lambda: None, shutdown=_async_noop())),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.realtime_listener_manager",
        SimpleNamespace(RealtimeListenerManager=lambda: SimpleNamespace(start=_async_noop(), stop=_async_noop())),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.core.provider_balance_mode",
        SimpleNamespace(is_provider_balance_sync_enabled=lambda: False),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.background_scheduler_owner",
        SimpleNamespace(
            background_scheduler_owner=SimpleNamespace(
                start=lambda: None,
                shutdown=_async_noop(),
            )
        ),
    )

    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    main = importlib.import_module("app.main")

    mounted_paths = {getattr(route, "path", "") for route in main.app.routes}

    assert "/api/v1/workspace" not in mounted_paths
