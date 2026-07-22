"""Craft reference registry.

Maps the `od.craft.requires` slugs declared in a skill's SKILL.md frontmatter to
short, universal craft rules that are injected into the prompt above the skill
body. These are intentionally brand-agnostic: the active design system / brand
wins on token *values* (color, type scale), while craft rules win on the
execution details a brand is usually silent about (rhythm, restraint,
anti-slop). Mirrors open-design's craft-section injection.
"""

from __future__ import annotations

# slug -> concise craft rule (universal design vocabulary, kept in English to
# match the shared craft language; the surrounding header is localized).
_CRAFT_RULES: dict[str, str] = {
    "narrative-clarity": (
        "Narrative clarity: every slide/section advances one clear idea. Lead with the takeaway, "
        "then support it. Cut anything that does not move the argument forward."
    ),
    "slide-rhythm": (
        "Slide rhythm: vary slide density deliberately - alternate dense data slides with breathing-room "
        "statement slides. Keep one dominant focal point per slide; never two competing hero elements."
    ),
    "information-hierarchy": (
        "Information hierarchy: establish a strict 3-level hierarchy (primary / secondary / supporting). "
        "Size, weight, and spacing must encode importance consistently across the whole document."
    ),
    "typographic-rhythm": (
        "Typographic rhythm: lock a modular type scale and a consistent vertical baseline. Line-height, "
        "paragraph spacing, and heading offsets should follow one repeating cadence, not ad-hoc values."
    ),
    "typography": (
        "Typography: choose at most two families with clear roles (display vs text). Tune tracking on large "
        "headings (tighter) and small caps/labels (looser). Never leave default browser type unstyled."
    ),
    "typography-hierarchy": (
        "Typography hierarchy: differentiate heading levels by more than size alone - combine weight, "
        "tracking, and color/opacity so the structure reads even in grayscale."
    ),
    "typography-hierarchy-editorial": (
        "Editorial typography: treat the page like a magazine spread - strong kickers, generous leading on "
        "body copy, pull quotes with real contrast, and intentional asymmetry instead of centered stacks."
    ),
    "color": (
        "Color: derive from the brand/design-system tokens only. Use a restrained palette (one accent, "
        "neutral structure). Ensure text/background contrast meets WCAG AA. No rainbow gradients as slop filler."
    ),
    "anti-ai-slop": (
        "Anti-AI-slop: no lorem ipsum, no generic centered hero + three-card grid, no purple-blue gradient "
        "defaults, no emoji as iconography, no placeholder images. Use real, specific content and intentional layout."
    ),
    "laws-of-ux": (
        "Laws of UX: respect Fitts (large/near targets), Hick (limit choices per step), Jakob (familiar patterns), "
        "and Miller (chunk information). Group related controls; keep primary actions visually dominant."
    ),
    "rtl-and-bidi": (
        "RTL & bidi: when content may be right-to-left, mirror layout direction, alignment, and iconography. "
        "Use logical CSS properties (margin-inline, text-align: start) instead of hard left/right."
    ),
    "pixel-discipline": (
        "Pixel discipline: align everything to an 8px (or 4px) grid. Consistent radii, consistent border widths, "
        "optically centered glyphs. No half-pixel seams or mismatched paddings."
    ),
    "state-coverage": (
        "State coverage: design every interactive element's default, hover, focus, active, disabled, loading, "
        "empty, and error states. Never ship a control that only has a resting state."
    ),
    "animation-discipline": (
        "Animation discipline: motion must be purposeful and fast (150-300ms), eased, and interruptible. "
        "Animate transform/opacity only. Respect prefers-reduced-motion. No gratuitous looping effects."
    ),
    "accessibility-baseline": (
        "Accessibility baseline: semantic HTML, labeled controls, visible focus rings, AA contrast, keyboard "
        "operability, and alt text. Accessibility is a requirement, not an enhancement."
    ),
    "form-validation": (
        "Form validation: validate inline with clear, specific messages near the field. Preserve user input on "
        "error, disable submit only when truly blocked, and confirm success explicitly."
    ),
}


def craft_rule_text(slug: str) -> str | None:
    """Return the craft rule body for a slug, or None if unknown."""
    return _CRAFT_RULES.get(str(slug or "").strip().lower())


def build_craft_reference_block(requires: list[str] | None, *, language: str = "zh") -> str:
    """Assemble the craft reference block for the given requires slugs.

    Returns an empty string when no known craft slugs are present.
    """
    slugs: list[str] = []
    seen: set[str] = set()
    for raw in list(requires or []):
        slug = str(raw or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)

    bullets: list[str] = []
    for slug in slugs:
        text = craft_rule_text(slug)
        if text:
            bullets.append(f"- {text}")
    if not bullets:
        return ""

    if str(language or "").lower().startswith("zh"):
        header = (
            "## 通用工艺基线（Craft）\n\n"
            "以下是凌驾于具体内容之上的通用工艺规则。品牌 / 设计系统决定 token 取值（颜色、字号刻度），"
            "工艺规则决定品牌未规定的执行细节（节奏、克制、反套话）。冲突时 token 取值以品牌为准。"
        )
    else:
        header = (
            "## Craft baseline\n\n"
            "Universal craft rules layered on top of content. The brand / design system wins on token *values* "
            "(color, type scale); these craft rules win on execution details the brand is silent about "
            "(rhythm, restraint, anti-slop). On conflict, brand token values take precedence."
        )
    return f"{header}\n\n" + "\n".join(bullets)
