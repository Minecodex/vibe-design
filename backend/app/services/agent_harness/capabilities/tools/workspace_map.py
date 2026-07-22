from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.services.agent_harness.capabilities.skill_protocols.tool_guard import ProtocolToolGuard
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.isolation.security.paths import artifact_work_project_path

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class WorkspaceMapInput(BaseModel):
    pass


class WorkspaceMapTool(BaseTool):
    @property
    def name(self) -> str:
        return "workspace_map"

    @property
    def description(self) -> str:
        return "Return the CONVERSATION_DIR workspace map, default command cwd, and v2 path-form examples."

    @property
    def input_model(self) -> type[BaseModel]:
        return WorkspaceMapInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    async def execute(self, params: WorkspaceMapInput, ctx: "HarnessContext") -> ToolResult:
        work_root = artifact_work_project_path(ctx)
        default_cwd = work_root or "project"
        payload = {
            "root": "CONVERSATION_DIR",
            "default_command_cwd": default_cwd,
            "artifact_work_root": work_root,
            "path_semantics": (
                f'base="work" resolves to the current artifact work directory ({work_root}).'
                if work_root
                else 'base="work" resolves to CONVERSATION_DIR/project/.'
            ),
            "visible_roots": {
                "project": {"path": "CONVERSATION_DIR/project", "read": True, "write": True},
                "references": {"path": "CONVERSATION_DIR/references", "read": True, "write": False},
                "skill": {"path": "CONVERSATION_DIR/skill", "read": True, "write": False},
                "published": {"path": "CONVERSATION_DIR/published", "read": True, "write": False},
            },
            "path_forms": {
                "workspace_relative": f"{default_cwd}/report.py",
                "work_directory_relative": "report.py",
                "command_cwd_relative": "python report.py",
                "base_parameter": 'base="work" | "project" | "skill" | "references" | "published" | "project:<relative-dir>"',
            },
            "base_semantics": {
                "work": f"Current artifact work directory ({work_root})." if work_root else "Current writable project work root.",
                "project": "CONVERSATION_DIR/project/ root.",
                "project:<relative-dir>": "A subdirectory under project/ for inspecting or reusing another prepared directory; writes still must stay inside the active work directory.",
                "skill": "Read-only active skill root. For open-design, .od-skills/<template>/ maps here.",
                "references": "Read-only conversation reference material.",
                "published": "Read-only published outputs.",
            },
            "examples": {
                "write_deliverable_file": {"tool": "write_file", "base": "work", "path": "report.py"},
                "run_project_file": {"tool": "exec_command", "base": "work", "command": "python report.py"},
                "script_reads_upload": "$HARNESS_REFERENCE_INPUTS_DIR/upload_001/source.png",
                "list_other_prepared_directory": {"tool": "list_files", "base": "project:other-prepared", "path": ".", "recursive": False},
                "register_artifact": {"tool": "register_artifact", "entry": "report.html", "kind": "html"},
                "publish_registered_artifact": {"tool": "publish_output"},
            },
        }
        contract = ProtocolToolGuard(ctx).contract
        if contract is not None:
            payload["protocol_runtime"] = contract.to_payload()
            if contract.artifact_work_root:
                payload["current_artifact_work_directory"] = _project_path(contract.artifact_work_root)
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=payload)


def _project_path(value: str | None) -> str:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    if not normalized:
        return "project"
    if normalized == "project" or normalized.startswith("project/"):
        return normalized
    return f"project/{normalized}"
