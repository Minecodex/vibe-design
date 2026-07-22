from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class LlmTimeoutProfile:
    connect_seconds: float
    read_seconds: float
    write_seconds: float
    pool_seconds: float


@dataclass(slots=True)
class LlmStreamRequest:
    model: str
    messages: list[dict[str, Any]]
    system: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_choice: dict[str, Any] | str | None = None
    temperature: float = 0.7
    max_tokens: int = 0
    timeout_profile: LlmTimeoutProfile | None = None
    prompt_cache_key: str | None = None


@dataclass(slots=True)
class LlmStreamChunk:
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None


class LlmConnectionFailure(Exception):
    def __init__(
        self,
        *,
        failure_kind: str,
        retryable: bool,
        raw_error_type: str,
        raw_message: str,
        provider_name: str,
        model: str,
        http_status: int | None = None,
        stream_started: bool = False,
        meaningful_output_seen: bool = False,
    ) -> None:
        super().__init__(raw_message or failure_kind)
        self.failure_kind = failure_kind
        self.retryable = retryable
        self.raw_error_type = raw_error_type
        self.raw_message = raw_message
        self.provider_name = provider_name
        self.model = model
        self.http_status = http_status
        self.stream_started = stream_started
        self.meaningful_output_seen = meaningful_output_seen

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "failure_kind": self.failure_kind,
            "retryable": self.retryable,
            "http_status": self.http_status,
            "raw_error_type": self.raw_error_type,
            "raw_message": self.raw_message,
            "stream_started": self.stream_started,
            "meaningful_output_seen": self.meaningful_output_seen,
            "provider_name": self.provider_name,
            "model": self.model,
        }


class LlmStreamClient(Protocol):
    async def stream_chat(
        self,
        request: LlmStreamRequest,
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        ...
