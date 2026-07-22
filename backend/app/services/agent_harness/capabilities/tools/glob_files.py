from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    split_workspace_location_path,
    workspace_path_for_base_tool,
)
from app.services.agent_harness.capabilities.tools._internal.search_ops import (
    RipgrepExecutionError,
    RipgrepUnavailableError,
    VCS_DIRECTORIES_TO_EXCLUDE,
    is_hidden_project_internal_path,
    normalize_rg_output_path,
    project_internal_globs,
    run_ripgrep,
    semantic_output_path,
)
from app.services.agent_harness.isolation.security.paths import normalize_tool_base
from app.services.agent_harness.isolation.security.service import get_security_service

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class GlobFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field(
        "work",
        description="Semantic search root: work, project, skill, references, published, or project:<relative-dir>.",
    )
    path: str = Field(
        ".",
        validation_alias=AliasChoices("path", "file_path"),
        serialization_alias="path",
        description="Directory to search within the selected base.",
    )
    pattern: str = Field(..., min_length=1, description="Glob pattern to match files against.")
    max_results: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum matching files to return. Defaults to the Claude Code Glob limit of 100.",
    )

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


class GlobFilesTool(BaseTool):
    @property
    def name(self) -> str:
        return "glob_files"

    @property
    def description(self) -> str:
        return (
            "Fast file pattern matching under the selected semantic base. "
            "Supports patterns like `**/*.js` or `src/**/*.ts` and returns matching paths sorted by modification time. "
            "Use it to find files by name; for content search use `grep_files`. "
            "Scoped by harness base/path security (no absolute paths or `..`)."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return GlobFilesInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, GlobFilesInput)
        location, path = _glob_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        root = decision.resolved_path
        if not decision.allowed:
            return decision.reason
        assert root is not None
        if is_hidden_project_internal_path(ctx, root, location=location):
            return f"Path not found: {params.file_path}"
        if not root.exists():
            return f"Directory does not exist: {params.file_path}"
        if not root.is_dir():
            return f"Path is not a directory: {params.file_path}"
        return None

    async def execute(self, params: GlobFilesInput, ctx: "HarnessContext") -> ToolResult:
        location, path = _glob_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        assert decision.resolved_path is not None
        payload = await run_file_io(
            _build_glob_payload,
            params,
            ctx,
            location,
            path,
            decision.resolved_path,
        )
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False),
            is_error=bool(payload.get("failure_kind")),
            metadata=payload,
        )


def _build_glob_payload(
    params: GlobFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    root: Path,
) -> dict[str, object]:
    args = [
        "--files",
        "--glob",
        params.pattern,
        "--sort=modified",
        "--no-ignore",
        "--hidden",
    ]
    for directory in VCS_DIRECTORIES_TO_EXCLUDE:
        args.extend(["--glob", f"!{directory}"])
    for exclusion in project_internal_globs(location):
        args.extend(["--glob", exclusion])
    try:
        result = run_ripgrep(args, target=".", cwd=root)
    except RipgrepUnavailableError as exc:
        return _error_payload(params, location, path, str(exc), failure_kind="search_backend_unavailable")
    except RipgrepExecutionError as exc:
        return _error_payload(params, location, path, str(exc), failure_kind="search_failed")

    resolved_files: list[Path] = []
    for raw in result.lines:
        resolved = normalize_rg_output_path(raw, cwd=root)
        if not resolved.is_file():
            continue
        if is_hidden_project_internal_path(ctx, resolved, location=location):
            continue
        resolved_files.append(resolved)
    truncated = len(resolved_files) > params.max_results
    limited = resolved_files[: params.max_results]
    filenames = [semantic_output_path(ctx, file_path, location=location) for file_path in limited]
    return {
        "durationMs": result.duration_ms,
        "duration_ms": result.duration_ms,
        "search_backend": result.backend,
        "numFiles": len(filenames),
        "num_files": len(filenames),
        "filenames": filenames,
        "truncated": truncated,
        "base": params.base,
        "root": params.file_path,
        "location": location,
        "pattern": params.pattern,
        **_reference_metadata(location, path),
    }


def _error_payload(
    params: GlobFilesInput,
    location: str,
    path: str,
    message: str,
    *,
    failure_kind: str,
) -> dict[str, object]:
    return {
        "durationMs": 0,
        "duration_ms": 0,
        "numFiles": 0,
        "num_files": 0,
        "filenames": [],
        "truncated": False,
        "base": params.base,
        "root": params.file_path,
        "location": location,
        "pattern": params.pattern,
        "failure_kind": failure_kind,
        "error": message,
        **_reference_metadata(location, path),
    }


def _reference_metadata(location: str, file_path: str) -> dict[str, object]:
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    if location == "skill":
        return {"reference_only": True, "reference_role": "skill_protocol_input"}
    if location == "references" or normalized.startswith("references/"):
        return {"reference_only": True, "reference_role": "conversation_reference"}
    return {}


def _glob_location_path(params: GlobFilesInput, ctx: "HarnessContext") -> tuple[str, str]:
    return split_workspace_location_path(
        workspace_path_for_base_tool(params.base, params.file_path, ctx, default_base="work")
    )
