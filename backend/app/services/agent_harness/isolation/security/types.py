from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SecurityVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True, slots=True)
class NormalizationEntry:
    warning: str
    normalized_value: str | None = None
    original_value: str | None = None
    kind: str = "normalization"


@dataclass(frozen=True, slots=True)
class ResolvedWorkspacePath:
    resolved: Path
    normalized_path: str
    location: str
    warning: str | None = None
    original_path: str | None = None
    audit_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    command: str
    cwd: Path
    location: str
    warning: str | None = None
    original_command: str | None = None


@dataclass(frozen=True, slots=True)
class SecurityDecision:
    verdict: SecurityVerdict
    reason: str | None = None
    reason_code: str | None = None
    warnings: tuple[NormalizationEntry, ...] = ()
    normalized_value: str | None = None
    resolved_path: Path | None = None
    resolved_cwd: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict == SecurityVerdict.ALLOW
