from __future__ import annotations

from app.services.agent_harness.runtime.open_design.artifact_lint_render import render_findings_for_agent
from app.services.agent_harness.runtime.open_design.contracts import ArtifactLintFinding


def test_render_findings_for_agent_uses_artifact_lint_block() -> None:
    rendered = render_findings_for_agent(
        [
            ArtifactLintFinding(
                severity="P0",
                id="purple-gradient",
                message="Found a violet gradient.",
                fix="Use a flat token surface.",
                snippet="linear-gradient(...)",
            ),
            ArtifactLintFinding(
                severity="P1",
                id="external-image",
                message="External placeholder image.",
                fix="Use local placeholder.",
            ),
        ]
    )

    assert rendered.startswith("<artifact-lint>")
    assert "1 P0 (must fix), 1 P1 (should fix), 0 P2 (nice to have)." in rendered
    assert "Repair the registered HTML and call register_artifact + publish_output again." in rendered
    assert "**[P0] purple-gradient**" in rendered
    assert rendered.rstrip().endswith("</artifact-lint>")

