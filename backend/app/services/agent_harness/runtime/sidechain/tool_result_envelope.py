from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.services.agent_harness.capabilities.tools._internal.base import ToolResult


DEFAULT_TOOL_RESULT_PREVIEW_CHARS = 4_000
_LARGE_METADATA_TEXT_KEYS = {"stdout", "stderr", "content", "result", "text"}
_TRUNCATION_SIGNAL_KEYS = {
    "truncated",
    "truncated_by_window",
    "stdout_truncated",
    "stderr_truncated",
}


@dataclass(frozen=True, slots=True)
class ToolResultEnvelope:
    preview_content: str
    original_size: int
    preview_size: int
    has_more: bool
    truncated: bool
    persisted: bool
    blob_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview_content": self.preview_content,
            "original_size": self.original_size,
            "preview_size": self.preview_size,
            "has_more": self.has_more,
            "truncated": self.truncated,
            "persisted": self.persisted,
            "blob_ref": self.blob_ref,
        }


def envelope_tool_result(
    *,
    ctx,
    tool_name: str,
    tool_call_id: str | None,
    result: ToolResult,
    preview_chars: int = DEFAULT_TOOL_RESULT_PREVIEW_CHARS,
) -> ToolResult:
    raw_output = result.output or ""
    metadata = dict(result.metadata or {})
    existing_envelope = metadata.get("tool_result_envelope")
    if isinstance(existing_envelope, dict):
        return ToolResult(output=raw_output, is_error=result.is_error, metadata=metadata)
    preview_limit = max(1, int(preview_chars or DEFAULT_TOOL_RESULT_PREVIEW_CHARS))
    original_size = len(raw_output)
    output_exceeds_model_window = original_size > preview_limit
    tool_reported_partial_output = _tool_reported_partial_output(metadata)
    truncated = output_exceeds_model_window or tool_reported_partial_output
    preview = raw_output[:preview_limit]

    if not truncated:
        metadata["tool_result_envelope"] = ToolResultEnvelope(
            preview_content=raw_output,
            original_size=original_size,
            preview_size=original_size,
            has_more=False,
            truncated=False,
            persisted=False,
        ).to_dict()
        return ToolResult(output=raw_output, is_error=result.is_error, metadata=metadata)

    if tool_reported_partial_output and not output_exceeds_model_window:
        envelope = ToolResultEnvelope(
            preview_content=preview,
            original_size=_reported_original_size(metadata) or original_size,
            preview_size=len(preview),
            has_more=bool(metadata.get("has_more", True)),
            truncated=True,
            persisted=False,
            blob_ref=None,
        )
        enveloped_metadata = _trim_large_metadata_text(metadata, preview_limit)
        enveloped_metadata["tool_result_envelope"] = {
            **envelope.to_dict(),
            "reason": "tool_reported_partial_output",
            "next_offset": metadata.get("next_offset"),
        }
        model_visible = _partial_output_message(
            preview=preview,
            preview_size=len(preview),
            original_size=envelope.original_size,
            metadata=metadata,
        )
        return ToolResult(output=model_visible, is_error=result.is_error, metadata=enveloped_metadata)

    blob_ref = _blob_ref(tool_name=tool_name, tool_call_id=tool_call_id, raw_output=raw_output)
    blob_path = ctx.conversation_dir / blob_ref
    try:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists() or blob_path.read_text(encoding="utf-8", errors="replace") != raw_output:
            blob_path.write_text(raw_output, encoding="utf-8")
    except Exception as exc:
        failed_metadata = {
            **metadata,
            "failure_kind": "tool_result_blob_persistence_failed",
            "tool_result_envelope": {
                "preview_content": preview,
                "original_size": original_size,
                "preview_size": len(preview),
                "has_more": True,
                "truncated": True,
                "persisted": False,
                "blob_ref": None,
                "error": str(exc),
            },
        }
        return ToolResult(
            output=f"Could not persist full tool output before returning preview: {exc}",
            is_error=True,
            metadata=failed_metadata,
        )

    envelope = ToolResultEnvelope(
        preview_content=preview,
        original_size=original_size,
        preview_size=len(preview),
        has_more=True,
        truncated=True,
        persisted=True,
        blob_ref=blob_ref,
    )
    enveloped_metadata = _trim_large_metadata_text(metadata, preview_limit)
    enveloped_metadata["tool_result_envelope"] = envelope.to_dict()
    model_visible = (
        f"[tool result preview only: showing {len(preview)} of {original_size} characters; "
        f"full output saved at {blob_ref}]\n{preview}"
    )
    return ToolResult(output=model_visible, is_error=result.is_error, metadata=enveloped_metadata)


def _tool_reported_partial_output(metadata: dict[str, Any]) -> bool:
    if any(bool(metadata.get(key)) for key in _TRUNCATION_SIGNAL_KEYS):
        return True
    return bool(metadata.get("has_more") and metadata.get("next_offset") is not None)


def _reported_original_size(metadata: dict[str, Any]) -> int | None:
    for key in ("original_size", "total_size", "size_chars", "size_bytes"):
        try:
            value = int(metadata.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return None


def _partial_output_message(
    *,
    preview: str,
    preview_size: int,
    original_size: int,
    metadata: dict[str, Any],
) -> str:
    next_offset = metadata.get("next_offset")
    continuation = f"; continue with offset={next_offset}" if next_offset is not None else ""
    return (
        "[tool result preview only: the tool returned partial output"
        f"; showing {preview_size} of at least {original_size} characters"
        f"; full output was not returned by this tool{continuation}]\n{preview}"
    )


def _blob_ref(*, tool_name: str, tool_call_id: str | None, raw_output: str) -> str:
    safe_tool = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(tool_name or "tool")).strip("-") or "tool"
    stable_source = f"{tool_name}:{tool_call_id or ''}:{hashlib.sha256(raw_output.encode('utf-8')).hexdigest()}"
    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:24]
    return f".agent/blobs/tool-results/{safe_tool}-{digest}.txt"


def _trim_large_metadata_text(metadata: dict[str, Any], preview_limit: int) -> dict[str, Any]:
    trimmed = dict(metadata)
    for key in _LARGE_METADATA_TEXT_KEYS:
        value = trimmed.get(key)
        if isinstance(value, str) and len(value) > preview_limit:
            trimmed[key] = value[:preview_limit]
            trimmed[f"{key}_preview_only"] = True
    return trimmed
