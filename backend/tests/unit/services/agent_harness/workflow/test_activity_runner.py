from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future

import pytest

from app.services.agent_harness.workflow.activity_runner import WorkflowActivityRunner


@pytest.mark.asyncio
async def test_activity_runner_uses_configurable_parallel_activity_loops():
    runner = WorkflowActivityRunner(workers=2)

    async def blocking_activity(label: str) -> str:
        time.sleep(0.2)
        return label

    started = time.perf_counter()
    results = await asyncio.gather(
        asyncio.wrap_future(runner.submit(blocking_activity("a"))),
        asyncio.wrap_future(runner.submit(blocking_activity("b"))),
    )

    assert sorted(results) == ["a", "b"]
    assert time.perf_counter() - started < 0.35


def test_activity_runner_dispatches_to_least_in_flight_loop():
    class _FakeLoop:
        def __init__(self) -> None:
            self.futures: list[Future] = []

        def submit(self, coro):
            coro.close()  # avoid "coroutine was never awaited" warnings
            future: Future = Future()
            self.futures.append(future)
            return future

    runner = WorkflowActivityRunner.__new__(WorkflowActivityRunner)
    runner.workers = 2
    runner._loops = [_FakeLoop(), _FakeLoop()]
    runner._inflight = [0, 0]
    runner._lock = threading.Lock()

    async def _noop():
        return None

    runner.submit(_noop())  # ties -> loop 0
    runner.submit(_noop())  # loop 0 busy -> loop 1
    assert len(runner._loops[0].futures) == 1
    assert len(runner._loops[1].futures) == 1

    # Completing loop 0's activity frees its slot; the next submit returns to loop 0.
    runner._loops[0].futures[0].set_result(None)
    runner.submit(_noop())
    assert len(runner._loops[0].futures) == 2
    assert len(runner._loops[1].futures) == 1
