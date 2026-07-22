from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.llm_runtime import LlmStreamChunk

from .stream_diagnostics import (
    build_stream_diagnostics_payload,
    new_stream_diagnostics_state,
    record_stream_chunk_diagnostics,
)


@dataclass(slots=True)
class ModelStreamTurn:
    text_parts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    chunk_count: int = 0
    content_chunk_count: int = 0
    tool_call_chunk_count: int = 0
    usage_chunk_count: int = 0
    usage_only_chunk_count: int = 0
    finish_reason_chunk_count: int = 0
    provider_usage_only_without_choices_count: int = 0
    provider_tool_call_argument_delta_count: int = 0
    diagnostics_state: dict[str, Any] = field(default_factory=new_stream_diagnostics_state)

    def observe(self, chunk: LlmStreamChunk) -> dict[str, Any]:
        self.chunk_count += 1
        has_content = bool(chunk.content)
        has_tool_calls = bool(chunk.tool_calls)
        has_usage = bool(chunk.usage)
        has_finish_reason = bool(getattr(chunk, "finish_reason", None))

        provider_event_kind = None
        if getattr(chunk, "diagnostics", None):
            diagnostics = chunk.diagnostics or {}
            record_stream_chunk_diagnostics(self.diagnostics_state, diagnostics)
            provider_event_kind = diagnostics.get("provider_event_kind")
            if provider_event_kind == "usage_only_without_choices":
                self.provider_usage_only_without_choices_count += 1
            if provider_event_kind == "tool_call_arguments_delta":
                self.provider_tool_call_argument_delta_count += 1

        if has_content:
            self.content_chunk_count += 1
            # Keep every streamed content chunk, including text the model interleaves
            # with tool-call argument streaming, so the persisted assistant_text matches
            # exactly what was streamed to the client.
            self.text_parts.append(chunk.content or "")
        if has_tool_calls:
            self.tool_call_chunk_count += 1
            self.tool_calls = list(chunk.tool_calls or [])
        if has_usage:
            self.usage_chunk_count += 1
            self.usage = chunk.usage
        if has_finish_reason:
            self.finish_reason_chunk_count += 1
            self.finish_reason = chunk.finish_reason
        if has_usage and not has_content and not has_tool_calls and not has_finish_reason:
            self.usage_only_chunk_count += 1

        return {
            "has_content": has_content,
            "has_tool_calls": has_tool_calls,
            "has_usage": has_usage,
            "has_finish_reason": has_finish_reason,
            "provider_event_kind": provider_event_kind,
        }

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    @property
    def had_activity(self) -> bool:
        return bool(
            self.chunk_count
            or self.text_parts
            or self.tool_calls
            or self.usage
            or self.finish_reason
        )

    def diagnostics_payload(self) -> dict[str, Any]:
        return build_stream_diagnostics_payload(
            chunk_count=self.chunk_count,
            content_chunk_count=self.content_chunk_count,
            tool_call_chunk_count=self.tool_call_chunk_count,
            usage_chunk_count=self.usage_chunk_count,
            usage_only_chunk_count=self.usage_only_chunk_count,
            finish_reason_chunk_count=self.finish_reason_chunk_count,
            provider_usage_only_without_choices_count=self.provider_usage_only_without_choices_count,
            provider_tool_call_argument_delta_count=self.provider_tool_call_argument_delta_count,
            provider_diagnostics_state=self.diagnostics_state,
        )
