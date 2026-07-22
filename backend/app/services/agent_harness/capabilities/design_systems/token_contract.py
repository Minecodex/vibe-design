"""Token contract health checks for Home Harness design-system bundles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .token_schema import TOKEN_SCHEMA, TOKEN_SCHEMA_NAMES, unknown_token_names


TOKEN_DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);")
TOKEN_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
ROOT_BLOCK_RE = re.compile(r":root\s*\{(?P<body>.*?)\}", re.IGNORECASE | re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

CONFLICT_COLOR_LABEL_RE = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s*)?(?:\*\*)?(Primary|Accent|Button[s]?|CTA)(?:\*\*)?\s*[:：][^\n#]*(#[0-9a-fA-F]{6})",
    re.IGNORECASE,
)


@dataclass(slots=True)
class DesignSystemHealth:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    token_report: dict[str, Any] = field(default_factory=dict)
    has_tokens: bool = False
    has_components_manifest: bool = False
    has_fixture: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "token_report": dict(self.token_report),
            "has_tokens": self.has_tokens,
            "has_components_manifest": self.has_components_manifest,
            "has_fixture": self.has_fixture,
        }


def evaluate_design_system_health(
    *,
    design_system_id: str,
    design_md: str | None,
    tokens_css: str | None,
    components_html: str | None,
    components_manifest: str | None,
) -> DesignSystemHealth:
    errors: list[str] = []
    warnings: list[str] = []
    tokens_text = str(tokens_css or "")
    design_text = str(design_md or "")
    fixture_text = str(components_html or "")
    manifest_text = str(components_manifest or "")

    root_block = extract_root_block(tokens_text)
    declarations = parse_token_declarations(root_block or tokens_text)
    token_names = set(declarations)
    token_refs = sorted(set(TOKEN_REF_RE.findall("\n".join([
        strip_css_comments(tokens_text),
        strip_html_style_comments(fixture_text),
        manifest_text,
    ]))))
    unresolved_refs = [token for token in token_refs if token not in token_names]

    if not tokens_text.strip():
        errors.append("tokens.css is required")
    elif root_block is None:
        errors.append("tokens.css must contain an unscoped :root { ... } token block")

    missing_schema = sorted(token for token in TOKEN_SCHEMA_NAMES if token not in token_names)
    if missing_schema:
        errors.append("tokens.css missing TOKEN_SCHEMA tokens: " + ", ".join(missing_schema))
    unknown_schema = unknown_token_names(design_system_id, token_names)
    if unknown_schema:
        errors.append(
            "tokens.css declares non-schema tokens: "
            + ", ".join(unknown_schema)
            + f" (add to BRAND_EXTENSIONS[{design_system_id!r}] only for reviewed brand-specific extensions)"
        )

    if unresolved_refs:
        errors.append("Unresolved token references: " + ", ".join(unresolved_refs))

    accent_hex = _first_hex(str(declarations.get("--accent") or ""))
    if accent_hex:
        conflicts = _design_color_conflicts(design_text, accent_hex)
        for label, color in conflicts:
            errors.append(
                f"DESIGN.md {label} color {color} conflicts with tokens.css --accent {accent_hex}"
            )

    rootless_tokens_css = tokens_text.replace(root_block or "", "", 1) if root_block else tokens_text
    raw_hex_outside_root = sorted(set(HEX_RE.findall(strip_css_comments(rootless_tokens_css))))
    fixture_raw_hex = sorted(set(HEX_RE.findall(strip_css_comments(_strip_style_root_blocks(fixture_text)))))
    if raw_hex_outside_root:
        warnings.append("tokens.css has raw hex outside :root: " + ", ".join(raw_hex_outside_root[:12]))
    if fixture_raw_hex:
        warnings.append("components.html has raw hex outside :root: " + ", ".join(fixture_raw_hex[:12]))

    accent_use_count = len(re.findall(r"var\(\s*--accent\b", fixture_text))
    if accent_use_count > 30:
        errors.append(f"components.html overuses --accent ({accent_use_count} references); reserve accent for CTA/focus/emphasis")
    elif accent_use_count > 12:
        warnings.append(f"components.html uses --accent {accent_use_count} times; check accent discipline")

    token_report = {
        "root_present": root_block is not None,
        "contract": "TOKEN_SCHEMA",
        "schema_token_count": len(TOKEN_SCHEMA),
        "declared_count": len(token_names),
        "declared_tokens": sorted(token_names),
        "missing_schema_tokens": missing_schema,
        "non_schema_tokens": unknown_schema,
        "referenced_tokens": token_refs,
        "unresolved_references": unresolved_refs,
        "accent": accent_hex,
        "palette": extract_palette_from_tokens(tokens_text),
        "raw_hex_outside_root": raw_hex_outside_root,
        "fixture_raw_hex": fixture_raw_hex,
        "accent_reference_count": accent_use_count,
    }
    return DesignSystemHealth(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        token_report=token_report,
        has_tokens=bool(tokens_text.strip()),
        has_components_manifest=bool(manifest_text.strip()),
        has_fixture=bool(fixture_text.strip()),
    )


def extract_root_block(tokens_css: str | None) -> str | None:
    matches = list(ROOT_BLOCK_RE.finditer(str(tokens_css or "")))
    if not matches:
        return None
    best = max(
        matches,
        key=lambda match: len(TOKEN_DECL_RE.findall(strip_css_comments(match.group("body")))),
    )
    return best.group(0)


def parse_token_declarations(css_text: str | None) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for token, value in TOKEN_DECL_RE.findall(strip_css_comments(css_text)):
        declarations[token] = value.strip()
    return declarations


def strip_css_comments(css_text: str | None) -> str:
    return CSS_COMMENT_RE.sub("", str(css_text or ""))


def strip_html_style_comments(html_text: str | None) -> str:
    return CSS_COMMENT_RE.sub("", str(html_text or ""))


def extract_palette_from_tokens(tokens_css: str | None, *, max_colors: int = 6) -> list[str]:
    declarations = parse_token_declarations(extract_root_block(tokens_css) or tokens_css)
    priority = [
        "--bg",
        "--surface",
        "--accent",
        "--fg",
        "--muted",
        "--border",
        "--accent-on",
    ]
    colors: list[str] = []
    seen: set[str] = set()
    for token in priority:
        color = _first_hex(str(declarations.get(token) or ""))
        if color and color not in seen:
            colors.append(color)
            seen.add(color)
    for value in declarations.values():
        for match in HEX_RE.findall(str(value)):
            color = match.upper()
            if color in seen:
                continue
            colors.append(color)
            seen.add(color)
            if len(colors) >= max_colors:
                return colors
    return colors


def _first_hex(value: str) -> str | None:
    match = HEX_RE.search(str(value or ""))
    return match.group(0).upper() if match else None


def _design_color_conflicts(design_md: str, accent_hex: str) -> list[tuple[str, str]]:
    conflicts: list[tuple[str, str]] = []
    normalized_accent = accent_hex.upper()
    for match in CONFLICT_COLOR_LABEL_RE.finditer(design_md):
        label = str(match.group(1) or "").strip()
        color = str(match.group(2) or "").upper()
        if color != normalized_accent:
            conflicts.append((label, color))
    return conflicts


def _strip_style_root_blocks(html: str) -> str:
    return ROOT_BLOCK_RE.sub("", str(html or ""))
