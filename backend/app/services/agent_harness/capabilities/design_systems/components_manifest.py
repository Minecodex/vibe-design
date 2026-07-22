"""Open-Design components.manifest helpers for Home Harness bundles."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

from .token_contract import TOKEN_REF_RE, parse_token_declarations, strip_css_comments

COMPONENTS_MANIFEST_SCHEMA_VERSION = 1

_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_CSS_SELECTOR_RE = re.compile(r"([^{}]+)\{")
_ROOT_BLOCK_RE = re.compile(r":root(?:\[[^\]]+\])?\s*\{[\s\S]*?\}", re.IGNORECASE)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_COLOR_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(|color-mix\(", re.IGNORECASE)
_PX_LITERAL_RE = re.compile(r"\b\d+(?:\.\d+)?px\b", re.IGNORECASE)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;{}]+);", re.IGNORECASE)


class ComponentHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: set[str] = set()
        self.classes: set[str] = set()
        self.title: str | None = None
        self.description: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        self.elements.add(normalized)
        if normalized == "title":
            self._in_title = True
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        class_value = attr_map.get("class")
        if class_value:
            self.classes.update(part for part in class_value.split() if part)
        if normalized == "meta" and str(attr_map.get("name") or "").lower() == "description":
            content = str(attr_map.get("content") or "").strip()
            if content:
                self.description = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            title = "".join(self._title_parts).strip()
            if title:
                self.title = title

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def extract_components_manifest(
    *,
    brand_id: str,
    fixture_html: str | None,
    tokens_css: str | None = None,
) -> dict[str, Any] | None:
    html = str(fixture_html or "")
    if not html.strip():
        return None
    parser = ComponentHtmlParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    style_blocks = [match.group(1).strip() for match in _STYLE_BLOCK_RE.finditer(html)]
    css = "\n\n".join(style_blocks)
    css_without_comments = strip_css_comments(css)
    selectors = _extract_css_selectors(css)
    selector_refs = _extract_selector_token_references(css_without_comments)
    classes = sorted(parser.classes)
    elements = sorted(parser.elements)
    declared = sorted(parse_token_declarations(tokens_css or _first_root_body(css) or ""))
    referenced = sorted(set(TOKEN_REF_RE.findall(strip_css_comments(html))))
    manifest = {
        "schemaVersion": COMPONENTS_MANIFEST_SCHEMA_VERSION,
        "brandId": brand_id,
        "source": {"componentsHtml": "components.html", **({"tokensCss": "tokens.css"} if tokens_css else {})},
        "fixture": {
            **({"title": parser.title} if parser.title else {}),
            **({"description": parser.description} if parser.description else {}),
            "styleBlockCount": len(style_blocks),
            "selectorCount": len(selectors),
            "classCount": len(classes),
            "elementCount": len(elements),
        },
        "tokens": {
            "declared": declared,
            "referenced": referenced,
            "unusedDeclared": [token for token in declared if token not in referenced],
            "undeclaredReferenced": [] if not declared else [token for token in referenced if token not in declared],
        },
        "selectors": selectors,
        "classes": classes,
        "elements": elements,
        "groups": [_build_group(definition, selectors, selector_refs, classes, elements, referenced) for definition in _GROUPS],
        "literals": _count_literals(_strip_root_blocks(strip_css_comments(css))),
    }
    return manifest


def summarize_components_manifest_for_prompt(manifest: dict[str, Any]) -> str | None:
    if not isinstance(manifest, dict):
        return None
    brand_id = str(manifest.get("brandId") or "").strip()
    schema_version = manifest.get("schemaVersion", COMPONENTS_MANIFEST_SCHEMA_VERSION)
    fixture = manifest.get("fixture") if isinstance(manifest.get("fixture"), dict) else {}
    tokens = manifest.get("tokens") if isinstance(manifest.get("tokens"), dict) else {}
    groups = manifest.get("groups") if isinstance(manifest.get("groups"), list) else []
    present_groups: list[str] = []
    for group in groups:
        if not isinstance(group, dict) or not group.get("present"):
            continue
        label = str(group.get("label") or group.get("id") or "Group").strip()
        selectors = ", ".join(_string_items(group.get("selectors"))[:8]) or "none"
        token_refs = ", ".join(_string_items(group.get("tokenReferences"))[:10]) or "none"
        present_groups.append(f"- {label}: selectors {selectors}; tokens {token_refs}")
    return "\n".join(
        [
            f"components.manifest schema v{schema_version} for {brand_id}",
            (
                f"Fixture: {int(fixture.get('selectorCount') or 0)} selectors, "
                f"{int(fixture.get('classCount') or 0)} classes, "
                f"{len(_string_items(tokens.get('declared')))} declared tokens, "
                f"{len(_string_items(tokens.get('referenced')))} referenced tokens."
            ),
            "Available component groups:",
            *(present_groups or ["- none detected"]),
        ]
    ).strip()


def summarize_components_manifest_json(raw: str | None, *, system_id: str) -> str | None:
    if not str(raw or "").strip():
        return None
    try:
        data = json.loads(str(raw))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "schemaVersion" not in data:
        data = _normalize_legacy_manifest(data, system_id=system_id)
    return summarize_components_manifest_for_prompt(data)


def _normalize_legacy_manifest(data: dict[str, Any], *, system_id: str) -> dict[str, Any]:
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    fixture = data.get("fixture") if isinstance(data.get("fixture"), dict) else {}
    return {
        "schemaVersion": COMPONENTS_MANIFEST_SCHEMA_VERSION,
        "brandId": data.get("brandId") or system_id,
        "source": {"componentsHtml": "components.html", "tokensCss": "tokens.css"},
        "fixture": {
            "title": fixture.get("title"),
            "description": fixture.get("description"),
            "styleBlockCount": int(fixture.get("styleBlockCount") or 0),
            "selectorCount": int(fixture.get("selectorCount") or len(_string_items(data.get("selectors")))),
            "classCount": int(fixture.get("classCount") or len(_string_items(data.get("classes")))),
            "elementCount": int(fixture.get("elementCount") or len(_string_items(data.get("elements")))),
        },
        "tokens": {
            "declared": _string_items(tokens.get("declared")),
            "referenced": _string_items(tokens.get("referenced")),
            "unusedDeclared": _string_items(tokens.get("unusedDeclared")),
            "undeclaredReferenced": _string_items(tokens.get("undeclaredReferenced")),
        },
        "selectors": _string_items(data.get("selectors")),
        "classes": _string_items(data.get("classes")),
        "elements": _string_items(data.get("elements")),
        "groups": data.get("groups") if isinstance(data.get("groups"), list) else [],
        "literals": data.get("literals") if isinstance(data.get("literals"), dict) else {"colorExpressions": 0, "pixelValues": 0, "hardcodedFontFamilies": 0},
    }


def _extract_css_selectors(css: str) -> list[str]:
    selectors: set[str] = set()
    for match in _CSS_SELECTOR_RE.finditer(css):
        raw = match.group(1).strip()
        if not raw or raw.startswith("@"):
            continue
        for part in raw.split(","):
            selector = " ".join(part.strip().split())
            if selector and not selector.startswith("@"):
                selectors.add(selector)
    return sorted(selectors)


def _extract_selector_token_references(css: str) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, re.DOTALL):
        body_refs = sorted(set(TOKEN_REF_RE.findall(match.group(2))))
        for part in match.group(1).split(","):
            selector = " ".join(part.strip().split())
            if selector:
                refs[selector] = body_refs
    return refs


def _build_group(
    definition: dict[str, Any],
    selectors: list[str],
    selector_refs: dict[str, list[str]],
    classes: list[str],
    elements: list[str],
    referenced_tokens: list[str],
) -> dict[str, Any]:
    group_selectors = [item for item in selectors if any(pattern.search(item) for pattern in definition["selector"])]
    group_classes = [item for item in classes if any(pattern.search(item) for pattern in definition["class"])]
    group_elements = [item for item in elements if any(pattern.search(item) for pattern in definition["element"])]
    group_refs = sorted(
        {
            ref
            for selector in group_selectors
            for ref in selector_refs.get(selector, [])
            if ref in referenced_tokens
        }
    )
    return {
        "id": definition["id"],
        "label": definition["label"],
        "present": bool(group_selectors or group_classes or group_elements),
        "selectors": group_selectors,
        "classes": group_classes,
        "elements": group_elements,
        "tokenReferences": group_refs,
    }


def _first_root_body(css: str) -> str | None:
    match = re.search(r":root\s*\{(?P<body>[\s\S]*?)\}", css, re.IGNORECASE)
    return match.group("body") if match else None


def _strip_root_blocks(css: str) -> str:
    return _ROOT_BLOCK_RE.sub("", css)


def _count_literals(css: str) -> dict[str, int]:
    font_values = [
        value.strip()
        for value in _FONT_FAMILY_RE.findall(css)
        if "var(" not in value and value.strip()
    ]
    return {
        "colorExpressions": len(_COLOR_LITERAL_RE.findall(css)),
        "pixelValues": len(_PX_LITERAL_RE.findall(css)),
        "hardcodedFontFamilies": len(font_values),
    }


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


_GROUPS = [
    {
        "id": "buttons",
        "label": "Buttons and calls to action",
        "selector": [re.compile(r"\bbutton\b", re.I), re.compile(r"\.btn(?:\b|[-_:])", re.I), re.compile(r"\[type=[\"']?(?:button|submit|reset)", re.I)],
        "class": [re.compile(r"^btn(?:$|-)", re.I), re.compile(r"button", re.I), re.compile(r"cta", re.I)],
        "element": [re.compile(r"^button$", re.I)],
    },
    {
        "id": "inputs",
        "label": "Form fields and controls",
        "selector": [re.compile(r"\binput\b", re.I), re.compile(r"\btextarea\b", re.I), re.compile(r"\bselect\b", re.I), re.compile(r"\.field(?:\b|[-_:])", re.I), re.compile(r"\blabel\b", re.I)],
        "class": [re.compile(r"^field(?:$|-)", re.I), re.compile(r"input", re.I), re.compile(r"control", re.I), re.compile(r"form", re.I)],
        "element": [re.compile(r"^(input|textarea|select|label|form)$", re.I)],
    },
    {
        "id": "cards",
        "label": "Cards and panels",
        "selector": [re.compile(r"\.card(?:\b|[-_:])", re.I), re.compile(r"\.panel(?:\b|[-_:])", re.I), re.compile(r"\.tile(?:\b|[-_:])", re.I)],
        "class": [re.compile(r"^card(?:$|-)", re.I), re.compile(r"^panel(?:$|-)", re.I), re.compile(r"^tile(?:$|-)", re.I)],
        "element": [],
    },
    {
        "id": "badges",
        "label": "Badges, chips, and status labels",
        "selector": [re.compile(r"\.badge(?:\b|[-_:])", re.I), re.compile(r"\.chip(?:\b|[-_:])", re.I), re.compile(r"\.tag(?:\b|[-_:])", re.I), re.compile(r"\.pill(?:\b|[-_:])", re.I)],
        "class": [re.compile(r"^badge(?:$|-)", re.I), re.compile(r"^chip(?:$|-)", re.I), re.compile(r"^tag(?:$|-)", re.I), re.compile(r"^pill(?:$|-)", re.I), re.compile(r"status", re.I)],
        "element": [],
    },
    {
        "id": "links",
        "label": "Links and inline actions",
        "selector": [re.compile(r"\ba\b", re.I), re.compile(r"\.link(?:\b|[-_:])", re.I)],
        "class": [re.compile(r"^link(?:$|-)", re.I)],
        "element": [re.compile(r"^a$", re.I)],
    },
    {
        "id": "keyboard",
        "label": "Keyboard hints",
        "selector": [re.compile(r"\bkbd\b", re.I), re.compile(r"\.kbd(?:\b|[-_:])", re.I)],
        "class": [re.compile(r"^kbd(?:$|-)", re.I), re.compile(r"keyboard", re.I), re.compile(r"shortcut", re.I)],
        "element": [re.compile(r"^kbd$", re.I)],
    },
    {
        "id": "icons",
        "label": "Icon slots",
        "selector": [re.compile(r"\.icon(?:\b|[-_:])", re.I), re.compile(r"\[aria-hidden=[\"']true[\"']\]", re.I)],
        "class": [re.compile(r"^icon(?:$|-)", re.I)],
        "element": [re.compile(r"^svg$", re.I)],
    },
    {
        "id": "typography",
        "label": "Typography scale and text utilities",
        "selector": [re.compile(r"\bh[1-6]\b", re.I), re.compile(r"\.lead(?:\b|[-_:])", re.I), re.compile(r"\.eyebrow(?:\b|[-_:])", re.I), re.compile(r"\.body-(?:muted|sm|small)\b", re.I)],
        "class": [re.compile(r"^lead$", re.I), re.compile(r"^eyebrow$", re.I), re.compile(r"^body-(?:muted|sm|small)$", re.I), re.compile(r"caption", re.I)],
        "element": [re.compile(r"^h[1-6]$", re.I), re.compile(r"^p$", re.I)],
    },
    {
        "id": "layout",
        "label": "Layout primitives",
        "selector": [re.compile(r"\.container(?:\b|[-_:])", re.I), re.compile(r"\.stack-\d+\b", re.I), re.compile(r"\.row-(?:between|center|start|end)\b", re.I), re.compile(r"\bsection\b", re.I), re.compile(r"\bmain\b", re.I), re.compile(r"\bnav\b", re.I)],
        "class": [re.compile(r"^container$", re.I), re.compile(r"^stack-\d+$", re.I), re.compile(r"^row-(?:between|center|start|end)$", re.I), re.compile(r"grid", re.I), re.compile(r"layout", re.I)],
        "element": [re.compile(r"^(main|section|nav|header|footer)$", re.I)],
    },
]
