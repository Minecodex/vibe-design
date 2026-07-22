from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PanelistRole = Literal["designer", "critic", "brand", "a11y", "copy"]
FallbackPolicy = Literal["ship_best", "ship_last", "fail"]
RoundDecision = Literal["continue", "ship"]
CritiqueWarningCode = Literal[
    "screenshot_unavailable",
    "screenshot_file_missing",
    "screenshot_file_type_unverified",
    "unknown_role",
    "score_clamped",
    "composite_mismatch",
    "artifact_not_critiqueable",
]
CritiqueRunStatus = Literal[
    "running",
    "shipped",
    "below_threshold",
    "degraded",
    "interrupted",
    "failed",
]


@dataclass(frozen=True, slots=True)
class CritiqueConfig:
    enabled: bool = False
    max_rounds: int = 3
    score_scale: int = 10
    score_threshold: float = 8.0
    fallback_policy: FallbackPolicy = "ship_best"
    per_round_timeout_seconds: float = 90.0
    total_timeout_seconds: float = 240.0
    parser_max_block_bytes: int = 262_144
    protocol_version: int = 1

    def validate(self) -> "CritiqueConfig":
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        if self.score_scale < 1:
            raise ValueError("score_scale must be positive")
        if self.score_threshold < 0 or self.score_threshold > self.score_scale:
            raise ValueError("score_threshold must be between zero and score_scale")
        if self.fallback_policy not in {"ship_best", "ship_last", "fail"}:
            raise ValueError("fallback_policy must be ship_best, ship_last, or fail")
        if self.per_round_timeout_seconds <= 0:
            raise ValueError("per_round_timeout_seconds must be positive")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.parser_max_block_bytes < 1024:
            raise ValueError("parser_max_block_bytes must be at least 1024")
        return self


@dataclass(frozen=True, slots=True)
class CritiqueFinding:
    role: PanelistRole
    text: str


@dataclass(frozen=True, slots=True)
class CritiqueWarning:
    code: CritiqueWarningCode | str
    message: str


@dataclass(frozen=True, slots=True)
class CritiqueEvidence:
    entry: str
    path: str
    kind: str = "rendered_screenshot"


@dataclass(frozen=True, slots=True)
class CritiqueDimension:
    role: PanelistRole
    name: str
    score: float
    note: str


@dataclass(frozen=True, slots=True)
class CritiqueRound:
    round_number: int
    active_entry: str
    artifact_work_root: str
    composite: float
    must_fix_count: int
    findings: tuple[CritiqueFinding, ...] = field(default_factory=tuple)
    snapshot_relpath: str | None = None
