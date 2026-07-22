from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.isolation.security.paths import MAX_TEXT_FILE_READ_BYTES, normalize_tool_base
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    split_workspace_location_path,
    workspace_path_for_base_tool,
    workspace_path_metadata,
)
from app.services.agent_harness.capabilities.tools._internal.harness_file_readers import read_harness_file_window
from app.services.agent_harness.agent_resources.file_io import run_file_io

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class ReadFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field("work", description="Semantic read root: work, project, skill, references, published, or project:<relative-dir>.")
    path: str = Field(..., validation_alias=AliasChoices("path", "file_path"), serialization_alias="path")
    offset: int | None = Field(None, ge=0, description="Zero-based line offset. Defaults to the beginning of the file.")
    limit: int | None = Field(None, ge=1, description="Maximum number of lines to return. Omit to read to EOF.")

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


class ReadFileTool(BaseTool):
    # File reads are already bounded by the offset/limit window; allow a large
    # verbatim budget so a deliberately-sized read is never re-truncated.
    max_result_size_chars: int = 200_000

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a text file from the selected semantic base under CONVERSATION_DIR. "
            "By default, and recommended, omit offset and limit to read the whole file — reading the "
            "entire file is preferred so you do not miss relevant content; do not pre-emptively cap reads. "
            "Only pass offset and limit when you already know the exact line range you need, or when a "
            "full read is rejected because the file is too large. "
            "If you already read a file earlier in this conversation and it hasn't changed, reuse that content instead of reading it again. "
            "When a full read is rejected for being too large, narrow it with offset and limit, or use grep_files to search."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return ReadFileInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, ReadFileInput)
        location, path = _read_location_path(params, ctx)
        resolved = get_security_service().check_read_path(ctx, location=location, path=path)
        path = resolved.resolved_path
        if not resolved.allowed:
            return resolved.reason
        assert path is not None
        if path.exists() and path.is_dir():
            return _directory_read_error(location, params.file_path)
        if not path.exists() or not path.is_file():
            return f"File not found: {params.file_path}"
        return None

    async def execute(self, params: ReadFileInput, ctx: "HarnessContext") -> ToolResult:
        location, path = _read_location_path(params, ctx)
        decision = get_security_service().check_read_path(ctx, location=location, path=path)
        assert decision.resolved_path is not None
        if decision.resolved_path.exists() and decision.resolved_path.is_dir():
            metadata_path = _metadata_file_path(location, path, decision.normalized_value)
            return ToolResult(
                output=_directory_read_error(location, path),
                is_error=True,
                metadata={
                    **workspace_path_metadata(
                        ctx,
                        decision.resolved_path,
                        location=location,
                        file_path=metadata_path,
                    ),
                    **_path_normalization_metadata(decision.metadata),
                    "failure_kind": "path_is_directory",
                    "suggested_next_tool": "list_files",
                    "suggested_action": f'Use list_files(path="{_display_path(location, path)}") to inspect directory contents.',
                },
            )
        metadata_path = _metadata_file_path(location, path, decision.normalized_value)
        normalization_metadata = _path_normalization_metadata(decision.metadata)
        offset = params.offset or 0
        repeated_read = ctx.has_read_file(decision.resolved_path)
        window_key = _read_window_key(ctx, decision.resolved_path, offset=offset, limit=params.limit)
        if repeated_read and _has_read_window(ctx, window_key):
            repeat_count = _bump_read_window_repeat_count(ctx, window_key)
            metadata = {
                **workspace_path_metadata(
                    ctx,
                    decision.resolved_path,
                    location=location,
                    file_path=metadata_path,
                ),
                **normalization_metadata,
                "offset": offset,
                "limit": params.limit,
                "repeated_read": True,
                "unchanged": True,
                "repeat_count": repeat_count,
                "content": "",
                **_reference_metadata(location, path),
            }
            output = (
                "File unchanged since last read. Reuse the previous content; change offset/limit to inspect another range."
            )
            return ToolResult(output=output, metadata=metadata)
        try:
            window = await run_file_io(
                read_harness_file_window,
                decision.resolved_path,
                offset=offset,
                limit=params.limit,
            )
        except ValueError as exc:
            return ToolResult(
                output=str(exc),
                is_error=True,
                metadata={
                    **workspace_path_metadata(
                        ctx,
                        decision.resolved_path,
                        location=location,
                        file_path=metadata_path,
                    ),
                    **normalization_metadata,
                    "failure_kind": "file_read_limit",
                    "max_read_size_bytes": MAX_TEXT_FILE_READ_BYTES,
                },
            )
        content = str(window["content"])
        output = _model_visible_read_output(content, window)
        if len(output) > self.max_result_size_chars:
            return ToolResult(
                output=(
                    f"read_file output window is too large ({len(output)} characters, max {self.max_result_size_chars}). "
                    "Retry with a smaller limit, use offset/limit to inspect a narrower range, or use grep_files to search for specific content."
                ),
                is_error=True,
                metadata={
                    **workspace_path_metadata(
                        ctx,
                        decision.resolved_path,
                        location=location,
                        file_path=metadata_path,
                    ),
                    **normalization_metadata,
                    "failure_kind": "file_read_output_too_large",
                    "offset": offset,
                    "limit": params.limit,
                    **window,
                    **_range_metadata(window),
                    **_reference_metadata(location, path),
                },
            )
        ctx.mark_file_read(decision.resolved_path)
        _mark_read_window(ctx, window_key)
        _reset_other_read_window_repeat_counts(ctx, window_key)
        return ToolResult(
            output=output,
            metadata={
                **workspace_path_metadata(
                    ctx,
                    decision.resolved_path,
                    location=location,
                    file_path=metadata_path,
                ),
                **normalization_metadata,
                "content": content,
                "offset": offset,
                "limit": params.limit,
                **window,
                "repeated_read": repeated_read,
                "unchanged": False,
                **_range_metadata(window),
                **_reference_metadata(location, path),
            },
        )


def _reference_metadata(location: str, file_path: str) -> dict[str, object]:
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    if location == "skill":
        return {"reference_only": True, "reference_role": "skill_protocol_input"}
    if location == "references" or normalized.startswith("references/"):
        return {"reference_only": True, "reference_role": "conversation_reference"}
    return {}


def _read_location_path(params: ReadFileInput, ctx: "HarnessContext") -> tuple[str, str]:
    return split_workspace_location_path(
        workspace_path_for_base_tool(params.base, params.file_path, ctx, default_base="work")
    )


def _directory_read_error(location: str, file_path: str) -> str:
    display_path = _display_path(location, file_path)
    return (
        f"Path is a directory, not a readable file: {display_path}. "
        f'Use list_files(path="{display_path}") to inspect directory contents.'
    )


def _display_path(location: str, file_path: str) -> str:
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    root = str(location or "").replace("\\", "/").strip().strip("/")
    if root and root not in {"root", "workspace"} and not normalized.startswith(f"{root}/") and normalized != root:
        return f"{root}/{normalized}" if normalized else root
    return normalized or root or "."


def _metadata_file_path(location: str, original_path: str, normalized_value: str | None) -> str:
    normalized = str(normalized_value or "").replace("\\", "/").strip().lstrip("/")
    root = str(location or "").replace("\\", "/").strip().strip("/")
    if root in {"root", "workspace", ""}:
        return normalized or original_path
    if normalized == root:
        return "."
    if normalized.startswith(f"{root}/"):
        return normalized[len(root) + 1 :]
    return original_path


def _path_normalization_metadata(decision_metadata: dict[str, object] | None) -> dict[str, object]:
    normalization = (decision_metadata or {}).get("path_normalization")
    if isinstance(normalization, dict) and normalization.get("correction_applied"):
        return {"path_normalization": normalization}
    return {}


def _range_metadata(window: dict[str, object]) -> dict[str, object]:
    total_lines = int(window.get("total_lines") or 0)
    start_line = int(window.get("start_line") or 1)
    num_lines = int(window.get("num_lines") or 0)
    end_offset = max(0, start_line - 1 + num_lines)
    has_more = end_offset < total_lines
    return {
        "has_more": has_more,
        "next_offset": end_offset if has_more else None,
    }


def _model_visible_read_output(content: str, window: dict[str, object]) -> str:
    formatted = _format_numbered_lines(
        content,
        start_line=int(window.get("start_line") or 1),
    )
    if not bool(window.get("truncated_by_window")):
        return formatted
    total_lines = int(window.get("total_lines") or 0)
    start_line = int(window.get("start_line") or 1)
    num_lines = int(window.get("num_lines") or 0)
    end_line = start_line + max(num_lines, 1) - 1
    range_metadata = _range_metadata(window)
    continuation = (
        f"; continue with offset={range_metadata['next_offset']}"
        if range_metadata.get("has_more") and range_metadata.get("next_offset") is not None
        else ""
    )
    return f"[read_file window: lines {start_line}-{end_line} of {total_lines}{continuation}]\n{formatted}"


def _format_numbered_lines(content: str, *, start_line: int) -> str:
    if content == "":
        return ""
    lines = content.split("\n")
    first = max(1, int(start_line or 1))
    return "\n".join(f"{line_number:>6}\t{line}" for line_number, line in enumerate(lines, start=first))


def _read_window_key(ctx: "HarnessContext", resolved_path, *, offset: int, limit: int | None) -> str:
    key = ctx._canonical_read_key(resolved_path)  # noqa: SLF001 - shared runtime read-state contract
    return f"{key}:{offset}:{limit if limit is not None else 'EOF'}"


def _read_window_cache(ctx: "HarnessContext") -> set[str]:
    cache = getattr(ctx, "_read_window_snapshots_cache", None)
    if isinstance(cache, set):
        return cache
    cache = set()
    setattr(ctx, "_read_window_snapshots_cache", cache)
    return cache


def _has_read_window(ctx: "HarnessContext", window_key: str) -> bool:
    return window_key in _read_window_cache(ctx)


def _mark_read_window(ctx: "HarnessContext", window_key: str) -> None:
    _read_window_cache(ctx).add(window_key)


def _read_window_repeat_counts(ctx: "HarnessContext") -> dict[str, int]:
    counts = getattr(ctx, "_read_window_repeat_counts_cache", None)
    if isinstance(counts, dict):
        return counts
    counts = {}
    setattr(ctx, "_read_window_repeat_counts_cache", counts)
    return counts


def _bump_read_window_repeat_count(ctx: "HarnessContext", window_key: str) -> int:
    counts = _read_window_repeat_counts(ctx)
    count = int(counts.get(window_key) or 0) + 1
    counts[window_key] = count
    return count


def _reset_other_read_window_repeat_counts(ctx: "HarnessContext", current_window_key: str) -> None:
    counts = _read_window_repeat_counts(ctx)
    for key in list(counts):
        if key != current_window_key:
            counts.pop(key, None)
