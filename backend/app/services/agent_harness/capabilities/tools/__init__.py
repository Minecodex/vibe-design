from __future__ import annotations

from functools import lru_cache

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolRegistry

DEFAULT_MAX_RESULT_SIZE_CHARS = BaseTool.max_result_size_chars


@lru_cache(maxsize=1)
def _tool_max_result_size_map() -> dict[str, int]:
    registry = create_harness_registry()
    mapping: dict[str, int] = {}
    for tool in registry.get_tools_for_skill(None):
        mapping[tool.name] = int(getattr(tool, "max_result_size_chars", DEFAULT_MAX_RESULT_SIZE_CHARS))
    return mapping


def tool_max_result_size_chars(tool_name: str | None) -> int:
    """Return the verbatim model-output budget (chars) for a tool, by name or alias."""
    name = str(tool_name or "")
    mapping = _tool_max_result_size_map()
    canonical = ToolRegistry._normalise_name(name)  # noqa: SLF001 - alias resolution is registry-owned
    return mapping.get(name) or mapping.get(canonical) or DEFAULT_MAX_RESULT_SIZE_CHARS


def create_harness_registry(*, web_search_enabled: bool = True) -> ToolRegistry:
    from app.services.agent_harness.authoring.preflight import HarnessPreflightHook
    from app.services.agent_harness.capabilities.tools.agent import AgentTool
    from app.services.agent_harness.capabilities.tools.analyze_image import AnalyzeImageTool
    from app.services.agent_harness.capabilities.tools.ask_user import AskUserTool
    from app.services.agent_harness.capabilities.tools.capture_artifact_evidence import CaptureArtifactEvidenceTool
    from app.services.agent_harness.capabilities.tools.edit_file import EditFileTool
    from app.services.agent_harness.capabilities.tools.ecommerce_product import PrepareEcommerceGenerationTool
    from app.services.agent_harness.capabilities.tools.exec_command import ExecCommandTool
    from app.services.agent_harness.capabilities.tools.fetch_webpage import FetchWebpageTool
    from app.services.agent_harness.capabilities.tools.generate_image import GenerateImageTool
    from app.services.agent_harness.capabilities.tools.generate_video import GenerateVideoTool
    from app.services.agent_harness.capabilities.tools.glob_files import GlobFilesTool
    from app.services.agent_harness.capabilities.tools.grep_files import GrepFilesTool
    from app.services.agent_harness.capabilities.tools.list_files import ListFilesTool
    from app.services.agent_harness.capabilities.tools.publish_output import PublishOutputTool
    from app.services.agent_harness.capabilities.tools.register_artifact import RegisterArtifactTool
    from app.services.agent_harness.capabilities.tools.read_file import ReadFileTool
    from app.services.agent_harness.capabilities.tools.search_harness_history import (
        SearchHarnessHistoryTool,
    )
    from app.services.agent_harness.capabilities.tools.plan_lifecycle import (
        RequestPlanApprovalTool,
        UpdateExecutionProgressTool,
        UpdatePlanningDraftTool,
    )
    from app.services.agent_harness.capabilities.tools.web_search import WebSearchTool
    from app.services.agent_harness.capabilities.tools.workspace_map import WorkspaceMapTool
    from app.services.agent_harness.capabilities.tools.write_file import WriteFileTool

    from ._internal.file_version_guard import FileVersionGuardHook

    ToolRegistry._ALIASES.update(
        {
            "Bash": "exec_command",
            "bash": "exec_command",
            "EditFile": "edit_file",
            "edit_file": "edit_file",
            "file_edit": "edit_file",
            "Glob": "glob_files",
            "GlobTool": "glob_files",
            "glob": "glob_files",
            "Grep": "grep_files",
            "GrepTool": "grep_files",
            "grep": "grep_files",
            "ListFiles": "list_files",
            "Task": "Agent",
            "agent": "Agent",
        }
    )
    registry = ToolRegistry()
    registry.add_hook(HarnessPreflightHook())
    registry.add_hook(FileVersionGuardHook())
    registry.register(AskUserTool(), base=True)
    registry.register(WorkspaceMapTool(), base=True)
    registry.register(RegisterArtifactTool(), base=True)

    registry.register(AnalyzeImageTool())
    registry.register(GenerateImageTool())
    registry.register(GenerateVideoTool())
    registry.register(PrepareEcommerceGenerationTool(), skill_surfaceable=True)
    registry.register(WebSearchTool(), hidden=not web_search_enabled)
    registry.register(FetchWebpageTool())
    registry.register(AgentTool())
    registry.register(CaptureArtifactEvidenceTool(), hidden=True)
    registry.register(SearchHarnessHistoryTool(), base=True)

    registry.register(EditFileTool())
    registry.register(ExecCommandTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListFilesTool())
    registry.register(GlobFilesTool())
    registry.register(GrepFilesTool())
    registry.register(PublishOutputTool())
    registry.register(UpdatePlanningDraftTool())
    registry.register(RequestPlanApprovalTool())
    registry.register(UpdateExecutionProgressTool())
    return registry
