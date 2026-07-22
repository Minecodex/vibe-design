from __future__ import annotations

from .contracts import ArtifactLintFinding


def render_findings_for_agent(findings: list[ArtifactLintFinding]) -> str:
    if not findings:
        return ""
    sorted_findings = sorted(findings, key=_severity_rank)
    p0 = sum(1 for finding in findings if finding.severity == "P0")
    p1 = sum(1 for finding in findings if finding.severity == "P1")
    p2 = sum(1 for finding in findings if finding.severity == "P2")
    lines = [
        "<artifact-lint>",
        "The artifact you just produced has the following anti-slop / design-token issues.",
        f"{p0} P0 (must fix), {p1} P1 (should fix), {p2} P2 (nice to have).",
        "Repair the registered HTML and call register_artifact + publish_output again.",
        "",
    ]
    for finding in sorted_findings:
        lines.append(f"**[{finding.severity}] {finding.id}** — {finding.message}")
        lines.append(f"  Fix: {finding.fix}")
        if finding.snippet:
            lines.append(f"  Snippet: `{finding.snippet}`")
        lines.append("")
    lines.append("</artifact-lint>")
    return "\n".join(lines)


def _severity_rank(finding: ArtifactLintFinding) -> int:
    return {"P0": 0, "P1": 1, "P2": 2}.get(str(finding.severity), 3)

