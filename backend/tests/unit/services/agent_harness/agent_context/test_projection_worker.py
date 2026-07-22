from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.services.agent_harness.agent_context import projection_worker


@pytest.mark.asyncio
async def test_context_worker_runs_regardless_of_active_run_pressure(monkeypatch):
    """The old pause-while-active-runs behaviour has been removed.

    The worker no longer owns prompt-shaping projections, so it does not need
    to back off when runs are active; it only refreshes the recall sidecar.
    """
    monkeypatch.setattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(settings, "HARNESS_AGENT_CONTEXT_CONCURRENCY", 1)

    processed_batches = 0

    def _process_context_projection_batch(*, batch_size):
        nonlocal processed_batches
        assert batch_size == 1
        processed_batches += 1
        return False

    async def _wait_agent_context_wakeup(*, timeout_seconds):
        await asyncio.sleep(min(float(timeout_seconds), 0.01))

    monkeypatch.setattr(projection_worker, "process_context_projection_batch", _process_context_projection_batch)
    monkeypatch.setattr(projection_worker, "wait_agent_context_wakeup", _wait_agent_context_wakeup)

    loop = projection_worker.AgentContextWorkerLoop()
    # Caller still passes active_run_count for compatibility, but it should
    # have no effect on whether the worker processes.
    task = asyncio.create_task(loop.run(active_run_count=lambda: 1))
    try:
        for _ in range(20):
            if processed_batches:
                break
            await asyncio.sleep(0.01)
        assert processed_batches > 0
    finally:
        await loop.shutdown()
        await asyncio.wait_for(task, timeout=1)
