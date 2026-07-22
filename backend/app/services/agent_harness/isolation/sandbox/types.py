from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    workspace_root: Path
    writable_roots: tuple[Path, ...]
    readonly_roots: tuple[Path, ...] = ()
    network_enabled: bool = True
    max_output_bytes: int = 100_000
    max_timeout_seconds: int = 300


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    command: str
    cwd: Path
    env: dict[str, str]
    timeout_seconds: int
    policy: SandboxPolicy


@dataclass(slots=True)
class SandboxResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    elapsed_ms: int = 0
    timed_out: bool = False
    denied: bool = False
    denied_reason: str | None = None
    truncated: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.denied or self.timed_out or (self.exit_code is not None and self.exit_code != 0)
