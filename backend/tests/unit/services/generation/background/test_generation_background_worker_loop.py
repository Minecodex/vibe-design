from __future__ import annotations

import asyncio

import pytest

from app.services.generation.background import worker_loop as generation_loop_mod
from app.services.generation.background.worker_loop import GenerationBackgroundWorkerLoop


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def start(self) -> None:
        self.events.append("start")

    async def shutdown(self) -> None:
        self.events.append("shutdown")


async def _run_loop_until_idle_then_cancel(loop: GenerationBackgroundWorkerLoop) -> None:
    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_generation_loop_starts_and_shuts_down_scheduler_owner(monkeypatch):
    owner = _Recorder()
    monkeypatch.setattr(generation_loop_mod, "background_scheduler_owner", owner)

    await _run_loop_until_idle_then_cancel(GenerationBackgroundWorkerLoop())

    assert owner.events == ["start", "shutdown"]


@pytest.mark.asyncio
async def test_generation_loop_propagates_start_failure_without_shutdown(monkeypatch):
    """The current implementation calls start() *outside* the try/finally,
    so a start-time exception bubbles up before any shutdown attempt."""

    class _ExplodingOwner:
        def __init__(self) -> None:
            self.shutdown_called = False

        def start(self) -> None:
            raise RuntimeError("scheduler owner init failed")

        async def shutdown(self) -> None:
            self.shutdown_called = True

    owner = _ExplodingOwner()
    monkeypatch.setattr(generation_loop_mod, "background_scheduler_owner", owner)

    with pytest.raises(RuntimeError, match="scheduler owner init failed"):
        await GenerationBackgroundWorkerLoop().run()
    assert owner.shutdown_called is False


@pytest.mark.asyncio
async def test_generation_loop_shutdown_runs_on_unrelated_cancel(monkeypatch):
    """If the idle wait is cancelled externally (e.g. uvicorn shutdown),
    the finally block must reach the adapter's shutdown."""
    owner = _Recorder()
    monkeypatch.setattr(generation_loop_mod, "background_scheduler_owner", owner)

    loop = GenerationBackgroundWorkerLoop()
    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert owner.events == ["start"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert owner.events[-1] == "shutdown"
