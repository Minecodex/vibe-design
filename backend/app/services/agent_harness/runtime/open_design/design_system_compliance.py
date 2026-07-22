from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.services.agent_harness.capabilities.design_systems.token_contract import (
    HEX_RE,
    TOKEN_DECL_RE,
    extract_root_block,
    parse_token_declarations,
    strip_css_comments,
)

from .contracts import ArtifactLintFinding

CORE_TOKENS = frozenset(
    {
        "--accent",
        "--bg",
        "--surface",
        "--fg",
        "--muted",
        "--border",
        "--font-display",
        "--font-body",
        "--focus-ring",
    }
)
CORE_TOKEN_PREFIXES = ("--text-", "--radius-", "--container-")


@dataclass(frozen=True, slots=True)
class DesignSystemComplianceResult:
    findings: list[ArtifactLintFinding]
    active_token_count: int
    artifact_token_count: int
    checked: bool
    reason: str | None = None

    @property
    def blocks_publish(self) -> bool:
        return any(finding.severity == "P0" for finding in self.findings)

    def to_payload(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "reason": self.reason,
            "blocks_publish": self.blocks_publish,
            "active_token_count": self.active_token_count,
            "artifact_token_count": self.artifact_token_count,
            "findings": [finding.to_payload() for finding in self.findings],
            "p0_count": sum(1 for finding in self.findings if finding.severity == "P0"),
            "p1_count": sum(1 for finding in self.findings if finding.severity == "P1"),
            "p2_count": sum(1 for finding in self.findings if finding.severity == "P2"),
        }


def lint_design_system_compliance(
    raw_html: object,
    *,
    active_design_system_context: dict[str, Any] | None,
    screenshot_path: str | Path | None = None,
) -> DesignSystemComplianceResult:
    if not isinstance(raw_html, str) or not raw_html:
        return DesignSystemComplianceResult([], 0, 0, checked=False, reason="empty_artifact")
    if not isinstance(active_design_system_context, dict):
        return DesignSystemComplianceResult([], 0, 0, checked=False, reason="missing_active_design_system_context")
    tokens_css = str(active_design_system_context.get("tokens_css") or "")
    active_root = extract_root_block(tokens_css)
    if not active_root:
        return DesignSystemComplianceResult([], 0, 0, checked=False, reason="missing_active_tokens_root")

    active_declarations = parse_token_declarations(active_root)
    artifact_root = _first_style_root_block(raw_html)
    artifact_declarations = parse_token_declarations(artifact_root)
    findings: list[ArtifactLintFinding] = []

    if artifact_root is None:
        findings.append(
            ArtifactLintFinding(
                "P0",
                "design-system-root-missing",
                "The artifact does not paste the active design system's unscoped :root token block in its first <style>.",
                "Paste the active tokens.css :root block verbatim into the first <style> before component rules.",
            )
        )
    else:
        _lint_root_contract(active_declarations, artifact_declarations, findings)

    raw_hexes = sorted(set(HEX_RE.findall(strip_css_comments(_strip_style_root_blocks(raw_html)))))
    if raw_hexes:
        findings.append(
            ArtifactLintFinding(
                "P0",
                "design-system-raw-hex",
                "Raw hex colors appear outside the design-system :root token block: " + ", ".join(raw_hexes[:12]),
                "Replace rendered colors with var(--*) references from the active tokens.css contract.",
                ", ".join(raw_hexes[:6]),
            )
        )

    active_palette = set(_palette_from_declarations(active_declarations))
    artifact_root_palette = set(_palette_from_declarations(artifact_declarations))
    if active_palette and artifact_root_palette:
        unexpected = sorted(artifact_root_palette - active_palette)
        if unexpected:
            findings.append(
                ArtifactLintFinding(
                    "P0",
                    "design-system-palette-drift",
                    "The artifact root declares colors outside the active design-system palette: " + ", ".join(unexpected[:12]),
                    "Use the active tokens.css values exactly; do not invent replacement palette values.",
                    ", ".join(unexpected[:6]),
                )
            )

    if screenshot_path is not None:
        findings.extend(_lint_screenshot_palette_drift(screenshot_path, active_palette=active_palette))

    return DesignSystemComplianceResult(
        findings=findings,
        active_token_count=len(active_declarations),
        artifact_token_count=len(artifact_declarations),
        checked=True,
    )


def compliance_context_from_runtime_contract(runtime_contract: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(runtime_contract, dict):
        return None
    ctx = runtime_contract.get("active_design_system_context")
    if isinstance(ctx, dict) and str(ctx.get("kind") or "") == "active_design_system_context":
        return ctx
    return None


def _lint_root_contract(
    active_declarations: dict[str, str],
    artifact_declarations: dict[str, str],
    findings: list[ArtifactLintFinding],
) -> None:
    missing = [token for token in sorted(active_declarations) if token not in artifact_declarations]
    extra = [token for token in sorted(artifact_declarations) if token not in active_declarations]
    changed_core: list[str] = []
    changed_other: list[str] = []
    for token, active_value in sorted(active_declarations.items()):
        if token not in artifact_declarations:
            continue
        artifact_value = artifact_declarations[token]
        if _normalize_token_value(active_value) == _normalize_token_value(artifact_value):
            continue
        if token in CORE_TOKENS or token.startswith(CORE_TOKEN_PREFIXES):
            changed_core.append(token)
        else:
            changed_other.append(token)

    if missing:
        findings.append(
            ArtifactLintFinding(
                "P0",
                "design-system-token-missing",
                "The artifact :root is missing active design-system tokens: " + ", ".join(missing[:16]),
                "Paste the active tokens.css :root block verbatim.",
                ", ".join(missing[:8]),
            )
        )
    if changed_core:
        findings.append(
            ArtifactLintFinding(
                "P0",
                "design-system-core-token-modified",
                "Core design-system token values were redefined: " + ", ".join(changed_core[:16]),
                "Restore these token values from active tokens.css exactly.",
                ", ".join(changed_core[:8]),
            )
        )
    if extra:
        findings.append(
            ArtifactLintFinding(
                "P1",
                "design-system-token-invented",
                "The artifact invents tokens that are not in active tokens.css: " + ", ".join(extra[:16]),
                "Remove invented root tokens or add them through the design-system asset bundle.",
                ", ".join(extra[:8]),
            )
        )
    if changed_other:
        findings.append(
            ArtifactLintFinding(
                "P1",
                "design-system-token-modified",
                "Non-core design-system token values were redefined: " + ", ".join(changed_other[:16]),
                "Restore token values from active tokens.css unless the bundle itself is updated.",
                ", ".join(changed_other[:8]),
            )
        )


def _first_style_root_block(html: str) -> str | None:
    style_match = re.search(r"<style\b[^>]*>(?P<css>[\s\S]*?)</style>", str(html or ""), re.IGNORECASE)
    if not style_match:
        return None
    return extract_root_block(style_match.group("css"))


def _strip_style_root_blocks(html: str) -> str:
    def replace_style(match: re.Match[str]) -> str:
        stripped_css = re.sub(r":root\s*\{[\s\S]*?\}", "", match.group(2), flags=re.IGNORECASE)
        return f"{match.group(1)}{stripped_css}{match.group(3)}"

    return re.sub(r"(<style\b[^>]*>)([\s\S]*?)(</style>)", replace_style, str(html or ""), flags=re.IGNORECASE)


def _normalize_token_value(value: str) -> str:
    return re.sub(r"\s+", " ", strip_css_comments(value).strip()).lower()


def _palette_from_declarations(declarations: dict[str, str]) -> list[str]:
    colors: list[str] = []
    seen: set[str] = set()
    for value in declarations.values():
        for match in HEX_RE.findall(value):
            color = match.upper()
            if color in seen:
                continue
            seen.add(color)
            colors.append(color)
    return colors


def _lint_screenshot_palette_drift(
    screenshot_path: str | Path,
    *,
    active_palette: set[str],
) -> list[ArtifactLintFinding]:
    if not active_palette:
        return []
    active_rgb = [_hex_to_rgb(color) for color in active_palette if _hex_to_rgb(color) is not None]
    if not active_rgb:
        return []
    try:
        image = Image.open(Path(screenshot_path)).convert("RGBA")
    except Exception:
        return [
            ArtifactLintFinding(
                "P2",
                "design-system-screenshot-unavailable",
                "Screenshot palette drift check could not read the rendered image.",
                "Capture artifact evidence again, then rerun quality review.",
            )
        ]

    image.thumbnail((160, 160))
    pixels = list(image.getdata())
    sampled: list[tuple[int, int, int]] = []
    for red, green, blue, alpha in pixels:
        if alpha < 32:
            continue
        if _is_near_neutral(red, green, blue):
            continue
        sampled.append((red, green, blue))
    if len(sampled) < 80:
        return []

    far_pixels = [rgb for rgb in sampled if _nearest_distance(rgb, active_rgb) > 58]
    ratio = len(far_pixels) / max(1, len(sampled))
    if ratio < 0.28:
        return []
    dominant = _dominant_quantized_colors(far_pixels)
    severity = "P0" if ratio >= 0.45 else "P1"
    return [
        ArtifactLintFinding(
            severity,
            "design-system-screenshot-palette-drift",
            f"Rendered screenshot colors visibly drift from the active design-system palette ({ratio:.0%} of chromatic sampled pixels are off-palette).",
            "Bring CTA, links, focus, and prominent chromatic surfaces back to active tokens; avoid introducing a new visual palette.",
            ", ".join(dominant[:8]) if dominant else None,
        )
    ]


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", str(value or "").strip())
    if not match:
        return None
    raw = match.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _nearest_distance(rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> float:
    return min(_color_distance(rgb, candidate) for candidate in palette)


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _is_near_neutral(red: int, green: int, blue: int) -> bool:
    spread = max(red, green, blue) - min(red, green, blue)
    return spread <= 18 or (red > 235 and green > 235 and blue > 235) or (red < 28 and green < 28 and blue < 28)


def _dominant_quantized_colors(pixels: list[tuple[int, int, int]]) -> list[str]:
    buckets: dict[tuple[int, int, int], int] = {}
    for red, green, blue in pixels:
        key = (round(red / 16) * 16, round(green / 16) * 16, round(blue / 16) * 16)
        buckets[key] = buckets.get(key, 0) + 1
    colors: list[str] = []
    for (red, green, blue), _count in sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:8]:
        colors.append(f"#{max(0, min(255, red)):02X}{max(0, min(255, green)):02X}{max(0, min(255, blue)):02X}")
    return colors
