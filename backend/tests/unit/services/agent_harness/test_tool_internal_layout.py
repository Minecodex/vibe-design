from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry
from app.services.agent_harness.capabilities.tools._internal.command_runner import build_env


def test_internal_tool_support_modules_live_under_internal_package():
    assert ToolRegistry is not None
    assert callable(build_env)
