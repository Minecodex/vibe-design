from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.agent_harness.workflow import scheduler as workflow_scheduler
from app.services.agent_harness.workflow import worker_loop


@pytest.mark.asyncio
@pytest.mark.load
async def test_agent_worker_runs_ten_light_requests_with_eight_active_slots(monkeypatch):
    monkeypatch.setattr(settings, "HARNESS_WORKFLOW_MAX_ACTIVE_STEPS", 8)

    pending = [SimpleNamespace(id=index, step_id=f"step-{index}") for index in range(10)]
    completed: list[int] = []
    active = 0
    max_active = 0
    eight_started = asyncio.Event()
    release_first_wave = asyncio.Event()

    async def _claim_next_step_async(*, worker_id, lease_seconds):
        del worker_id, lease_seconds
        if not pending:
            return None
        return pending.pop(0)

    async def _execute_step(self, step, *, wake_source=None):
        del self
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 8:
            eight_started.set()
        if step.id < 8:
            await release_first_wave.wait()
        else:
            await asyncio.sleep(0)
        completed.append(step.id)
        active -= 1

    async def _wait_agent_run_wakeup(*, timeout_seconds):
        await asyncio.sleep(min(float(timeout_seconds), 0.01))

    monkeypatch.setattr(workflow_scheduler, "claim_next_step_async", _claim_next_step_async)
    monkeypatch.setattr(workflow_scheduler.WorkflowStepScheduler, "_execute_step", _execute_step)
    monkeypatch.setattr(workflow_scheduler, "wait_agent_run_wakeup", _wait_agent_run_wakeup)

    loop = worker_loop.WorkflowStepWorkerLoop(worker_id="load-test-worker")
    task = asyncio.create_task(loop.run())
    try:
        await asyncio.wait_for(eight_started.wait(), timeout=1)
        await asyncio.sleep(0.03)
        assert max_active == 8
        assert len(pending) == 2

        release_first_wave.set()
        for _ in range(100):
            if len(completed) == 10:
                break
            await asyncio.sleep(0.01)
        assert sorted(completed) == list(range(10))
        assert max_active == 8
    finally:
        release_first_wave.set()
        await loop.shutdown()
        await asyncio.wait_for(task, timeout=1)
