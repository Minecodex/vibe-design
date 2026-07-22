from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.capabilities.skill_protocols.registry import resolve_protocol_for_context
from app.services.agent_harness.capabilities.skill_protocols.tool_guard import ProtocolToolGuard, tool_result_from_protocol_failure
from app.services.agent_harness.capabilities.skill_protocols.validation_profiles import validate_protocol_write_content
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    add_normalization_warning,
    read_text_file,
    resolve_work_file_path,
    sha256_text,
    workspace_path_metadata,
)
from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.isolation.security.paths import normalize_tool_base

if TYPE_CHECKING:
    from pathlib import Path

    from app.services.agent_harness.core.context import HarnessContext


class TextReplacementInput(BaseModel):
    old_text: str = Field(
        ...,
        description=(
            "Existing text to replace. Must match exactly once unless replace_all is true. "
            "Curly quotes and tab/space differences are tolerated automatically."
        ),
    )
    new_text: str = Field(..., description="Replacement text.")
    replace_all: bool = Field(
        False,
        description="Replace every occurrence of old_text instead of requiring a unique match. Use for renames.",
    )

    @field_validator("old_text")
    @classmethod
    def old_text_must_not_be_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("old_text must not be empty")
        return value


class EditFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field("work", description="Semantic edit root: work, project, skill, references, published, or project:<relative-dir>. Read-only roots are rejected.")
    path: str = Field(
        ...,
        validation_alias=AliasChoices("path", "file_path"),
        serialization_alias="path",
        description="Project file path, for example project/foo.py.",
    )
    edits: list[TextReplacementInput] = Field(
        ...,
        min_length=1,
        description="One or more exact text replacements to apply atomically to this file.",
    )

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


@dataclass(frozen=True, slots=True)
class _ResolvedEdit:
    start: int
    end: int
    old_text: str
    new_text: str


class EditFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Preferred tool for modifying an existing text file in your working directory (paths resolve under the work/project bases). "
            "Applies one or more exact old_text -> new_text replacements and sends only the changed text, so it is far cheaper than "
            "rewriting the whole file with `write_file` — always prefer it when the file already exists and you are changing only part of it. "
            "Each old_text must match exactly once; include just enough surrounding context (usually 2-4 adjacent lines) to be unique, "
            "or set replace_all on that edit to change every occurrence (handy for renames). "
            "Matching tolerates curly-vs-straight quotes and tab/space differences, so copy the text as the read tool shows it. "
            "Use the file's current text as old_text — never the value you just changed it to. "
            "All edits are validated before writing, so a failed edit never partially modifies the file. "
            "The file must already exist under a writable base (skill/references/published are read-only)."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return EditFileInput

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, EditFileInput)
        base = _edit_base(params)
        decision = get_security_service().check_write_path(ctx, location="project", path=params.file_path, base=base)
        if not decision.allowed:
            return decision.reason
        resolved = resolve_work_file_path(params.file_path, ctx, base=base)
        if resolved is None:
            return (
                f"Text files must live under project/. Use a project path like project/foo.py, "
                f"not {params.file_path}."
            )
        if not resolved.resolved.exists() or not resolved.resolved.is_file():
            return f"File not found: {params.file_path}"
        return None

    async def execute(self, params: EditFileInput, ctx: "HarnessContext") -> ToolResult:
        base = _edit_base(params)
        decision = get_security_service().check_write_path(ctx, location="project", path=params.file_path, base=base)
        if not decision.allowed:
            return ToolResult(
                output=decision.reason or f"Path is not editable: {params.file_path}",
                is_error=True,
                metadata={
                    "failure_kind": decision.reason_code or "path_not_editable",
                    "path": params.file_path,
                    "base": base or "work",
                    **(decision.metadata or {}),
                },
            )
        resolved = resolve_work_file_path(params.file_path, ctx, base=base)
        if resolved is None:
            return ToolResult(
                output=f"Editable files must live under the current artifact work directory, not {params.file_path}.",
                is_error=True,
                metadata={
                    "failure_kind": "path_not_editable",
                    "path": params.file_path,
                    "base": base or "work",
                },
            )
        if not resolved.resolved.exists() or not resolved.resolved.is_file():
            return ToolResult(
                output=f"File not found: {params.file_path}",
                is_error=True,
                metadata={
                    "failure_kind": "file_not_found",
                    "path": f"project/{resolved.normalized_path}",
                    "file_path": resolved.normalized_path,
                },
            )

        protocol = resolve_protocol_for_context(ctx)
        guard_failure = ProtocolToolGuard(ctx, protocol).check_write_target(resolved.normalized_path, operation="update")
        if guard_failure is not None:
            return tool_result_from_protocol_failure(
                guard_failure,
                metadata={
                    "path": f"project/{resolved.normalized_path}",
                    "file_path": resolved.normalized_path,
                    "protocol_family": protocol.family,
                    "protocol_provider": protocol.provider,
                },
            )

        try:
            old_text = await run_file_io(read_text_file, resolved.resolved)
            new_text, resolved_edits = _apply_replacements(old_text, params.edits, resolved.normalized_path)
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True, metadata={"reason": "invalid_edit"})

        protocol_validation = validate_protocol_write_content(
            new_text,
            normalized_path=resolved.normalized_path,
            protocol=protocol,
            base_dir=resolved.resolved.parent,
        )
        if not protocol_validation["valid"]:
            return ToolResult(
                output="; ".join(protocol_validation["errors"]) or "Skill protocol validation failed",
                is_error=True,
                metadata=protocol_validation,
            )

        try:
            if new_text != old_text:
                await run_file_io(resolved.resolved.write_bytes, new_text.encode("utf-8"))
                ctx.mark_file_read(resolved.resolved)
        except Exception as exc:
            rollback_applied = await run_file_io(_restore_original_text, resolved.resolved, old_text)
            return ToolResult(
                output=(
                    f"Edit failed after writing {resolved.normalized_path}; "
                    f"{'rolled back to the original content' if rollback_applied else 'rollback failed'}: {exc}"
                ),
                is_error=True,
                metadata={
                    "reason": "write_failed",
                    "path": f"project/{resolved.normalized_path}",
                    "file_path": resolved.normalized_path,
                    "rollback_applied": rollback_applied,
                },
            )

        changed_item = {
            **workspace_path_metadata(ctx, resolved.resolved, location="project", file_path=resolved.normalized_path),
            "action": "update",
            "sha256": sha256_text(new_text),
            "changed": new_text != old_text,
            "edit_count": len(resolved_edits),
            "first_changed_line": _first_changed_line(old_text, resolved_edits),
            "diff": _unified_diff(old_text, new_text, resolved.normalized_path),
        }
        _attach_prepared_workspace_flags(ctx, changed_item)
        payload = {"changed_files": [changed_item]}
        output, payload = add_normalization_warning(
            output=json.dumps(payload, ensure_ascii=False),
            metadata=payload,
            warning=resolved.warning,
            normalized_path=resolved.normalized_path,
            original=resolved.original_path,
            audit_metadata=resolved.audit_metadata,
        )
        return ToolResult(output=output, metadata=payload)


def _edit_base(params: EditFileInput) -> str:
    return params.base or "work"


def _apply_replacements(
    original: str,
    edits: list[TextReplacementInput],
    path: str,
) -> tuple[str, list[_ResolvedEdit]]:
    # Resolve every edit before failing so the model gets the full picture in one
    # shot: which edits matched cleanly, which were ambiguous, and — crucially —
    # for a missing old_text, what the closest existing text actually is. The old
    # behaviour raised on the first failure with no current-content hint, which
    # left the model re-sending the same unmatched old_text verbatim.
    #
    # Matching is forgiving like Claude Code's Edit tool: old_text is resolved to
    # the actual file text through a cascade (exact -> curly/straight quotes ->
    # tab/space) so the model does not have to reproduce whitespace byte-for-byte.
    resolved_edits: list[_ResolvedEdit] = []
    failures: list[str] = []
    applied_new_texts: list[str] = []
    for index, edit in enumerate(edits, start=1):
        actual = _find_actual_text(original, edit.old_text)
        if actual is None:
            stripped = edit.old_text.strip()
            if stripped and any(stripped in prior for prior in applied_new_texts):
                failures.append(
                    f"edit #{index}: old_text was not found, but it appears inside an earlier edit's new_text "
                    f"— you are likely using the value you just changed it to. Use the file's current "
                    f"(pre-edit) text as old_text."
                )
            else:
                failures.append(
                    f"edit #{index}: old_text was not found.{_nearest_text_hint(original, edit.old_text)}"
                )
            continue
        matches = _find_all(original, actual)
        if len(matches) > 1 and not edit.replace_all:
            lines = ", ".join(str(_line_for_offset(original, offset)) for offset in matches[:10])
            failures.append(
                f"edit #{index}: old_text matched {len(matches)} times (lines {lines}); "
                f"set replace_all=true to replace every occurrence, or include more surrounding context "
                f"so it is unique."
            )
            continue
        for start in matches:
            resolved_edits.append(
                _ResolvedEdit(start=start, end=start + len(actual), old_text=actual, new_text=edit.new_text)
            )
        applied_new_texts.append(edit.new_text)

    if failures:
        matched = len(resolved_edits)
        header = (
            f"{len(failures)} of {len(edits)} edit(s) to {path} could not be applied, so the file was left unchanged"
            f" ({matched} edit(s) matched cleanly). Re-read the file to copy the exact current text "
            f"(including whitespace) and retry — do not resend the same old_text:"
        )
        raise ValueError(header + "\n- " + "\n- ".join(failures))

    resolved_edits.sort(key=lambda edit: edit.start)
    for previous, current in zip(resolved_edits, resolved_edits[1:]):
        if current.start < previous.end:
            raise ValueError(
                f"Edit ranges overlap in {path}; merge overlapping replacements into a single edit."
            )

    chunks: list[str] = []
    cursor = 0
    for edit in resolved_edits:
        chunks.append(original[cursor : edit.start])
        chunks.append(edit.new_text)
        cursor = edit.end
    chunks.append(original[cursor:])
    return "".join(chunks), resolved_edits


# Curly quotes the model cannot emit but that often appear in files; we match
# them against the straight quotes the model sends.
_LEFT_SINGLE_QUOTE = "‘"
_RIGHT_SINGLE_QUOTE = "’"
_LEFT_DOUBLE_QUOTE = "“"
_RIGHT_DOUBLE_QUOTE = "”"


def _normalize_quotes(text: str) -> str:
    return (
        text.replace(_LEFT_SINGLE_QUOTE, "'")
        .replace(_RIGHT_SINGLE_QUOTE, "'")
        .replace(_LEFT_DOUBLE_QUOTE, '"')
        .replace(_RIGHT_DOUBLE_QUOTE, '"')
    )


def _normalize_whitespace(text: str) -> str:
    # Read output renders tabs as spaces, so the model often copies spaces where
    # the file has tabs. Expand tabs to a canonical width for fuzzy matching.
    return text.replace("\t", "    ")


def _find_actual_text(file_content: str, search: str) -> str | None:
    """Resolve search to the real substring present in file_content.

    Cascade: exact -> quote-normalized -> whitespace-normalized -> combined.
    Quote normalization is length-preserving, so its match index maps directly.
    Whitespace normalization expands tabs, so matches are mapped back to the
    original byte ranges via :func:`_map_normalized_match_back`.
    """
    if search in file_content:
        return search

    normalized_search = _normalize_quotes(search)
    normalized_file = _normalize_quotes(file_content)
    index = normalized_file.find(normalized_search)
    if index != -1:
        return file_content[index : index + len(search)]

    ws_file = _normalize_whitespace(file_content)
    ws_search = _normalize_whitespace(search)
    ws_index = ws_file.find(ws_search)
    if ws_index != -1:
        return _map_normalized_match_back(file_content, ws_index, len(ws_search))

    combined_file = _normalize_whitespace(normalized_file)
    combined_search = _normalize_whitespace(normalized_search)
    combined_index = combined_file.find(combined_search)
    if combined_index != -1:
        return _map_normalized_match_back(file_content, combined_index, len(combined_search))

    return None


def _map_normalized_match_back(file_content: str, normalized_start: int, normalized_length: int) -> str:
    """Map a match in the tab-expanded view back to the original substring.

    Walks both strings together: a literal tab advances the normalized cursor by
    4 but the original cursor by 1.
    """
    norm_pos = 0
    orig_pos = 0
    orig_start = -1
    orig_end = -1
    target_end = normalized_start + normalized_length

    while orig_pos < len(file_content) and norm_pos <= target_end:
        if norm_pos == normalized_start:
            orig_start = orig_pos
        if norm_pos == target_end:
            orig_end = orig_pos
            break
        if file_content[orig_pos] == "\t":
            next_norm = norm_pos + 4
            if norm_pos < normalized_start and next_norm > normalized_start and orig_start == -1:
                orig_start = orig_pos
            if norm_pos < target_end and next_norm > target_end and orig_end == -1:
                orig_end = orig_pos + 1
            norm_pos = next_norm
        else:
            norm_pos += 1
        orig_pos += 1

    if orig_start == -1:
        orig_start = 0
    if orig_end == -1:
        orig_end = orig_pos
    return file_content[orig_start:orig_end]


def _nearest_text_hint(original: str, old_text: str) -> str:
    """Point the model at the closest existing line so it can fix a stale old_text."""
    anchor = next((line for line in old_text.splitlines() if line.strip()), "").strip()
    if not anchor:
        return ""
    best_ratio = 0.0
    best_index = -1
    for index, line in enumerate(original.splitlines()):
        ratio = difflib.SequenceMatcher(None, anchor, line.strip()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_index = index
    if best_index < 0 or best_ratio < 0.5:
        return ""
    actual = original.splitlines()[best_index].strip()
    return f" Closest existing text is at line {best_index + 1} (~{best_ratio:.0%} similar): {actual!r}."


def _find_all(text: str, needle: str) -> list[int]:
    matches: list[int] = []
    cursor = 0
    while True:
        index = text.find(needle, cursor)
        if index < 0:
            return matches
        matches.append(index)
        cursor = index + max(len(needle), 1)


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _first_changed_line(original: str, edits: list[_ResolvedEdit]) -> int | None:
    if not edits:
        return None
    return _line_for_offset(original, min(edit.start for edit in edits))


def _unified_diff(original: str, updated: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def _restore_original_text(path: "Path", original: str) -> bool:
    try:
        path.write_bytes(original.encode("utf-8"))
    except Exception:
        return False
    return True


def _attach_prepared_workspace_flags(ctx: "HarnessContext", metadata: dict[str, object]) -> None:
    prepared_entry = str(getattr(ctx, "prepared_entry_file", "") or "").replace("\\", "/").strip().lstrip("/")
    target_path = str(metadata.get("conversation_path") or metadata.get("path") or "").replace("\\", "/").strip().lstrip("/")
    if not prepared_entry or not target_path:
        return
    is_prepared_entry = target_path == f"project/{prepared_entry}".strip("/")
    if not is_prepared_entry:
        return
    metadata["prepared_workspace_entry"] = True
    metadata["prepared_entry_file"] = prepared_entry
