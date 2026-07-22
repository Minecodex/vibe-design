from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from .labels import RESOURCE_FILE_IO
from .scheduler import get_agent_resource_scheduler

T = TypeVar("T")


async def run_file_io(fn: Callable[..., T], *args, **kwargs) -> T:
    async with get_agent_resource_scheduler().acquire(RESOURCE_FILE_IO):
        return await asyncio.to_thread(fn, *args, **kwargs)
