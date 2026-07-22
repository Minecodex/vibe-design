from __future__ import annotations

import asyncio

from .labels import RESOURCE_SUBPROCESS
from .scheduler import get_agent_resource_scheduler


async def run_subprocess(command: list[str], *, timeout: float | None = None, cwd: str | None = None) -> tuple[int, bytes, bytes]:
    async with get_agent_resource_scheduler().acquire(RESOURCE_SUBPROCESS):
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise
        return int(proc.returncode or 0), stdout, stderr
