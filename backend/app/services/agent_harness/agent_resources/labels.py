from __future__ import annotations

RESOURCE_LLM = "llm"
RESOURCE_FILE_IO = "file_io"
RESOURCE_CPU_TOOL = "cpu_tool"
RESOURCE_SUBPROCESS = "subprocess"
RESOURCE_BROWSER = "browser"
RESOURCE_OFFICE = "office"
RESOURCE_GPU = "gpu"
RESOURCE_NETWORK = "network"

RESOURCE_TYPES = {
    RESOURCE_LLM,
    RESOURCE_FILE_IO,
    RESOURCE_CPU_TOOL,
    RESOURCE_SUBPROCESS,
    RESOURCE_BROWSER,
    RESOURCE_OFFICE,
    RESOURCE_GPU,
    RESOURCE_NETWORK,
}

TOOL_RESOURCE_LABELS = {
    "workspace_map": RESOURCE_FILE_IO,
    "list_files": RESOURCE_FILE_IO,
    "glob_files": RESOURCE_FILE_IO,
    "grep_files": RESOURCE_FILE_IO,
    "read_file": RESOURCE_FILE_IO,
    "write_file": RESOURCE_FILE_IO,
    "edit_file": RESOURCE_FILE_IO,
    "exec_command": RESOURCE_SUBPROCESS,
    "Bash": RESOURCE_SUBPROCESS,
    "bash": RESOURCE_SUBPROCESS,
    "Glob": RESOURCE_FILE_IO,
    "GlobTool": RESOURCE_FILE_IO,
    "glob": RESOURCE_FILE_IO,
    "Grep": RESOURCE_FILE_IO,
    "GrepTool": RESOURCE_FILE_IO,
    "grep": RESOURCE_FILE_IO,
    "web_search": RESOURCE_NETWORK,
    "fetch_webpage": RESOURCE_NETWORK,
    "capture_artifact_evidence": RESOURCE_BROWSER,
    "Agent": RESOURCE_CPU_TOOL,
    "search_harness_history": RESOURCE_CPU_TOOL,
    # Media model tools call external model providers; reuse the existing model-call limiter.
    "analyze_image": RESOURCE_LLM,
    "generate_image": RESOURCE_LLM,
    "generate_video": RESOURCE_LLM,
}


def resource_for_tool(tool_name: str) -> str:
    return TOOL_RESOURCE_LABELS.get(str(tool_name or ""), RESOURCE_CPU_TOOL)
