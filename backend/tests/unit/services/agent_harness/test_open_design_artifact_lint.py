from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.services.agent_harness.runtime.open_design.artifact_lint import lint_artifact
from app.services.agent_harness.runtime.open_design.design_system_compliance import lint_design_system_compliance


def _ids(html: str) -> set[str]:
    return {finding.id for finding in lint_artifact(html)}


def _active_design_context() -> dict:
    return {
        "kind": "active_design_system_context",
        "design_system_id": "test",
        "tokens_css": """
        :root {
          --bg: #FFFFFF;
          --surface: #F8FAFC;
          --fg: #0F172A;
          --muted: #64748B;
          --border: #CBD5E1;
          --accent: #FECE14;
          --font-display: Georgia, serif;
          --font-body: Arial, sans-serif;
          --text-base: 16px;
          --radius-md: 8px;
          --focus-ring: 0 0 0 3px rgba(254, 206, 20, 0.35);
          --container-max: 1120px;
        }
        """,
    }


def test_lint_flags_p0_slop_patterns() -> None:
    html = """
    <!doctype html><html><head><style>
    :root { --primary: #6366f1; }
    .hero { background: linear-gradient(90deg, #3b82f6, #06b6d4); }
    .card { border-left: 4px solid #6366f1; border-radius: 16px; }
    h1 { font-family: Inter, system-ui, sans-serif; }
    </style></head><body>
      <h1>10× faster launch ✨</h1>
      <section>Feature One</section>
      <script>document.querySelector('.hero').scrollIntoView()</script>
    </body></html>
    """

    ids = _ids(html)

    assert {
        "trust-gradient",
        "ai-default-indigo",
        "emoji-icon",
        "left-accent-card",
        "sans-display",
        "invented-metric",
        "filler-copy",
        "scroll-into-view",
    }.issubset(ids)


def test_lint_flags_visual_slop_patterns_as_p0() -> None:
    html = """
    <!doctype html><html><body>
      <section>Hand drawn doodle sketch illustration for the hero.</section>
      <img src="team.jpg" alt="smiling person using laptop in office">
      <div>Mountain landscape at sunset hero background.</div>
    </body></html>
    """

    ids = _ids(html)

    assert {
        "hand-drawn-illustration",
        "generic-person-photo",
        "generic-scenery-hero",
    }.issubset(ids)


def test_lint_allows_indigo_when_it_is_the_global_accent_token() -> None:
    html = """
    <!doctype html><html><head><style>
    :root { --accent: #6366f1; }
    .button { color: var(--accent); }
    </style></head><body><h1>Specific launch plan</h1></body></html>
    """

    assert "ai-default-indigo" not in _ids(html)


def test_lint_flags_uppercase_without_tracking_as_p1() -> None:
    html = """
    <!doctype html><html><head><style>
    .eyebrow { text-transform: uppercase; font-size: 24px; letter-spacing: 1px; }
    </style></head><body><p class="eyebrow">Launch notes</p></body></html>
    """

    findings = lint_artifact(html)

    assert any(finding.id == "all-caps-no-tracking" and finding.severity == "P1" for finding in findings)


def test_lint_flags_p1_p2_density_and_static_contrast_rules() -> None:
    html = """
    <!doctype html><html><head><style>
      .a { background: linear-gradient(red, blue); }
      .b { background: linear-gradient(#111, #222); }
      .c { background: linear-gradient(#333, #444); }
      .d { background: linear-gradient(#555, #666); }
      .low { color: #777777; background: #777777; }
    </style></head><body>
      <span class="icon">x</span><span class="icon">x</span><span class="icon">x</span><span class="icon">x</span>
      <svg></svg><svg></svg><svg></svg><svg></svg><svg></svg><svg></svg><svg></svg><svg></svg><svg></svg>
    </body></html>
    """

    findings = lint_artifact(html)
    ids = {finding.id for finding in findings}

    assert "excessive-gradients" in ids
    assert "excessive-icons" in ids
    assert "static-low-contrast" in ids
    assert any(finding.id == "excessive-gradients" and finding.severity == "P1" for finding in findings)
    assert any(finding.id == "excessive-icons" and finding.severity == "P2" for finding in findings)


def test_design_system_compliance_flags_modified_core_token() -> None:
    html = """
    <!doctype html><html><head><style>
    :root {
      --bg: #FFFFFF;
      --surface: #F8FAFC;
      --fg: #0F172A;
      --muted: #64748B;
      --border: #CBD5E1;
      --accent: #2563EB;
      --font-display: Georgia, serif;
      --font-body: Arial, sans-serif;
      --text-base: 16px;
      --radius-md: 8px;
      --focus-ring: 0 0 0 3px rgba(254, 206, 20, 0.35);
      --container-max: 1120px;
    }
    .cta { background: var(--accent); }
    </style></head><body><a class="cta">Start</a></body></html>
    """

    result = lint_design_system_compliance(html, active_design_system_context=_active_design_context())

    assert result.blocks_publish is True
    assert "design-system-core-token-modified" in {finding.id for finding in result.findings}


def test_design_system_compliance_flags_raw_hex_outside_root() -> None:
    html = """
    <!doctype html><html><head><style>
    :root {
      --bg: #FFFFFF;
      --surface: #F8FAFC;
      --fg: #0F172A;
      --muted: #64748B;
      --border: #CBD5E1;
      --accent: #FECE14;
      --font-display: Georgia, serif;
      --font-body: Arial, sans-serif;
      --text-base: 16px;
      --radius-md: 8px;
      --focus-ring: 0 0 0 3px rgba(254, 206, 20, 0.35);
      --container-max: 1120px;
    }
    .cta { background: #FECE14; }
    </style></head><body><a class="cta">Start</a></body></html>
    """

    result = lint_design_system_compliance(html, active_design_system_context=_active_design_context())

    assert result.blocks_publish is True
    assert "design-system-raw-hex" in {finding.id for finding in result.findings}


def test_design_system_compliance_flags_screenshot_palette_drift(tmp_path: Path) -> None:
    screenshot = tmp_path / "drift.png"
    Image.new("RGB", (120, 120), "#FF00FF").save(screenshot)
    html = """
    <!doctype html><html><head><style>
    :root {
      --bg: #FFFFFF;
      --surface: #F8FAFC;
      --fg: #0F172A;
      --muted: #64748B;
      --border: #CBD5E1;
      --accent: #FECE14;
      --font-display: Georgia, serif;
      --font-body: Arial, sans-serif;
      --text-base: 16px;
      --radius-md: 8px;
      --focus-ring: 0 0 0 3px rgba(254, 206, 20, 0.35);
      --container-max: 1120px;
    }
    .cta { background: var(--accent); }
    </style></head><body><a class="cta">Start</a></body></html>
    """

    result = lint_design_system_compliance(
        html,
        active_design_system_context=_active_design_context(),
        screenshot_path=screenshot,
    )

    assert "design-system-screenshot-palette-drift" in {finding.id for finding in result.findings}
    assert result.blocks_publish is True
