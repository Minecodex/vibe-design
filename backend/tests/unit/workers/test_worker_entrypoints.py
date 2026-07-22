from __future__ import annotations

import asyncio

import pytest


def test_agent_worker_entrypoint_keeps_agent_domains_together():
    from app.workers import agent_worker

    assert agent_worker.WorkflowStepWorkerLoop is not None
    assert agent_worker.AgentContextWorkerLoop is not None


def test_background_worker_entrypoint_keeps_non_agent_domains_together():
    from app.workers import background_worker

    assert background_worker.GenerationBackgroundWorkerLoop is not None
    assert background_worker.BillingBackgroundWorkerLoop is not None
    assert background_worker.AssetThumbnailBackgroundWorkerLoop is not None


@pytest.mark.asyncio
async def test_agent_worker_exits_when_agent_run_loop_fails(monkeypatch):
    from app.workers import agent_worker

    refresh_calls = 0
    catalog_ready_calls = 0

    async def _refresh_license_runtime():
        nonlocal refresh_calls
        refresh_calls += 1

    async def _wait_agent_catalog_ready():
        nonlocal catalog_ready_calls
        catalog_ready_calls += 1

    class _FailingRunLoop:
        async def run(self):
            raise RuntimeError("agent loop failed")

        async def shutdown(self):
            return None

    class _IdleContextLoop:
        async def run(self, *, active_run_count):
            del active_run_count
            await asyncio.Event().wait()

        async def shutdown(self):
            return None

    monkeypatch.setattr(agent_worker, "WorkflowStepWorkerLoop", _FailingRunLoop)
    monkeypatch.setattr(agent_worker, "AgentContextWorkerLoop", _IdleContextLoop)
    monkeypatch.setattr(agent_worker, "refresh_license_runtime", _refresh_license_runtime)
    monkeypatch.setattr(agent_worker, "wait_agent_catalog_ready", _wait_agent_catalog_ready)

    with pytest.raises(RuntimeError, match="agent loop failed"):
        await asyncio.wait_for(agent_worker._main(), timeout=1)
    assert refresh_calls == 1
    assert catalog_ready_calls == 1


@pytest.mark.asyncio
async def test_agent_worker_retries_until_agent_catalog_is_ready(monkeypatch):
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError
    from app.workers import agent_worker

    calls = 0

    async def _wait_agent_catalog_ready():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AgentCatalogUnavailableError("agent catalog not ready")

    monkeypatch.setattr(agent_worker, "AGENT_CATALOG_RETRY_SLEEP_SECONDS", 0)
    monkeypatch.setattr(agent_worker, "wait_agent_catalog_ready", _wait_agent_catalog_ready)

    await agent_worker._wait_agent_catalog_ready_for_worker()

    assert calls == 2


@pytest.mark.asyncio
async def test_background_worker_exits_when_domain_loop_fails(monkeypatch):
    from app.workers import background_worker

    refresh_calls = 0

    async def _refresh_license_runtime():
        nonlocal refresh_calls
        refresh_calls += 1

    class _FailingLoop:
        async def run(self):
            raise RuntimeError("generation loop failed")

    class _IdleLoop:
        async def run(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(background_worker, "GenerationBackgroundWorkerLoop", _FailingLoop)
    monkeypatch.setattr(background_worker, "BillingBackgroundWorkerLoop", _IdleLoop)
    monkeypatch.setattr(background_worker, "AssetThumbnailBackgroundWorkerLoop", _IdleLoop)
    monkeypatch.setattr(background_worker, "refresh_license_runtime", _refresh_license_runtime)

    with pytest.raises(RuntimeError, match="generation loop failed"):
        await asyncio.wait_for(background_worker._main(), timeout=1)
    assert refresh_calls == 1


def _async_noop():
    async def _wrapped(*args, **kwargs):
        return None

    return _wrapped
