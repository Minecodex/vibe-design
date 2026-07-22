from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .labels import RESOURCE_OFFICE
from .scheduler import get_agent_resource_scheduler

T = TypeVar("T")


async def run_office_task(fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
    async with get_agent_resource_scheduler().acquire(RESOURCE_OFFICE):
        return await fn(*args, **kwargs)
