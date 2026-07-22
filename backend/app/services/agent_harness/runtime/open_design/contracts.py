from __future__ import annotations

from dataclasses import dataclass


LintSeverity = str


@dataclass(frozen=True, slots=True)
class ArtifactLintFinding:
    severity: LintSeverity
    id: str
    message: str
    fix: str
    snippet: str | None = None

    def to_payload(self) -> dict[str, str]:
        payload = {
            "severity": self.severity,
            "id": self.id,
            "message": self.message,
            "fix": self.fix,
        }
        if self.snippet:
            payload["snippet"] = self.snippet
        return payload


@dataclass(frozen=True, slots=True)
class ArtifactLintResult:
    findings: list[ArtifactLintFinding]

    @property
    def p0_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "P0")

    @property
    def p1_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "P1")

    @property
    def p2_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "P2")

    @property
    def blocks_publish(self) -> bool:
        return self.p0_count > 0

    def to_payload(self) -> dict[str, object]:
        return {
            "findings": [finding.to_payload() for finding in self.findings],
            "p0_count": self.p0_count,
            "p1_count": self.p1_count,
            "p2_count": self.p2_count,
            "blocks_publish": self.blocks_publish,
        }


@dataclass(frozen=True, slots=True)
class ArtifactBlock:
    identifier: str | None
    type: str
    title: str | None
    html: str
    raw_text_before: str = ""
    raw_text_after: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactCaptureResult:
    entry: str | None
    title: str | None
    manifest: dict | None
    replacement_text: str
    error_text: str | None = None
