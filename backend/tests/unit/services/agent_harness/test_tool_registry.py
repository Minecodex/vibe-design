from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolRegistry, ToolResult
from app.services.agent_harness.capabilities.tools import create_harness_registry

REMOVED_ECOMMERCE_ANALYSIS_TOOL = "_".join(["analyze", "ecommerce", "realshots"])


class _DummyInput(BaseModel):
    pass


class _ValueInput(BaseModel):
    value: str


class _DummyTool(BaseTool):
    def __init__(self, tool_name: str, input_model: type[BaseModel] = _DummyInput) -> None:
        self._tool_name = tool_name
        self._input_model = input_model

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        return f"Tool {self._tool_name}"

    @property
    def input_model(self) -> type[BaseModel]:
        return self._input_model

    async def execute(self, params: BaseModel, ctx) -> ToolResult:
        del ctx
        return ToolResult(output=getattr(params, "value", self._tool_name))


def test_get_tools_for_skill_without_explicit_tools_returns_all_registered_tools():
    registry = ToolRegistry()
    registry.register(_DummyTool("read_file"), base=True)
    registry.register(_DummyTool("list_files"))
    registry.register(_DummyTool("edit_file"))

    tool_names = [tool.name for tool in registry.get_tools_for_skill([])]

    assert tool_names == ["edit_file", "list_files", "read_file"]


def test_get_tools_for_skill_with_explicit_tools_keeps_whitelist_behavior():
    registry = ToolRegistry()
    registry.register(_DummyTool("read_file"), base=True)
    registry.register(_DummyTool("list_files"))
    registry.register(_DummyTool("edit_file"))

    tool_names = [tool.name for tool in registry.get_tools_for_skill(["ListFiles"])]

    assert tool_names == ["list_files", "read_file"]


def test_ecommerce_tools_are_only_surfaced_by_explicit_skill_tools():
    registry = create_harness_registry()

    generic_tool_names = {tool.name for tool in registry.get_tools_for_skill(None)}
    ecommerce_tool_names = {
        "prepare_ecommerce_generation",
    }

    assert ecommerce_tool_names.isdisjoint(generic_tool_names)
    assert REMOVED_ECOMMERCE_ANALYSIS_TOOL not in generic_tool_names

    product_tool_names = {
        tool.name
        for tool in registry.get_tools_for_skill(
            [
                "prepare_ecommerce_generation",
                "generate_image",
                "analyze_image",
            ]
        )
    }

    assert ecommerce_tool_names <= product_tool_names
    assert REMOVED_ECOMMERCE_ANALYSIS_TOOL not in product_tool_names


@pytest.mark.asyncio
async def test_registry_expands_raw_json_arguments_before_validation():
    registry = ToolRegistry()
    registry.register(_DummyTool("value_tool", _ValueInput))

    result = await registry.execute("value_tool", {"raw": json.dumps({"value": "ok"})}, ctx=None)

    assert result.is_error is False
    assert result.output == "ok"


@pytest.mark.asyncio
async def test_registry_reports_invalid_raw_json_arguments():
    registry = ToolRegistry()
    registry.register(_DummyTool("value_tool", _ValueInput))

    result = await registry.execute("value_tool", {"raw": '{"value":'}, ctx=None)

    assert result.is_error is True
    assert "Invalid parameters" in result.output
    # Incomplete/truncated raw JSON now yields actionable recovery guidance.
    assert "not valid JSON" in result.output
    assert "edit_file" in result.output
