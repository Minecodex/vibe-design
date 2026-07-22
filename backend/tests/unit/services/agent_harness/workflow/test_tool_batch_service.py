from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolRegistry, ToolResult
from app.services.agent_harness.workflow.tool_batch_service import execute_segment, plan_next_segment


class _Input(BaseModel):
    value: str = "ok"


class _RequiredInput(BaseModel):
    value: str


class _SafeTool(BaseTool):
    @property
    def name(self) -> str:
        return "safe_tool"

    @property
    def description(self) -> str:
        return "safe"

    @property
    def input_model(self) -> type[BaseModel]:
        return _Input

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    async def execute(self, params: BaseModel, ctx) -> ToolResult:
        return ToolResult(output="ok")


class _UnsafeTool(_SafeTool):
    @property
    def name(self) -> str:
        return "unsafe_tool"

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return False


class _WriteTool(_SafeTool):
    @property
    def name(self) -> str:
        return "write_tool"

    def is_read_only(self, params: BaseModel) -> bool:
        return False


class _RequiredTool(_SafeTool):
    @property
    def name(self) -> str:
        return "required_tool"

    @property
    def input_model(self) -> type[BaseModel]:
        return _RequiredInput


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_SafeTool())
    registry.register(_UnsafeTool())
    registry.register(_WriteTool())
    registry.register(_RequiredTool())
    return registry


def test_plan_next_segment_groups_consecutive_safe_tools():
    calls = [
        {"id": "call-1", "name": "safe_tool", "arguments": {"value": "a"}},
        {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
        {"id": "call-3", "name": "unsafe_tool", "arguments": {"value": "c"}},
    ]

    segment = plan_next_segment(registry=_registry(), tool_calls=calls, start_index=0)

    assert segment.start_index == 0
    assert segment.end_index == 2
    assert segment.is_concurrent is True
    assert [call["id"] for call in segment.tool_calls] == ["call-1", "call-2"]


def test_plan_next_segment_makes_unsafe_first_call_exclusive():
    calls = [
        {"id": "call-1", "name": "unsafe_tool", "arguments": {"value": "a"}},
        {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
    ]

    segment = plan_next_segment(registry=_registry(), tool_calls=calls, start_index=0)

    assert segment.start_index == 0
    assert segment.end_index == 1
    assert segment.is_concurrent is False
    assert [call["id"] for call in segment.tool_calls] == ["call-1"]


def test_plan_next_segment_treats_unknown_tool_as_exclusive():
    calls = [
        {"id": "call-1", "name": "missing_tool", "arguments": {"value": "a"}},
        {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
    ]

    segment = plan_next_segment(registry=_registry(), tool_calls=calls, start_index=0)

    assert segment.end_index == 1
    assert segment.is_concurrent is False


@pytest.mark.parametrize(
    "first_call",
    [
        {"id": "call-1", "name": "safe_tool", "arguments": None},
        {"id": "call-1", "name": "safe_tool", "arguments": ["not", "object"]},
        {"id": "call-1", "name": "safe_tool", "arguments": "not-json"},
        {"id": "call-1", "name": "safe_tool", "arguments": "[1, 2]"},
        {"id": "call-1", "name": "required_tool", "arguments": {}},
        {"id": "call-1", "name": "write_tool", "arguments": {"value": "a"}},
    ],
)
def test_plan_next_segment_fail_closes_bad_or_non_readonly_calls(first_call):
    calls = [
        first_call,
        {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
    ]

    segment = plan_next_segment(registry=_registry(), tool_calls=calls, start_index=0)

    assert segment.start_index == 0
    assert segment.end_index == 1
    assert segment.is_concurrent is False
    assert segment.tool_calls == [first_call]


@pytest.mark.asyncio
async def test_execute_segment_returns_outcomes_in_original_order_with_concurrency_limit():
    segment = plan_next_segment(
        registry=_registry(),
        tool_calls=[
            {"id": "call-1", "name": "safe_tool", "arguments": {"value": "a"}},
            {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
            {"id": "call-3", "name": "safe_tool", "arguments": {"value": "c"}},
        ],
        start_index=0,
    )
    active = 0
    max_active = 0
    completed: list[int] = []

    async def execute_one(_call: dict, index: int) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01 * (3 - index))
        active -= 1
        completed.append(index)
        return {"tool_index": index, "call_id": f"call-{index + 1}", "status": "completed"}

    outcomes = await execute_segment(segment=segment, execute_one=execute_one, max_concurrency=2)

    assert max_active == 2
    assert completed != [0, 1, 2]
    assert [outcome["tool_index"] for outcome in outcomes] == [0, 1, 2]


@pytest.mark.asyncio
async def test_execute_segment_keeps_running_siblings_when_one_tool_returns_business_error():
    segment = plan_next_segment(
        registry=_registry(),
        tool_calls=[
            {"id": "call-1", "name": "safe_tool", "arguments": {"value": "a"}},
            {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
        ],
        start_index=0,
    )
    executed: list[int] = []

    async def execute_one(_call: dict, index: int) -> dict:
        executed.append(index)
        if index == 0:
            return {"tool_index": index, "call_id": "call-1", "status": "failed", "is_error": True}
        return {"tool_index": index, "call_id": "call-2", "status": "completed", "is_error": False}

    outcomes = await execute_segment(segment=segment, execute_one=execute_one, max_concurrency=2)

    assert executed == [0, 1]
    assert [outcome["is_error"] for outcome in outcomes] == [True, False]


@pytest.mark.asyncio
async def test_execute_segment_waits_for_started_siblings_before_reraising_infrastructure_error():
    segment = plan_next_segment(
        registry=_registry(),
        tool_calls=[
            {"id": "call-1", "name": "safe_tool", "arguments": {"value": "a"}},
            {"id": "call-2", "name": "safe_tool", "arguments": {"value": "b"}},
        ],
        start_index=0,
    )
    completed: list[int] = []

    async def execute_one(_call: dict, index: int) -> dict:
        if index == 0:
            await asyncio.sleep(0.01)
            raise RuntimeError("network down")
        await asyncio.sleep(0.02)
        completed.append(index)
        return {"tool_index": index, "call_id": "call-2", "status": "completed"}

    with pytest.raises(RuntimeError, match="network down"):
        await execute_segment(segment=segment, execute_one=execute_one, max_concurrency=2)

    assert completed == [1]
