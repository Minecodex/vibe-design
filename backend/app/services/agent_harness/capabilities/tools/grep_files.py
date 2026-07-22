from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    split_workspace_location_path,
    workspace_path_for_base_tool,
)
from app.services.agent_harness.capabilities.tools._internal.search_ops import (
    VCS_DIRECTORIES_TO_EXCLUDE,
    RipgrepExecutionError,
    RipgrepUnavailableError,
    apply_head_limit,
    is_hidden_project_internal_path,
    is_supported_ripgrep_type,
    normalize_rg_output_path,
    project_internal_globs,
    run_ripgrep,
    semantic_output_path,
    split_rg_glob_patterns,
)
from app.services.agent_harness.isolation.security.paths import normalize_tool_base
from app.services.agent_harness.isolation.security.service import get_security_service

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

GrepOutputMode = Literal["content", "files_with_matches", "count"]


class GrepFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field(
        "work",
        description="Semantic search root: work, project, skill, references, published, or project:<relative-dir>.",
    )
    path: str = Field(
        ".",
        validation_alias=AliasChoices("path", "file_path"),
        serialization_alias="path",
        description="File or directory to search within the selected base.",
    )
    pattern: str = Field(..., min_length=1, description="Regular expression pattern to search for.")
    glob: str | None = Field(
        None,
        description='Glob pattern to filter files, such as "*.js" or "*.{ts,tsx}".',
    )
    output_mode: GrepOutputMode = Field(
        "files_with_matches",
        description='Output mode: "content", "files_with_matches", or "count".',
    )
    before_context: int | None = Field(
        None,
        ge=0,
        validation_alias=AliasChoices("-B", "before_context"),
        description="Number of lines to show before each match in content mode.",
    )
    after_context: int | None = Field(
        None,
        ge=0,
        validation_alias=AliasChoices("-A", "after_context"),
        description="Number of lines to show after each match in content mode.",
    )
    context: int | None = Field(
        None,
        ge=0,
        validation_alias=AliasChoices("-C", "context"),
        description="Number of lines to show before and after each match in content mode.",
    )
    show_line_numbers: bool = Field(
        True,
        validation_alias=AliasChoices("-n", "show_line_numbers"),
        description="Show line numbers in content mode.",
    )
    case_insensitive: bool = Field(
        False,
        validation_alias=AliasChoices("-i", "case_insensitive"),
        description="Perform case-insensitive search.",
    )
    file_type: str | None = Field(
        None,
        description=(
            "Optional ripgrep file type filter, such as js, ts, py, rust, go, java, json, md, html, or css. "
            "This filters files by language or extension; do not use it for regex or literal matching modes."
        ),
    )
    head_limit: int | None = Field(
        None,
        ge=0,
        description="Limit output to first N lines or entries. Defaults to 250; pass 0 for unlimited.",
    )
    offset: int = Field(
        0,
        ge=0,
        description="Skip first N lines or entries before applying head_limit.",
    )
    multiline: bool = Field(
        False,
        description="Enable multiline mode where . matches newlines and patterns can span lines.",
    )

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


class GrepFilesTool(BaseTool):
    @property
    def name(self) -> str:
        return "grep_files"

    @property
    def description(self) -> str:
        return (
            "Search file contents with ripgrep under the selected semantic base. "
            "Always use this for content search — do not run `grep`/`rg` via `exec_command`. "
            "Supports full regex (e.g. `log.*Error`), filtering by glob or file type, and output modes: "
            '"content" (matching lines), "files_with_matches" (paths, default), "count". '
            "Escape literal braces; use multiline mode for cross-line patterns. Scoped by harness base/path security."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return GrepFilesInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, GrepFilesInput)
        location, path = _grep_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        root = decision.resolved_path
        if not decision.allowed:
            return decision.reason
        assert root is not None
        if is_hidden_project_internal_path(ctx, root, location=location):
            return f"Path does not exist: {params.file_path}"
        if not root.exists():
            return f"Path does not exist: {params.file_path}"
        if not is_supported_ripgrep_type(params.file_type):
            return _unsupported_file_type_message(params.file_type)
        return None

    async def execute(self, params: GrepFilesInput, ctx: "HarnessContext") -> ToolResult:
        location, path = _grep_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        assert decision.resolved_path is not None
        if not is_supported_ripgrep_type(params.file_type):
            payload = _error_payload(
                params,
                location,
                path,
                _unsupported_file_type_message(params.file_type),
                failure_kind="search_failed",
            )
            return ToolResult(output=json.dumps(payload, ensure_ascii=False), is_error=True, metadata=payload)
        payload = await run_file_io(
            _build_grep_payload,
            params,
            ctx,
            location,
            path,
            decision.resolved_path,
        )
        is_error = bool(payload.get("failure_kind"))
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), is_error=is_error, metadata=payload)


def _build_grep_payload(
    params: GrepFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    root: Path,
) -> dict[str, object]:
    cwd, target = _search_invocation_root(root)
    args = ["--hidden"]
    for directory in VCS_DIRECTORIES_TO_EXCLUDE:
        args.extend(["--glob", f"!{directory}"])
    for exclusion in project_internal_globs(location):
        args.extend(["--glob", exclusion])
    args.extend(["--max-columns", "500"])
    if root.is_file() and params.output_mode in {"content", "count"}:
        args.append("--with-filename")
    if params.multiline:
        args.extend(["-U", "--multiline-dotall"])
    if params.case_insensitive:
        args.append("-i")
    if params.output_mode == "files_with_matches":
        args.append("-l")
    elif params.output_mode == "count":
        args.append("-c")
    if params.show_line_numbers and params.output_mode == "content":
        args.append("-n")
    if params.output_mode == "content":
        if params.context is not None:
            args.extend(["-C", str(params.context)])
        else:
            if params.before_context is not None:
                args.extend(["-B", str(params.before_context)])
            if params.after_context is not None:
                args.extend(["-A", str(params.after_context)])
    if params.pattern.startswith("-"):
        args.extend(["-e", params.pattern])
    else:
        args.append(params.pattern)
    if params.file_type:
        args.extend(["--type", params.file_type])
    for glob_pattern in split_rg_glob_patterns(params.glob):
        args.extend(["--glob", glob_pattern])

    try:
        result = run_ripgrep(args, target=target, cwd=cwd)
    except RipgrepUnavailableError as exc:
        return _error_payload(params, location, path, str(exc), failure_kind="search_backend_unavailable")
    except RipgrepExecutionError as exc:
        return _error_payload(params, location, path, str(exc), failure_kind="search_failed")

    if params.output_mode == "content":
        payload = _content_payload(params, ctx, location, path, cwd, result.lines)
    elif params.output_mode == "count":
        payload = _count_payload(params, ctx, location, path, cwd, result.lines)
    else:
        payload = _files_with_matches_payload(params, ctx, location, path, cwd, result.lines)
    payload["search_backend"] = result.backend
    return payload


def _content_payload(
    params: GrepFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    cwd: Path,
    lines: list[str],
) -> dict[str, object]:
    limited, applied_limit = apply_head_limit(lines, head_limit=params.head_limit, offset=params.offset)
    final_lines = [
        line
        for line in (_semantic_rg_content_line(ctx, line, location=location, cwd=cwd) for line in limited)
        if line
    ]
    filenames = _filenames_from_content_lines(final_lines)
    return {
        "mode": "content",
        "numFiles": len(filenames),
        "filenames": filenames,
        "content": "\n".join(final_lines),
        "numLines": len(final_lines),
        **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
        **({"appliedOffset": params.offset} if params.offset > 0 else {}),
        **_common_metadata(params, location, path),
    }


def _count_payload(
    params: GrepFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    cwd: Path,
    lines: list[str],
) -> dict[str, object]:
    limited, applied_limit = apply_head_limit(lines, head_limit=params.head_limit, offset=params.offset)
    final_lines: list[str] = []
    total_matches = 0
    file_count = 0
    for line in limited:
        parsed = _split_path_count(line)
        if parsed is None:
            continue
        raw_path, count = parsed
        resolved = normalize_rg_output_path(raw_path, cwd=cwd)
        if is_hidden_project_internal_path(ctx, resolved, location=location):
            continue
        semantic_path = semantic_output_path(ctx, resolved, location=location)
        final_lines.append(f"{semantic_path}:{count}")
        total_matches += count
        file_count += 1
    return {
        "mode": "count",
        "numFiles": file_count,
        "filenames": [],
        "content": "\n".join(final_lines),
        "numMatches": total_matches,
        **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
        **({"appliedOffset": params.offset} if params.offset > 0 else {}),
        **_common_metadata(params, location, path),
    }


def _files_with_matches_payload(
    params: GrepFilesInput,
    ctx: "HarnessContext",
    location: str,
    path: str,
    cwd: Path,
    lines: list[str],
) -> dict[str, object]:
    resolved_files = []
    for raw in lines:
        resolved = normalize_rg_output_path(raw, cwd=cwd)
        if is_hidden_project_internal_path(ctx, resolved, location=location):
            continue
        mtime = resolved.stat().st_mtime if resolved.exists() else 0
        resolved_files.append((resolved, mtime))
    resolved_files.sort(key=lambda item: (-item[1], item[0].as_posix()))
    sorted_paths = [path_item for path_item, _ in resolved_files]
    limited, applied_limit = apply_head_limit(sorted_paths, head_limit=params.head_limit, offset=params.offset)
    filenames = [semantic_output_path(ctx, resolved, location=location) for resolved in limited]
    return {
        "mode": "files_with_matches",
        "numFiles": len(filenames),
        "filenames": filenames,
        **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
        **({"appliedOffset": params.offset} if params.offset > 0 else {}),
        **_common_metadata(params, location, path),
    }


def _semantic_rg_content_line(
    ctx: "HarnessContext",
    line: str,
    *,
    location: str,
    cwd: Path,
) -> str:
    if line == "--":
        return line
    parsed = _split_rg_content_line(line)
    if parsed is None:
        return line
    raw_path, rest = parsed
    resolved = normalize_rg_output_path(raw_path, cwd=cwd)
    if is_hidden_project_internal_path(ctx, resolved, location=location):
        return ""
    return f"{semantic_output_path(ctx, resolved, location=location)}{rest}"


def _split_rg_content_line(line: str) -> tuple[str, str] | None:
    numbered_match = re.match(r"^(?P<path>.*?)(?P<sep>[:-])(?P<line>\d+)(?P=sep)(?P<rest>.*)$", line)
    if numbered_match:
        path = str(numbered_match.group("path"))
        sep = str(numbered_match.group("sep"))
        line_number = str(numbered_match.group("line"))
        rest = str(numbered_match.group("rest"))
        return path, f"{sep}{line_number}{sep}{rest}"
    colon_index = line.find(":")
    if colon_index <= 0:
        return None
    return line[:colon_index], line[colon_index:]


def _filenames_from_content_lines(lines: list[str]) -> list[str]:
    filenames: list[str] = []
    seen: set[str] = set()
    for line in lines:
        parsed = _split_rg_content_line(line)
        if parsed is None:
            continue
        filename, _rest = parsed
        if filename in seen:
            continue
        seen.add(filename)
        filenames.append(filename)
    return filenames


def _split_path_count(line: str) -> tuple[str, int] | None:
    colon_index = line.rfind(":")
    if colon_index <= 0:
        return None
    count_text = line[colon_index + 1 :].strip()
    try:
        count = int(count_text)
    except ValueError:
        return None
    return line[:colon_index], count


def _search_invocation_root(root: Path) -> tuple[Path, str]:
    if root.is_file():
        return root.parent.resolve(), root.name
    return root.resolve(), "."


def _error_payload(
    params: GrepFilesInput,
    location: str,
    path: str,
    message: str,
    *,
    failure_kind: str,
) -> dict[str, object]:
    return {
        "mode": params.output_mode,
        "numFiles": 0,
        "filenames": [],
        "content": "",
        "numLines": 0 if params.output_mode == "content" else None,
        "numMatches": 0 if params.output_mode == "count" else None,
        "failure_kind": failure_kind,
        "error": message,
        **_common_metadata(params, location, path),
    }


def _unsupported_file_type_message(file_type: str | None) -> str:
    return (
        f"Unsupported ripgrep file_type: {file_type}. "
        "Use a language/extension value such as js, ts, py, html, css, json, or md; "
        "omit file_type for regex or literal text searches."
    )


def _common_metadata(params: GrepFilesInput, location: str, path: str) -> dict[str, object]:
    return {
        "base": params.base,
        "root": params.file_path,
        "location": location,
        "pattern": params.pattern,
        "glob": params.glob,
        "file_type": params.file_type,
        **_reference_metadata(location, path),
    }


def _reference_metadata(location: str, file_path: str) -> dict[str, object]:
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    if location == "skill":
        return {"reference_only": True, "reference_role": "skill_protocol_input"}
    if location == "references" or normalized.startswith("references/"):
        return {"reference_only": True, "reference_role": "conversation_reference"}
    return {}


def _grep_location_path(params: GrepFilesInput, ctx: "HarnessContext") -> tuple[str, str]:
    return split_workspace_location_path(
        workspace_path_for_base_tool(params.base, params.file_path, ctx, default_base="work")
    )
