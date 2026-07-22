from __future__ import annotations

from app.services.agent_harness.runtime import context_projection_wakeup


async def wait_agent_context_wakeup(*, timeout_seconds: float) -> bool:
    result = await context_projection_wakeup.wait_context_projection_wakeup(
        timeout_seconds=max(float(timeout_seconds), 0.0),
    )
    return bool(result.get("woken"))


def wake_agent_context_worker() -> None:
    context_projection_wakeup.wake_context_projection_sync()
