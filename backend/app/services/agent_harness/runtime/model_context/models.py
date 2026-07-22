from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CompactType = Literal["auto_full", "session_memory", "manual"]


class ModelContextLimitExceeded(RuntimeError):
    """Raised when a turn cannot be assembled without compacting first."""

    def __init__(
        self,
        message: str,
        *,
        token_usage: int,
        blocking_limit_tokens: int,
        auto_compact_enabled: bool,
    ) -> None:
        super().__init__(message)
        self.token_usage = int(token_usage)
        self.blocking_limit_tokens = int(blocking_limit_tokens)
        self.auto_compact_enabled = bool(auto_compact_enabled)


@dataclass(frozen=True, slots=True)
class CompactionBoundaryV2:
    boundary_id: str
    compact_type: CompactType
    covered: dict[str, Any]
    summary_message: dict[str, Any]
    restore_messages: list[dict[str, Any]]
    token_counts: dict[str, Any]
    method: dict[str, Any]
    event_sequence: int
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelContextBudget:
    effective_window_tokens: int
    auto_threshold_tokens: int
    predictive_threshold_tokens: int
    blocking_limit_tokens: int
    reserved_output_tokens: int
    predictive_turn_growth_tokens: int
    buffer_tokens: int
    auto_compact_enabled: bool
    microcompact_threshold_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ModelContextTokenState:
    token_usage: int
    projected_token_usage: int
    percent_left: int
    is_above_auto_compact_threshold: bool
    is_above_predictive_threshold: bool
    is_at_blocking_limit: bool


@dataclass(frozen=True, slots=True)
class ModelContextBundle:
    messages: list[dict[str, Any]]
    compact_messages: list[dict[str, Any]]
    persisted_messages: list[dict[str, Any]]
    boundary: CompactionBoundaryV2 | None
    message_row_id_end: int
    event_sequence_end: int
    source: str
    token_state: ModelContextTokenState | None = None


@dataclass(frozen=True, slots=True)
class RestorePlan:
    messages: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompactResult:
    boundary: CompactionBoundaryV2
    compact_type: CompactType
    summary_message: dict[str, Any]
    restore_messages: list[dict[str, Any]]
    token_counts: dict[str, Any]
    method: dict[str, Any]
