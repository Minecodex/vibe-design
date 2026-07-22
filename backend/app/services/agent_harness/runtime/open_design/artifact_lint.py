from __future__ import annotations

import re

from .contracts import ArtifactLintFinding

PURPLE_HEXES = (
    "#a855f7", "#9333ea", "#7c3aed", "#6d28d9", "#581c87",
    "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe", "#ede9fe",
    "#6366f1", "#4f46e5", "#4338ca", "#3730a3", "#312e81",
    "#818cf8", "#a5b4fc", "#c7d2fe", "#e0e7ff", "#eef2ff",
)
TRUST_GRADIENT_BLUE = (
    "#3b82f6", "#2563eb", "#1d4ed8", "#1e40af", "#1e3a8a",
    "#60a5fa", "#93c5fd", "#bfdbfe", "#0ea5e9", "#0284c7",
    "#0369a1", "#38bdf8", "#7dd3fc",
)
TRUST_GRADIENT_CYAN = (
    "#06b6d4", "#0891b2", "#0e7490", "#155e75", "#164e63",
    "#22d3ee", "#67e8f9", "#a5f3fc",
)
AI_DEFAULT_INDIGO = ("#6366f1", "#4f46e5", "#4338ca", "#3730a3", "#8b5cf6", "#7c3aed", "#a855f7")
SLOP_EMOJI = ("✨", "🚀", "🎯", "⚡", "🔥", "💡", "📈", "🎨", "🛡️", "🌟", "💪", "🎉", "👋", "🙌", "✅", "⭐", "🏆")
INVENTED_METRIC_PATTERNS = (
    re.compile(r"\b10×\s+(faster|better|easier)\b", re.I),
    re.compile(r"\b100×\s+(faster|better)\b", re.I),
    re.compile(r"\b99\.\d+%\s+uptime\b", re.I),
    re.compile(r"\bzero[- ]downtime\b", re.I),
    re.compile(r"\b3×\s+more\s+(productive|efficient)\b", re.I),
)
FILLER_PATTERNS = (
    re.compile(r"\bfeature\s+(one|two|three|1|2|3)\b", re.I),
    re.compile(r"\blorem\s+ipsum\b", re.I),
    re.compile(r"\bdolor\s+sit\s+amet\b", re.I),
    re.compile(r"\bplaceholder\s+text\b", re.I),
    re.compile(r"\bsample\s+content\b", re.I),
)
HAND_DRAWN_PATTERNS = (
    re.compile(r"\b(hand[- ]drawn|doodle|sketch(?:y)?|scribble|rough illustration)\b", re.I),
)
GENERIC_PERSON_PATTERNS = (
    re.compile(r"\b(smiling|happy)\s+(person|people|team|professional|customer)s?\b", re.I),
    re.compile(r"\bperson\s+(using|holding|looking at)\s+(a\s+)?(laptop|phone|tablet)\b", re.I),
    re.compile(r"\bteam\s+(meeting|collaboration|brainstorming)\b", re.I),
)
SCENERY_PATTERNS = (
    re.compile(r"\b(mountain|forest|ocean|desert|landscape)\s+(at\s+)?(sunset|sunrise|background|hero)\b", re.I),
    re.compile(r"\babstract\s+(waves|blob|gradient)\s+background\b", re.I),
)


def lint_artifact(raw_html: object) -> list[ArtifactLintFinding]:
    if not isinstance(raw_html, str) or not raw_html:
        return []
    html = re.sub(r"<!--[\s\S]*?-->", "", raw_html)
    findings: list[ArtifactLintFinding] = []

    _lint_purple_gradient(html, findings)
    _lint_trust_gradient(html, findings)
    _lint_ai_default_indigo(html, findings)
    _lint_emoji_icon(html, findings)
    _lint_left_accent_card(html, findings)
    _lint_sans_display(html, findings)
    _lint_patterns(html, findings, INVENTED_METRIC_PATTERNS, "invented-metric", "Suspected invented metric: \"{match}\". Anti-slop list says: no numbers without a real source.", "Either remove the claim or replace with a labelled placeholder until the user supplies a real number.")
    _lint_patterns(html, findings, FILLER_PATTERNS, "filler-copy", "Filler copy detected: \"{match}\". Pages should ship with real, brief-derived copy.", "Replace with copy specific to the brief or delete the section entirely.")
    _lint_patterns(html, findings, HAND_DRAWN_PATTERNS, "hand-drawn-illustration", "Generic hand-drawn / doodle illustration language detected: \"{match}\".", "Use a concrete visual system from the skill or remove the generic illustration placeholder.")
    _lint_patterns(html, findings, GENERIC_PERSON_PATTERNS, "generic-person-photo", "Generic smiling-person/team stock-photo language detected: \"{match}\".", "Use a brief-specific visual, local asset, or non-photo composition instead of stock-photo filler.")
    _lint_patterns(html, findings, SCENERY_PATTERNS, "generic-scenery-hero", "Generic scenery/abstract hero background detected: \"{match}\".", "Replace with a product- or brief-specific visual structure.")
    if re.search(r"\.scrollIntoView\s*\(", html):
        findings.append(ArtifactLintFinding("P0", "scroll-into-view", "Element.scrollIntoView() detected — it can yank the host page across iframe boundaries.", "Use scrollTo on the actual scroller instead."))
    _lint_uppercase_tracking(html, findings)
    _lint_external_images(html, findings)
    _lint_raw_hex(html, findings)
    _lint_density(html, findings)
    _lint_static_contrast(html, findings)
    return findings


def _lint_purple_gradient(html: str, findings: list[ArtifactLintFinding]) -> None:
    for hex_value in PURPLE_HEXES:
        match = re.search(r"linear-gradient\([^)]*" + re.escape(hex_value) + r"[^)]*\)", html, re.I)
        if match:
            findings.append(ArtifactLintFinding("P0", "purple-gradient", f"Found a violet/purple gradient using {hex_value} — anti-slop list says no.", "Replace the gradient with a flat surface or a single design-token color.", _clip(match.group(0))))
            return
    match = re.search(r"linear-gradient\([^)]*\b(purple|violet)\b[^)]*\)", html, re.I)
    if match:
        findings.append(ArtifactLintFinding("P0", "purple-gradient", f"Found a \"{match.group(1)}\" keyword inside a gradient — anti-slop.", "Remove the gradient or swap to a single solid color from the active design tokens.", _clip(match.group(0))))


def _lint_trust_gradient(html: str, findings: list[ArtifactLintFinding]) -> None:
    for match in re.finditer(r"linear-gradient\(([^)]*)\)", html, re.I):
        value = match.group(1).lower()
        has_blue = "blue" in value or any(hex_value in value for hex_value in TRUST_GRADIENT_BLUE)
        has_cyan = "cyan" in value or any(hex_value in value for hex_value in TRUST_GRADIENT_CYAN)
        if has_blue and has_cyan:
            findings.append(ArtifactLintFinding("P0", "trust-gradient", "Found a blue→cyan two-stop \"trust\" gradient — anti-slop list says no.", "Replace the gradient with a flat surface or a single design-token color.", _clip(match.group(0))))
            return


def _lint_ai_default_indigo(html: str, findings: list[ArtifactLintFinding]) -> None:
    scoped = _strip_token_blocks(html)
    lower = scoped.lower()
    for hex_value in AI_DEFAULT_INDIGO:
        if hex_value in lower:
            findings.append(ArtifactLintFinding("P0", "ai-default-indigo", f"Found a default LLM accent color ({hex_value}) — this is a common AI design tell.", "Replace with var(--accent) from the active design system, or encode the brief's true accent as --accent.", hex_value))
            return


# ---------------------------------------------------------------------------
# Token-block stripping (ported from open-design lint-artifact.ts)
#
# Removes CSS rule blocks that are pure design-token definitions inside a
# global theme scope (`:root`, `html`, `body`, `[data-theme="..."]`, etc.)
# so that the indigo lint only fires on colors the browser actually renders,
# not on token declarations that the design system overrides downstream via
# var(--accent).
#
# A block is stripped only when ALL THREE conditions hold:
#   1. Every selector in the comma-separated list is a global theme scope.
#   2. Every declaration in the body is token-shaped (--name: value).
#   3. No non-`--accent` token launders an AI-default indigo hex.
# ---------------------------------------------------------------------------

_GLOBAL_THEME_ATTRIBUTES = frozenset({"data-theme", "data-color-scheme", "data-mode"})

_GLOBAL_THEME_SELECTOR_RE = re.compile(
    r"^(?::root|html|body)(?:\[([a-zA-Z-]+)(?:[*^$|~]?=[^\]]*)?\])?$"
)
_BARE_ATTR_SELECTOR_RE = re.compile(
    r"^\[([a-zA-Z-]+)(?:[*^$|~]?=[^\]]*)?\]$"
)


def _is_global_theme_scope_selector(selector: str) -> bool:
    """Check if a single selector targets a global theme scope."""
    m = _GLOBAL_THEME_SELECTOR_RE.match(selector)
    if m:
        attr_name = m.group(1)
        if not attr_name:
            return True  # bare :root / html / body
        return attr_name.lower() in _GLOBAL_THEME_ATTRIBUTES
    m = _BARE_ATTR_SELECTOR_RE.match(selector)
    if m:
        return m.group(1).lower() in _GLOBAL_THEME_ATTRIBUTES
    return False


def _selector_list_is_global_theme_scope(selector: str) -> bool:
    """Check if every selector in a comma-separated list is a global theme scope."""
    parts = [s.strip() for s in selector.split(",") if s.strip()]
    if not parts:
        return False
    return all(_is_global_theme_scope_selector(s) for s in parts)


def _is_token_shaped_declaration(decl: str) -> bool:
    """A declaration is token-shaped if it's a CSS custom property or color-scheme."""
    if re.match(r"^--[\w-]+\s*:", decl):
        return True
    if re.match(r"^color-scheme\s*:", decl, re.I):
        return True
    return False


def _declaration_launders_indigo(decl: str) -> bool:
    """True if a non-`--accent` token carries an AI-default indigo hex value."""
    m = re.match(r"^(--[\w-]+)\s*:\s*(.+)$", decl)
    if not m:
        return False
    token_name = m.group(1)
    token_value = m.group(2)
    if token_name.lower() == "--accent":
        return False  # --accent is the legitimate escape hatch
    value_lower = token_value.lower()
    return any(hex_value in value_lower for hex_value in AI_DEFAULT_INDIGO)


def _strip_token_blocks(html: str) -> str:
    """Strip pure-token global-theme CSS blocks from <style> tags before indigo scan."""
    def _strip_css_block(style_match: re.Match[str]) -> str:
        open_tag = style_match.group(1)
        css = style_match.group(2)
        close_tag = style_match.group(3)
        # Strip CSS comments before structural matching
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", css)
        # Match innermost rule blocks only ([^{}]* not [^}]*)
        def _replace_rule(rule_match: re.Match[str]) -> str:
            selector = (rule_match.group(1) or "").strip()
            body = rule_match.group(2) or ""
            if not _selector_list_is_global_theme_scope(selector):
                return rule_match.group(0)
            decls = [d.strip() for d in body.split(";") if d.strip()]
            if not decls:
                return rule_match.group(0)
            if not all(_is_token_shaped_declaration(d) for d in decls):
                return rule_match.group(0)
            if any(_declaration_launders_indigo(d) for d in decls):
                return rule_match.group(0)
            return ""  # strip this block
        stripped = re.sub(r"([^{}]*)\{([^{}]*)\}", _replace_rule, cleaned)
        return f"{open_tag}{stripped}{close_tag}"

    return re.sub(r"(<style[^>]*>)([\s\S]*?)(</style>)", _strip_css_block, html, flags=re.I)


def _lint_emoji_icon(html: str, findings: list[ArtifactLintFinding]) -> None:
    for emoji in SLOP_EMOJI:
        if emoji not in html:
            continue
        match = re.search(rf"<(?:h[1-6]|button|li|span class=\"[^\"]*icon[^\"]*\")[^>]*>[^<]*{re.escape(emoji)}", html, re.I)
        if match:
            findings.append(ArtifactLintFinding("P0", "emoji-icon", f"Emoji \"{emoji}\" used as a UI icon — anti-slop list says SVG monoline only.", "Replace with a small inline SVG icon or remove the icon entirely.", _clip(match.group(0))))
            return


def _lint_left_accent_card(html: str, findings: list[ArtifactLintFinding]) -> None:
    match = re.search(r"\.[\w-]+\s*\{[^}]*border-left\s*:\s*\d+px\s+solid\s+[^;]+;[^}]*border-radius\s*:\s*[1-9]", html, re.I)
    if match:
        findings.append(ArtifactLintFinding("P0", "left-accent-card", "Rounded card with a coloured left border — the canonical AI-slop card pattern.", "Drop either the border-radius or the border-left.", _clip(match.group(0))))


def _lint_sans_display(html: str, findings: list[ArtifactLintFinding]) -> None:
    match = re.search(r"(?:h1|h2|h3|\.h-?(?:hero|xl|lg|md))[^{}]*\{[^}]*font-family\s*:\s*[\"']?(?:Inter|Roboto|Arial|-apple-system|system-ui|SF\s+Pro)", html, re.I)
    if match:
        findings.append(ArtifactLintFinding("P0", "sans-display", "A heading rule uses Inter / Roboto / system-sans as the display face.", "Use font-family: var(--font-display) on h1/h2/h3 unless the active direction explicitly calls for utility sans.", _clip(match.group(0))))


def _lint_patterns(html: str, findings: list[ArtifactLintFinding], patterns: tuple[re.Pattern[str], ...], id_: str, message: str, fix: str) -> None:
    for pattern in patterns:
        match = pattern.search(html)
        if match:
            findings.append(ArtifactLintFinding("P0", id_, message.format(match=match.group(0)), fix, _clip(match.group(0))))
            return


def _lint_uppercase_tracking(html: str, findings: list[ArtifactLintFinding]) -> None:
    for style in re.findall(r"<style[^>]*>([\s\S]*?)</style>", html, re.I):
        css = re.sub(r"/\*[\s\S]*?\*/", "", style)
        for match in re.finditer(r"([^{}]+)\{([^{}]*text-transform\s*:\s*uppercase[^{}]*)\}", css, re.I):
            body = match.group(2)
            if not _has_adequate_tracking(body):
                findings.append(ArtifactLintFinding("P1", "all-caps-no-tracking", "A selector sets text-transform: uppercase without sufficient letter-spacing (>=0.06em).", "Add letter-spacing: 0.08em to the same rule.", _clip(f"{match.group(1).strip()} {{ {body.strip()} }}")))
                return


def _has_adequate_tracking(body: str) -> bool:
    declarations = _declarations(body)
    ls = declarations.get("letter-spacing")
    if not ls:
        return False
    match = re.search(r"(-?\d*\.?\d+)\s*(em|px|rem)\b", ls, re.I)
    if not match:
        return False
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "em":
        return value >= 0.06
    tracking_px = value * 16 if unit == "rem" else value
    fs = declarations.get("font-size")
    if fs:
        fs_match = re.search(r"(-?\d*\.?\d+)\s*(px|rem)\b", fs, re.I)
        if not fs_match:
            return False
        fs_px = float(fs_match.group(1)) * (16 if fs_match.group(2).lower() == "rem" else 1)
        return fs_px > 0 and tracking_px >= fs_px * 0.06
    return tracking_px >= 1


def _declarations(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in body.split(";"):
        if ":" not in raw:
            continue
        prop, value = raw.split(":", 1)
        prop = prop.strip().lower()
        if prop and not prop.startswith("--"):
            out[prop] = value.strip()
    return out


def _lint_external_images(html: str, findings: list[ArtifactLintFinding]) -> None:
    match = re.search(r"<img[^>]+src=[\"']https?://(?:images\.unsplash\.com|placehold\.co|placekitten\.com|via\.placeholder\.com|picsum\.photos|loremflickr\.com)", html, re.I)
    if match:
        findings.append(ArtifactLintFinding("P1", "external-image", "External placeholder image CDN detected.", "Use a local placeholder or bundled asset instead.", _clip(match.group(0))))


def _lint_raw_hex(html: str, findings: list[ArtifactLintFinding]) -> None:
    style = re.search(r"<style[^>]*>([\s\S]*?)</style>", html, re.I)
    if not style:
        return
    css = re.sub(r":root\s*\{[^}]*\}", "", style.group(1), flags=re.I)
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    if len(hexes) > 12:
        findings.append(ArtifactLintFinding("P1", "raw-hex", f"{len(hexes)} raw hex values found outside :root — design tokens probably were not honored.", "Move repeated colors into design tokens and use var(...)."))


def _lint_density(html: str, findings: list[ArtifactLintFinding]) -> None:
    gradient_count = len(re.findall(r"\b(?:linear|radial|conic)-gradient\s*\(", html, re.I))
    if gradient_count > 3:
        findings.append(ArtifactLintFinding("P1", "excessive-gradients", f"{gradient_count} CSS gradients found.", "Reduce gradients to one intentional accent surface or replace with tokenized flat surfaces."))
    icon_count = len(re.findall(r"<svg\b|class=[\"'][^\"']*(?:\bicon\b|icon-)[^\"']*[\"']", html, re.I))
    if icon_count > 10:
        findings.append(ArtifactLintFinding("P2", "excessive-icons", f"{icon_count} icon-like elements found.", "Remove decorative icons that do not carry information."))


def _lint_static_contrast(html: str, findings: list[ArtifactLintFinding]) -> None:
    for style in re.findall(r"<style[^>]*>([\s\S]*?)</style>", html, re.I):
        css = re.sub(r"/\*[\s\S]*?\*/", "", style)
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            declarations = _declarations(match.group(2))
            fg = _parse_hex_color(declarations.get("color"))
            bg = _parse_hex_color(declarations.get("background") or declarations.get("background-color"))
            if fg is None or bg is None:
                continue
            ratio = _contrast_ratio(fg, bg)
            if ratio < 3.0:
                findings.append(ArtifactLintFinding("P2", "static-low-contrast", f"Static CSS contrast appears low ({ratio:.2f}:1).", "Increase foreground/background contrast or use validated design tokens.", _clip(f"{match.group(1).strip()} {{ {match.group(2).strip()} }}")))
                return


def _parse_hex_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.search(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", value)
    if not match:
        return None
    raw = match.group(1)
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        normalized = value / 255
        return normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _clip(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:180]
