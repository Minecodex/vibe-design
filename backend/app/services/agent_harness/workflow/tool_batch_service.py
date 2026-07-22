from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry


@dataclass(frozen=True)
class ToolSegment:
    start_index: int
    end_index: int
    is_concurrent: bool
    tool_calls: list[dict[str, Any]]


def plan_next_segment(
    *,
    registry: ToolRegistry,
    tool_calls: list[dict[str, Any]],
    start_index: int,
) -> ToolSegment:
    calls = [dict(call or {}) for call in tool_calls]
    if not calls:
        return ToolSegment(start_index=0, end_index=0, is_concurrent=False, tool_calls=[])
    start = max(min(int(start_index or 0), len(calls)), 0)
    first = registry.classify_tool_call(calls[start], start)
    if not first.is_concurrency_safe:
        return ToolSegment(start_index=start, end_index=start + 1, is_concurrent=False, tool_calls=[calls[start]])

    end = start + 1
    while end < len(calls):
        classification = registry.classify_tool_call(calls[end], end)
        if not classification.is_concurrency_safe:
            break
        end += 1
    return ToolSegment(start_index=start, end_index=end, is_concurrent=True, tool_calls=calls[start:end])


async def execute_segment(
    *,
    segment: ToolSegment,
    execute_one: Callable[[dict[str, Any], int], Awaitable[dict[str, Any]]],
    max_concurrency: int,
) -> list[dict[str, Any]]:
    if not segment.tool_calls:
        return []
    if not segment.is_concurrent:
        return [await execute_one(dict(segment.tool_calls[0]), segment.start_index)]

    semaphore = asyncio.Semaphore(max(int(max_concurrency or 1), 1))

    async def _run(call: dict[str, Any], offset: int) -> dict[str, Any]:
        async with semaphore:
            return await execute_one(dict(call), segment.start_index + offset)

    results = await asyncio.gather(
        *[_run(call, offset) for offset, call in enumerate(segment.tool_calls)],
        return_exceptions=True,
    )
    exceptions = [result for result in results if isinstance(result, BaseException)]
    if exceptions:
        raise exceptions[0]
    return sorted((dict(result) for result in results), key=lambda item: int(item.get("tool_index") or 0))
