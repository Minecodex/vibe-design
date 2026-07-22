from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from html import escape
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_harness.capabilities.design_systems.token_contract import (
    evaluate_design_system_health,
    extract_palette_from_tokens,
    parse_token_declarations,
)
from app.services.agent_harness.capabilities.design_systems.components_manifest import extract_components_manifest
from app.services.agent_harness.capabilities.design_systems.token_schema import (
    TOKEN_SCHEMA,
    fallback_token_value as schema_fallback_token_value,
)

CSS_FILE_RE = re.compile(r"\.(?:css|scss|sass|less|tsx|ts|jsx|js|vue|svelte|html?)$", re.IGNORECASE)
TOKEN_DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);")
TOKEN_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

STANDARD_TOKEN_ALIASES = {
    "--bg": ("--bg", "--background", "--color-bg", "--color-background"),
    "--surface": ("--surface", "--card", "--panel", "--color-surface"),
    "--fg": ("--fg", "--foreground", "--text", "--color-text", "--color-fg"),
    "--muted": ("--muted", "--muted-foreground", "--color-muted"),
    "--border": ("--border", "--color-border"),
    "--accent": ("--accent", "--primary", "--brand", "--color-primary", "--color-accent"),
    "--font-display": ("--font-display", "--font-heading", "--font-sans"),
    "--font-body": ("--font-body", "--font-sans"),
    "--text-base": ("--text-base", "--font-size-base"),
    "--radius-md": ("--radius-md", "--radius", "--border-radius"),
    "--focus-ring": ("--focus-ring", "--ring", "--focus"),
    "--container-max": ("--container-max", "--container", "--max-width"),
}
for spec in TOKEN_SCHEMA:
    STANDARD_TOKEN_ALIASES.setdefault(spec.name, (spec.name,))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a local project as a Home Harness design-system asset bundle.")
    parser.add_argument("source", type=Path, help="Local project directory to scan.")
    parser.add_argument("--id", required=True, help="Design system id, e.g. acme-dashboard.")
    parser.add_argument("--name", help="Display name. Defaults to title-cased id.")
    parser.add_argument("--category", default="Imported", help="Catalog category.")
    parser.add_argument("--description", default="Imported local design system.", help="Short description.")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("backend/app/services/agent_harness/capabilities/design_systems"),
        help="Destination design_systems directory.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing destination directory.")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"source directory does not exist: {source}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.id):
        raise SystemExit("--id must match [A-Za-z0-9][A-Za-z0-9_-]*")

    out_dir = (args.out_root / args.id).resolve()
    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"destination already exists: {out_dir}; pass --force to replace")
        shutil.rmtree(out_dir)
    (out_dir / "source").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(exist_ok=True)
    (out_dir / "fonts").mkdir(exist_ok=True)
    (out_dir / "preview").mkdir(exist_ok=True)

    scanned = scan_project(source)
    tokens_css = build_tokens_css(scanned["tokens"])
    design_md = build_design_md(
        design_system_id=args.id,
        name=args.name or title_from_id(args.id),
        category=args.category,
        description=args.description,
        palette=extract_palette_from_tokens(tokens_css),
        source=source,
        scanned_files=scanned["file_count"],
    )
    usage_md = build_usage_md()
    components_html = build_components_html(args.name or title_from_id(args.id), tokens_css, scanned)
    components_manifest = build_components_manifest(args.id, components_html, tokens_css, scanned)
    manifest = {
        "schemaVersion": "od-design-system-project/v1",
        "id": args.id,
        "name": args.name or title_from_id(args.id),
        "category": args.category,
        "description": args.description,
        "source": {"type": "local", "path": str(source)},
        "files": {
            "design": "DESIGN.md",
            "tokens": "tokens.css",
            "components": "components.html",
            "designTokens": "design-tokens.json",
            "tailwind": "tailwind-v4.css",
        },
        "usage": "USAGE.md",
        "componentsManifest": "components.manifest.json",
        "sourceFiles": {"report": "source/token-contract.report.json"},
        "importMode": "normalized",
        "craft": {"applies": [], "suggested": [], "exemptions": []},
    }
    health = evaluate_design_system_health(
        design_system_id=args.id,
        design_md=design_md,
        tokens_css=tokens_css,
        components_html=components_html,
        components_manifest=json.dumps(components_manifest, ensure_ascii=False, indent=2),
    )

    write_text(out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_text(out_dir / "USAGE.md", usage_md)
    write_text(out_dir / "DESIGN.md", design_md)
    write_text(out_dir / "tokens.css", tokens_css)
    write_text(out_dir / "components.html", components_html)
    write_text(out_dir / "components.manifest.json", json.dumps(components_manifest, ensure_ascii=False, indent=2) + "\n")
    write_text(out_dir / "source" / "token-contract.report.json", json.dumps(health.to_payload(), ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({"id": args.id, "out_dir": str(out_dir), "valid": health.valid, "errors": health.errors, "warnings": health.warnings}, ensure_ascii=False, indent=2))


def scan_project(source: Path) -> dict:
    tokens: dict[str, str] = {}
    refs: set[str] = set()
    classes: set[str] = set()
    elements: set[str] = set()
    file_count = 0
    for path in source.rglob("*"):
        if not path.is_file() or not CSS_FILE_RE.search(path.name):
            continue
        if any(part in {"node_modules", ".git", "dist", "build", ".next", "vendor"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        file_count += 1
        for name, value in TOKEN_DECL_RE.findall(text):
            tokens.setdefault(name, value.strip())
        refs.update(TOKEN_REF_RE.findall(text))
        classes.update(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]+)", text))
        elements.update(re.findall(r"<([a-z][a-z0-9-]*)\b", text, flags=re.IGNORECASE))
    return {
        "tokens": tokens,
        "refs": sorted(refs),
        "classes": sorted(classes)[:120],
        "elements": sorted(elements)[:80],
        "file_count": file_count,
    }


def build_tokens_css(tokens: dict[str, str]) -> str:
    mapped: dict[str, str] = {}
    for standard, aliases in STANDARD_TOKEN_ALIASES.items():
        value = next((tokens[name] for name in aliases if name in tokens), None)
        mapped[standard] = value or fallback_token_value(standard)
    for name, value in sorted(tokens.items()):
        mapped.setdefault(name, value)
    lines = [":root {"]
    for name, value in mapped.items():
        lines.append(f"  {name}: {value};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def fallback_token_value(name: str) -> str:
    schema_value = schema_fallback_token_value(name)
    if schema_value is not None:
        return schema_value
    fallback = {
        "--bg": "#FFFFFF",
        "--surface": "#F8FAFC",
        "--fg": "#0F172A",
        "--muted": "#64748B",
        "--border": "#CBD5E1",
        "--accent": "#2563EB",
        "--font-display": "Inter, system-ui, sans-serif",
        "--font-body": "Inter, system-ui, sans-serif",
        "--text-base": "16px",
        "--radius-md": "8px",
        "--focus-ring": "0 0 0 3px color-mix(in srgb, var(--accent) 28%, transparent)",
        "--container-max": "1120px",
    }
    return fallback.get(name, "initial")


def build_design_md(*, design_system_id: str, name: str, category: str, description: str, palette: list[str], source: Path, scanned_files: int) -> str:
    palette_text = ", ".join(palette) if palette else "defined in tokens.css"
    return (
        f"# {name}\n\n"
        f"> {description}\n"
        f"> Category: {category}\n\n"
        "## 1. Intent\n"
        f"Imported from `{source}` after scanning {scanned_files} source files. Use this design system as a normalized asset bundle, not as free-form styling advice.\n\n"
        "## 2. Color And Tone\n"
        f"Palette is binding through `tokens.css`: {palette_text}. Keep accent use restrained for CTA, focus, and important emphasis.\n\n"
        "## 3. Layout\n"
        "Use the container, radius, typography, border, and spacing tokens from `tokens.css`. Favor clear hierarchy and reusable component shapes from the fixture.\n\n"
        "## 4. Components\n"
        "Match `components.manifest.json` and `components.html` for button, card, field, and section shapes.\n"
    )


def build_usage_md() -> str:
    return (
        "# Usage\n\n"
        "- Paste the unscoped `:root` block from `tokens.css` verbatim into the first `<style>`.\n"
        "- Use `var(--*)` references for colors, typography, focus, radius, border, and surfaces.\n"
        "- Do not redefine token values or write raw hex outside the root block.\n"
    )


def build_components_html(name: str, tokens_css: str, scanned: dict) -> str:
    classes = ", ".join(scanned["classes"][:12]) or "button, card, field"
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\"><style>\n"
        f"{tokens_css}\n"
        ".fixture { max-width: var(--container-max); margin: 0 auto; padding: 32px; background: var(--bg); color: var(--fg); font-family: var(--font-body); }\n"
        ".fixture-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 24px; }\n"
        ".fixture-button { background: var(--accent); color: var(--bg); border: 0; border-radius: var(--radius-md); padding: 10px 14px; }\n"
        ".fixture-muted { color: var(--muted); }\n"
        "</style></head><body><main class=\"fixture\">\n"
        f"<section class=\"fixture-card\"><h1>{escape(name)}</h1><p class=\"fixture-muted\">Imported component fixture. Source classes include: {escape(classes)}</p><button class=\"fixture-button\">Primary action</button></section>\n"
        "</main></body></html>\n"
    )


def build_components_manifest(design_system_id: str, components_html: str, tokens_css: str, scanned: dict) -> dict:
    manifest = extract_components_manifest(brand_id=design_system_id, fixture_html=components_html, tokens_css=tokens_css)
    if manifest is not None:
        return manifest
    declarations = sorted(parse_token_declarations(tokens_css))
    return {
        "schemaVersion": 1,
        "brandId": design_system_id,
        "source": {"componentsHtml": "components.html", "tokensCss": "tokens.css"},
        "fixture": {"styleBlockCount": 0, "selectorCount": 0, "classCount": 0, "elementCount": 0},
        "tokens": {
            "declared": declarations,
            "referenced": [],
            "unusedDeclared": declarations,
            "undeclaredReferenced": [],
        },
        "selectors": [],
        "classes": [],
        "elements": [],
        "groups": [],
        "literals": {"colorExpressions": 0, "pixelValues": 0, "hardcodedFontFamilies": 0},
    }


def title_from_id(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
