from __future__ import annotations

from typing import Any

PLANNING_VISIBLE_TOOLS = frozenset({
    "ask_user",
    "update_planning_draft",
    "request_plan_approval",
    "update_execution_progress",
    "workspace_map",
    "read_file",
    "list_files",
    "glob_files",
    "grep_files",
    "edit_file",
    "analyze_image",
    "fetch_webpage",
    "generate_image",
    "generate_video",
    "search_harness_history",
    "web_search",
})

PLAN_ARTIFACT_PATHS = frozenset()
PLAN_NON_READONLY_ALLOWED_TOOLS = frozenset({
    "generate_image",
    "generate_video",
})


def normalize_workspace_path(value: str | None) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    normalized = normalized.removeprefix("./").removeprefix("/")
    return normalized


def allows_plan_artifact_mutation(tool_name: str, args: dict[str, Any]) -> bool:
    if tool_name != "edit_file":
        return False

    target = normalize_workspace_path(str(args.get("file_path") or ""))
    if not target:
        return False
    return target in PLAN_ARTIFACT_PATHS


def allows_plan_non_read_only_tool(tool_name: str, args: dict[str, Any]) -> bool:
    if tool_name in PLAN_NON_READONLY_ALLOWED_TOOLS:
        return True
    return allows_plan_artifact_mutation(tool_name, args)
