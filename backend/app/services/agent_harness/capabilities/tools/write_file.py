from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.workspace.generated_content.entry_validation_service import (
    validate_serialized_content,
)
from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.capabilities.skill_protocols.registry import resolve_protocol_for_context
from app.services.agent_harness.capabilities.skill_protocols.tool_guard import (
    ProtocolToolGuard,
    tool_result_from_protocol_failure,
)
from app.services.agent_harness.capabilities.skill_protocols.validation_profiles import (
    validate_protocol_write_content,
)
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    add_normalization_warning,
    resolve_work_file_path,
    workspace_path_metadata,
)
from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.capabilities.tools._internal.json_content import (
    JsonContentError,
    normalize_json_content,
    serialize_jsonl_content,
)
from app.services.agent_harness.isolation.security.paths import normalize_tool_base

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


# Common shorthands the model reaches for that are not themselves valid `kind`
# literals. We canonicalize them before validation so a reasonable value like
# "js" or "py" doesn't fail with a literal_error and force a wasted retry.
# Mapped targets are all passthrough-serialized + leniently validated, so the
# alias never changes the written bytes.
_KIND_ALIASES: dict[str, str] = {
    "js": "js_module",
    "javascript": "js_module",
    "mjs": "js_module",
    "cjs": "js_module",
    "jsx": "js_module",
    "node": "js_module",
    "typescript": "ts",
    "tsx": "ts",
    "py": "python",
    "md": "markdown",
    "mdx": "markdown",
    "htm": "html",
    "scss": "css",
    "sass": "css",
    "less": "css",
    "txt": "text",
    "plain": "text",
}


class WriteFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    base: str = Field("work", description="Semantic write root: work, project, skill, references, published, or project:<relative-dir>. Read-only roots are rejected.")
    path: str = Field(..., validation_alias=AliasChoices("path", "file_path"), serialization_alias="path")
    content: Any = Field(...)
    kind: Literal["text", "json", "jsonl", "markdown", "html", "js_module", "python", "css", "ts"] = Field(
        "text",
        description=(
            "Content kind, one of: text, json, jsonl, markdown, html, js_module, python, css, ts. "
            "Use the matching value for code/source files (python, css, ts, js_module — note JavaScript is `js_module`) "
            "or text for any other plain-text/source file; json/jsonl/markdown/html get format-specific handling and "
            "validation. Common aliases (js, jsx, py, htm, scss, ...) are accepted and normalized."
        ),
    )
    overwrite: bool = Field(True)
    allow_json_scalar: bool = Field(False)

    @property
    def file_path(self) -> str:
        return self.path

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        return _KIND_ALIASES.get(normalized, normalized)


class WriteFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write a complete file under the selected semantic base (default `work`, the current artifact's work directory). "
            "Use it to create a new file or to fully rewrite one when you are replacing essentially all of its contents; "
            "it overwrites the existing file at the path. To change only part of an existing file, prefer `edit_file`, "
            "which sends just the modified text instead of regenerating the whole file — far cheaper for large files. "
            "Writes are confined to writable bases (work/project); skill, references, and published are read-only."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return WriteFileInput

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, WriteFileInput)
        base = _write_base(params)
        decision = get_security_service().check_write_path(ctx, location="project", path=params.file_path, base=base)
        if not decision.allowed:
            return decision.reason
        resolved = resolve_work_file_path(params.file_path, ctx, base=base)
        assert resolved is not None
        if resolved.resolved.exists() and not params.overwrite:
            return f"File already exists: {params.file_path}"
        return None

    async def execute(self, params: WriteFileInput, ctx: "HarnessContext") -> ToolResult:
        base = _write_base(params)
        decision = get_security_service().check_write_path(ctx, location="project", path=params.file_path, base=base)
        if not decision.allowed:
            return ToolResult(
                output=decision.reason or f"Path is not writable: {params.file_path}",
                is_error=True,
                metadata={
                    "failure_kind": decision.reason_code or "path_not_writable",
                    "path": params.file_path,
                    "base": base or "work",
                    **(decision.metadata or {}),
                },
            )
        resolved = resolve_work_file_path(params.file_path, ctx, base=base)
        if resolved is None:
            return ToolResult(
                output=f"Writable files must live under the current artifact work directory, not {params.file_path}.",
                is_error=True,
                metadata={
                    "failure_kind": "path_not_writable",
                    "path": params.file_path,
                    "base": base or "work",
                },
            )
        try:
            payload, content_metadata = _serialize_content(
                params.kind,
                params.content,
                allow_json_scalar=params.allow_json_scalar,
            )
        except JsonContentError as exc:
            return ToolResult(
                output=str(exc),
                is_error=True,
                metadata={
                    "failure_kind": "json_content_invalid",
                    "kind": params.kind,
                    "path": f"project/{resolved.normalized_path}",
                    "file_path": resolved.normalized_path,
                },
            )
        protocol = resolve_protocol_for_context(ctx)
        guard_failure = ProtocolToolGuard(ctx, protocol).check_write_target(resolved.normalized_path)
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
        validation = validate_serialized_content(
            payload,
            kind=params.kind,
            path_hint=params.file_path,
            base_dir=resolved.resolved.parent,
        )
        if not validation["valid"]:
            return ToolResult(
                output="; ".join(validation["errors"]) or "Candidate validation failed",
                is_error=True,
                metadata=validation,
            )
        protocol_validation = validate_protocol_write_content(
            payload,
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
        await run_file_io(resolved.resolved.parent.mkdir, parents=True, exist_ok=True)
        await run_file_io(resolved.resolved.write_text, payload, encoding="utf-8")
        metadata = {
            **workspace_path_metadata(
                ctx,
                resolved.resolved,
                location="project",
                file_path=resolved.normalized_path,
            ),
            "bytes": len(payload.encode("utf-8")),
            "kind": params.kind,
            "validation": validation,
            **content_metadata,
        }
        protocol_metadata = protocol_validation.get("metadata")
        if isinstance(protocol_metadata, dict) and protocol_metadata:
            metadata["protocol_validation"] = protocol_metadata
        _attach_prepared_workspace_flags(ctx, metadata)
        output, metadata = add_normalization_warning(
            output=json.dumps(metadata, ensure_ascii=False),
            metadata=metadata,
            warning=resolved.warning,
            normalized_path=resolved.normalized_path,
            original=resolved.original_path,
            audit_metadata=resolved.audit_metadata,
        )
        return ToolResult(output=output, metadata=metadata)


def _write_base(params: WriteFileInput) -> str:
    return params.base or "work"


def _attach_prepared_workspace_flags(ctx: "HarnessContext", metadata: dict[str, Any]) -> None:
    prepared_entry = str(getattr(ctx, "prepared_entry_file", "") or "").replace("\\", "/").strip().lstrip("/")
    target_path = str(metadata.get("conversation_path") or metadata.get("path") or "").replace("\\", "/").strip().lstrip("/")
    if not prepared_entry or not target_path:
        return
    is_prepared_entry = target_path == f"project/{prepared_entry}".strip("/")
    if not is_prepared_entry:
        return
    metadata["prepared_workspace_entry"] = True
    metadata["prepared_entry_file"] = prepared_entry
    metadata["prepared_workspace_entry_overwritten"] = True


def _serialize_content(kind: str, content: Any, *, allow_json_scalar: bool = False) -> tuple[str, dict[str, Any]]:
    if kind == "json":
        normalized = normalize_json_content(content, allow_json_scalar=allow_json_scalar)
        return normalized.text, normalized.metadata
    if kind == "jsonl":
        return serialize_jsonl_content(content), {"jsonl_records": len(content)}
    if kind in {"markdown", "html", "js_module", "python", "css", "ts"}:
        if not isinstance(content, str):
            raise JsonContentError(f"{kind} content must be a string")
        return content, {}
    if isinstance(content, str):
        return content, {}
    return json.dumps(content, ensure_ascii=False, indent=2), {}
