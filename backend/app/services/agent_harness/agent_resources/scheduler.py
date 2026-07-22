from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from weakref import WeakKeyDictionary
from contextlib import asynccontextmanager

from .budgets import resource_budgets
from .labels import RESOURCE_TYPES

_TASK_RESOURCE_COUNTS: WeakKeyDictionary[asyncio.Task, dict[str, int]] = WeakKeyDictionary()
_TASK_RESOURCE_COUNTS_LOCK = threading.Lock()


@dataclass
class _ResourceWaiter:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]
    granted: bool = False
    released: bool = False


class _LoopNeutralLimiter:
    """A small async limiter that can be acquired and released from different loops."""

    def __init__(self, limit: int) -> None:
        self._limit = max(int(limit or 1), 1)
        self._available = self._limit
        self._waiters: deque[_ResourceWaiter] = deque()
        self._lock = threading.Lock()

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        waiter: _ResourceWaiter | None = None
        with self._lock:
            if self._available > 0 and not self._waiters:
                self._available -= 1
                return
            future: asyncio.Future[None] = loop.create_future()
            waiter = _ResourceWaiter(loop=loop, future=future)
            self._waiters.append(waiter)

        try:
            await waiter.future
        except BaseException:
            should_release = False
            with self._lock:
                if waiter.granted and not waiter.released:
                    waiter.released = True
                    should_release = True
                else:
                    try:
                        self._waiters.remove(waiter)
                    except ValueError:
                        pass
            if should_release:
                self.release()
            raise

    def release(self) -> None:
        waiter_to_resume: _ResourceWaiter | None = None
        with self._lock:
            if self._available < self._limit:
                self._available += 1
            while self._waiters and self._available > 0:
                waiter = self._waiters.popleft()
                if waiter.released:
                    continue
                waiter.granted = True
                self._available -= 1
                waiter_to_resume = waiter
                break

        if waiter_to_resume is None:
            return
        try:
            waiter_to_resume.loop.call_soon_threadsafe(self._complete_waiter, waiter_to_resume)
        except RuntimeError:
            self._release_granted_waiter(waiter_to_resume)

    def _complete_waiter(self, waiter: _ResourceWaiter) -> None:
        if waiter.future.done():
            self._release_granted_waiter(waiter)
            return
        waiter.future.set_result(None)

    def _release_granted_waiter(self, waiter: _ResourceWaiter) -> None:
        should_release = False
        with self._lock:
            if waiter.granted and not waiter.released:
                waiter.released = True
                should_release = True
        if should_release:
            self.release()


class AgentResourceScheduler:
    def __init__(self, budgets: dict[str, int] | None = None) -> None:
        resolved = budgets or resource_budgets()
        self._limiters = {
            resource_type: _LoopNeutralLimiter(max(int(limit or 1), 1))
            for resource_type, limit in resolved.items()
            if resource_type in RESOURCE_TYPES
        }

    @asynccontextmanager
    async def acquire(
        self,
        resource_type: str,
        *,
        tool_name: str | None = None,
        owner_domain: str | None = None,
    ):
        task = asyncio.current_task()
        if _task_resource_count(task, resource_type) > 0:
            yield
            return
        limiter = self._limiters.get(resource_type)
        if limiter is None:
            yield
            return
        await limiter.acquire()
        try:
            _increment_task_resource_count(task, resource_type)
            yield
        finally:
            _decrement_task_resource_count(task, resource_type)
            limiter.release()


def _task_resource_count(task: asyncio.Task | None, resource_type: str) -> int:
    if task is None:
        return 0
    with _TASK_RESOURCE_COUNTS_LOCK:
        task_counts = _TASK_RESOURCE_COUNTS.get(task)
        if task_counts is None:
            return 0
        return int(task_counts.get(resource_type, 0) or 0)


def _increment_task_resource_count(task: asyncio.Task | None, resource_type: str) -> None:
    if task is None:
        return
    with _TASK_RESOURCE_COUNTS_LOCK:
        task_counts = _TASK_RESOURCE_COUNTS.setdefault(task, {})
        task_counts[resource_type] = task_counts.get(resource_type, 0) + 1


def _decrement_task_resource_count(task: asyncio.Task | None, resource_type: str) -> None:
    if task is None:
        return
    with _TASK_RESOURCE_COUNTS_LOCK:
        task_counts = _TASK_RESOURCE_COUNTS.get(task)
        if task_counts is None:
            return
        remaining = task_counts.get(resource_type, 1) - 1
        if remaining > 0:
            task_counts[resource_type] = remaining
        else:
            task_counts.pop(resource_type, None)


_SCHEDULER: AgentResourceScheduler | None = None


def get_agent_resource_scheduler() -> AgentResourceScheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = AgentResourceScheduler()
    return _SCHEDULER
