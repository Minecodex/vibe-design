from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    split_workspace_location_path,
    workspace_path_for_base_tool,
    workspace_path_metadata,
)
from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.isolation.security.paths import normalize_tool_base
from app.services.agent_harness.runtime.context_hygiene import is_low_signal_dir_name

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

_CHILDREN_PER_DIR_LIMIT = 24
_RECURSIVE_DEPTH_LIMIT = 3
_INTERNAL_RUNTIME_ROOT = ".skill_runtime"


class ListFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field("work", description="Semantic list root: work, project, skill, references, published, or project:<relative-dir>.")
    path: str = Field(".", validation_alias=AliasChoices("path", "file_path"), serialization_alias="path")
    recursive: bool = Field(False)
    max_entries: int = Field(200, ge=1, le=1000)

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


class ListFilesTool(BaseTool):
    SKIP_DIRS = {".git", ".npm", "__pycache__", "node_modules"}

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories from the selected semantic base under CONVERSATION_DIR. "
            "Use it to discover what exists before reading or editing. "
            "To match files by name pattern use `glob_files`; to search file contents use `grep_files`."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return ListFilesInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, ListFilesInput)
        location, path = _list_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        root = decision.resolved_path
        if not decision.allowed:
            return decision.reason
        assert root is not None
        if not root.exists():
            return f"Path not found: {params.file_path}"
        return None

    async def execute(self, params: ListFilesInput, ctx: "HarnessContext") -> ToolResult:
        location, path = _list_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        assert decision.resolved_path is not None
        root = decision.resolved_path
        payload = await run_file_io(_build_listing_payload, self, params, ctx, location, path, root)
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=payload)


def _build_listing_payload(
    tool: ListFilesTool,
    params: ListFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    root: Path,
) -> dict:
    if root.is_file():
        return {
            "entries": [_entry(ctx, root, location=location)],
            "truncated": False,
            **_reference_metadata(location, path),
        }
    entries: list[dict] = []
    omitted: list[dict[str, object]] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(entries) < params.max_entries:
        current, depth = stack.pop()
        children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        visible_children = [child for child in children if not _should_hide_path(ctx, child, location=location)]
        if len(visible_children) > _CHILDREN_PER_DIR_LIMIT:
            omitted.append(
                {
                    "path": _relative_from_root(root, current),
                    "reason": "child_limit",
                    "omitted_count": len(visible_children) - _CHILDREN_PER_DIR_LIMIT,
                }
            )
            visible_children = visible_children[:_CHILDREN_PER_DIR_LIMIT]
        for child in visible_children:
            if len(entries) >= params.max_entries:
                break
            entries.append(_entry(ctx, child, location=location))
            if not params.recursive or not child.is_dir():
                continue
            if depth >= _RECURSIVE_DEPTH_LIMIT:
                omitted.append(
                    {
                        "path": _relative_from_root(root, child),
                        "reason": "depth_limit",
                    }
                )
                continue
            if child.name in tool.SKIP_DIRS or is_low_signal_dir_name(child.name):
                omitted.append(
                    {
                        "path": _relative_from_root(root, child),
                        "reason": "low_signal_dir",
                    }
                )
                continue
            stack.append((child, depth + 1))
    return {
        "entries": entries,
        "truncated": len(entries) >= params.max_entries,
        "entry_count": len(entries),
        "dir_count": sum(1 for entry in entries if entry.get("type") == "dir"),
        "file_count": sum(1 for entry in entries if entry.get("type") == "file"),
        "location": location,
        "root": params.file_path,
        "recursive": params.recursive,
        "omitted": omitted[:20],
        "top_paths": [entry.get("path") for entry in entries[:12] if isinstance(entry, dict)],
        **_reference_metadata(location, path),
    }


def _entry(ctx: "HarnessContext", path: Path, *, location: str) -> dict:
    stat = path.lstat()
    return {
        **workspace_path_metadata(ctx, path, location=location),
        "type": "dir" if path.is_dir() else "file",
        "size": stat.st_size,
    }


def _reference_metadata(location: str, file_path: str) -> dict[str, object]:
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    if location == "skill":
        return {"reference_only": True, "reference_role": "skill_protocol_input"}
    if location == "references" or normalized.startswith("references/"):
        return {"reference_only": True, "reference_role": "conversation_reference"}
    return {}


def _list_location_path(params: ListFilesInput, ctx: "HarnessContext") -> tuple[str, str]:
    return split_workspace_location_path(
        workspace_path_for_base_tool(params.base, params.file_path, ctx, default_base="work")
    )


def _should_hide_path(ctx: "HarnessContext", path: Path, *, location: str) -> bool:
    if location != "project":
        return False
    try:
        rel = path.resolve().relative_to(ctx.project_dir.resolve()).as_posix()
    except ValueError:
        return False
    return rel == _INTERNAL_RUNTIME_ROOT or rel.startswith(f"{_INTERNAL_RUNTIME_ROOT}/")


def _relative_from_root(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return rel or "."
