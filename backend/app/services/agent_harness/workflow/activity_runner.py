from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from concurrent.futures import Future
from typing import TypeVar

from app.core.config import settings

T = TypeVar("T")


class _WorkflowActivityLoop:
    """Owns one event loop used for blocking legacy workflow activities."""

    def __init__(self, *, index: int) -> None:
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"harness-workflow-activity-{index}",
            daemon=True,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread.start()
        self._ready.wait(timeout=10)
        if self._loop is None:
            raise RuntimeError("workflow activity loop did not start")

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    def submit(self, coro: Awaitable[T]) -> Future[T]:
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("workflow activity loop is not running")
        return asyncio.run_coroutine_threadsafe(coro, loop)


class WorkflowActivityRunner:
    """Runs blocking or legacy async activities away from the scheduler loop."""

    def __init__(self, *, workers: int | None = None) -> None:
        configured_workers = workers
        if configured_workers is None:
            configured_workers = int(getattr(settings, "HARNESS_BLOCKING_IO_WORKERS", 6) or 6)
        self.workers = max(int(configured_workers or 1), 1)
        self._loops = [_WorkflowActivityLoop(index=index + 1) for index in range(self.workers)]
        self._inflight = [0] * len(self._loops)
        self._lock = threading.Lock()

    def submit(self, coro: Awaitable[T]) -> Future[T]:
        # Dispatch to the loop with the fewest in-flight activities (ties → lowest
        # index) instead of round-robin, so a long synchronous activity occupying one
        # loop does not head-of-line block newly submitted work.
        with self._lock:
            index = min(range(len(self._loops)), key=lambda i: self._inflight[i])
            self._inflight[index] += 1
        future = self._loops[index].submit(coro)

        def _release(_future: Future[T], slot: int = index) -> None:
            with self._lock:
                self._inflight[slot] = max(self._inflight[slot] - 1, 0)

        future.add_done_callback(_release)
        return future


_RUNNER: WorkflowActivityRunner | None = None
_LOCK = threading.Lock()


def get_workflow_activity_runner() -> WorkflowActivityRunner:
    global _RUNNER
    if _RUNNER is None:
        with _LOCK:
            if _RUNNER is None:
                _RUNNER = WorkflowActivityRunner()
    return _RUNNER
