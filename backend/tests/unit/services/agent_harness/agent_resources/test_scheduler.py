from __future__ import annotations

import asyncio
import threading

import pytest

from app.services.agent_harness.agent_resources.labels import RESOURCE_LLM, resource_for_tool
from app.services.agent_harness.agent_resources.scheduler import AgentResourceScheduler
from app.services.agent_harness.workflow.activity_runner import WorkflowActivityRunner


@pytest.mark.asyncio
async def test_scheduler_waits_for_saturated_resource_slot():
    events: list[str] = []
    scheduler = AgentResourceScheduler({"llm": 1})

    async def contender() -> None:
        async with scheduler.acquire("llm"):
            events.append("contender-acquired")

    async with scheduler.acquire("llm"):
        events.append("first-acquired")
        task = asyncio.create_task(contender())
        try:
            await asyncio.sleep(0)
            assert events == ["first-acquired"]
        finally:
            pass
    await asyncio.wait_for(task, timeout=1)

    assert events == ["first-acquired", "contender-acquired"]


@pytest.mark.asyncio
async def test_scheduler_releases_waiter_running_on_another_activity_loop():
    scheduler = AgentResourceScheduler({"gpu": 1})
    runner = WorkflowActivityRunner(workers=2)
    holder_acquired = threading.Event()
    release_holder = threading.Event()
    waiter_started = threading.Event()

    async def holder() -> None:
        async with scheduler.acquire("gpu", tool_name="analyze_image"):
            holder_acquired.set()
            await asyncio.to_thread(release_holder.wait)

    async def waiter() -> str:
        waiter_started.set()
        async with scheduler.acquire("gpu", tool_name="analyze_image"):
            return "waiter-acquired"

    holder_future = runner.submit(holder())
    assert await asyncio.to_thread(holder_acquired.wait, 1)

    waiter_future = runner.submit(waiter())
    assert await asyncio.to_thread(waiter_started.wait, 1)
    assert not waiter_future.done()

    release_holder.set()
    await asyncio.wait_for(asyncio.wrap_future(holder_future), timeout=1)

    assert await asyncio.wait_for(
        asyncio.wrap_future(waiter_future),
        timeout=1,
    ) == "waiter-acquired"


def test_media_model_tools_use_model_call_resource():
    assert resource_for_tool("analyze_image") == RESOURCE_LLM
    assert resource_for_tool("generate_image") == RESOURCE_LLM
    assert resource_for_tool("generate_video") == RESOURCE_LLM
