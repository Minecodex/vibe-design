from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_harness.capabilities.design_systems import (  # noqa: E402
    _summarize_components_manifest,
)
from app.services.agent_harness.capabilities.design_systems.components_manifest import extract_components_manifest
from app.services.agent_harness.capabilities.design_systems.token_contract import (  # noqa: E402
    CONFLICT_COLOR_LABEL_RE,
    TOKEN_REF_RE,
    evaluate_design_system_health,
    extract_palette_from_tokens,
    extract_root_block,
    parse_token_declarations,
)

DESIGN_SYSTEMS_ROOT = BACKEND_ROOT / "app/services/agent_harness/capabilities/design_systems"


def main() -> None:
    changed = 0
    total = 0
    for system_dir in sorted(DESIGN_SYSTEMS_ROOT.iterdir()):
        if not system_dir.is_dir() or system_dir.name.startswith("_") or system_dir.name == "__pycache__":
            continue
        if not (system_dir / "DESIGN.md").is_file() or not (system_dir / "tokens.css").is_file():
            continue
        total += 1
        changed += normalize_bundle(system_dir)
    print(json.dumps({"normalized": changed, "total": total}, ensure_ascii=False, indent=2))


def normalize_bundle(system_dir: Path) -> int:
    before = snapshot(system_dir)
    design_md = read_text(system_dir / "DESIGN.md")
    tokens_css = read_text(system_dir / "tokens.css")
    components_html = read_text(system_dir / "components.html")

    tokens_css = ensure_missing_token_references(tokens_css, components_html)
    design_md = align_design_color_labels(design_md, tokens_css)

    write_text(system_dir / "DESIGN.md", design_md)
    write_text(system_dir / "tokens.css", tokens_css)
    ensure_dirs(system_dir)
    ensure_manifest(system_dir, design_md)
    ensure_usage(system_dir)
    ensure_components_manifest(system_dir, tokens_css, components_html)
    write_health_report(system_dir)
    return 1 if snapshot(system_dir) != before else 0


def align_design_color_labels(design_md: str, tokens_css: str) -> str:
    declarations = parse_token_declarations(extract_root_block(tokens_css) or tokens_css)
    accent = first_hex(str(declarations.get("--accent") or ""))
    if not accent:
        return design_md

    replacements: set[str] = set()

    def replace_label(match: re.Match[str]) -> str:
        label = str(match.group(1) or "")
        color = str(match.group(2) or "")
        if color.upper() != accent.upper():
            replacements.add(color)
        return match.group(0).replace(color, accent)

    updated = CONFLICT_COLOR_LABEL_RE.sub(replace_label, design_md)
    for old in sorted(replacements, key=len, reverse=True):
        updated = re.sub(
            rf"\b(Primary|Accent|Button|Buttons|CTA)\s*\(\s*{re.escape(old)}\s*\)",
            lambda m: m.group(0).replace(old, accent),
            updated,
            flags=re.IGNORECASE,
        )
        updated = re.sub(
            rf"`{re.escape(old)}`",
            f"`{accent}`",
            updated,
        )
    return updated


def ensure_missing_token_references(tokens_css: str, components_html: str) -> str:
    root = extract_root_block(tokens_css)
    declarations = parse_token_declarations(root or tokens_css)
    refs = sorted(set(TOKEN_REF_RE.findall(tokens_css + "\n" + components_html)))
    missing = [ref for ref in refs if ref not in declarations]
    if not missing:
        return ensure_trailing_newline(tokens_css)
    additions = "".join(f"  {token}: {fallback_for_token(token)};\n" for token in missing)
    if root:
        replacement = root[:-1].rstrip() + "\n" + additions + "}"
        return ensure_trailing_newline(tokens_css.replace(root, replacement, 1))
    return ensure_trailing_newline(":root {\n" + additions + "}\n\n" + tokens_css)


def fallback_for_token(token: str) -> str:
    lowered = token.lower()
    if "font" in lowered:
        return "var(--font-body)"
    if "radius" in lowered:
        return "var(--radius-md)"
    if "border" in lowered:
        return "var(--border)"
    if "bg" in lowered or "surface" in lowered:
        return "var(--surface)"
    if "fg" in lowered or "text" in lowered:
        return "var(--fg)"
    return "var(--accent)"


def ensure_manifest(system_dir: Path, design_md: str) -> None:
    manifest_path = system_dir / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(read_text(manifest_path))
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception:
            manifest = {}
    system_id = system_dir.name
    title = title_from_design(system_id, design_md)
    description = description_from_design(title, design_md)
    category = category_from_design(design_md) or "Bundled"
    normalized = {
        "schemaVersion": "od-design-system-project/v1",
        "id": str(manifest.get("id") or system_id),
        "name": str(manifest.get("name") or title),
        "category": str(manifest.get("category") or category),
        "description": str(manifest.get("description") or description),
        "source": manifest.get("source") if isinstance(manifest.get("source"), dict) else {"type": "bundled"},
        "files": {
            "design": "DESIGN.md",
            "tokens": "tokens.css",
            "components": "components.html",
        },
        "usage": "USAGE.md",
        "componentsManifest": "components.manifest.json",
        "assetsDir": "assets",
        "previewDir": "preview",
        "sourceFiles": {"report": "source/token-contract.report.json"},
        "importMode": str(manifest.get("importMode") or "normalized"),
        "craft": manifest.get("craft") if isinstance(manifest.get("craft"), dict) else {"applies": [], "suggested": [], "exemptions": []},
    }
    write_text(manifest_path, json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")


def ensure_usage(system_dir: Path) -> None:
    path = system_dir / "USAGE.md"
    if path.is_file() and read_text(path).strip():
        return
    write_text(
        path,
        "# Usage\n\n"
        "- `DESIGN.md` describes visual intent and component language.\n"
        "- `tokens.css` is the binding runtime contract.\n"
        "- Paste the unscoped `:root { ... }` block from `tokens.css` verbatim into the first `<style>`.\n"
        "- Do not invent tokens, redefine token values, or write raw hex outside the root block.\n"
        "- Match component shapes from `components.manifest.json` and `components.html`.\n",
    )


def ensure_components_manifest(system_dir: Path, tokens_css: str, components_html: str) -> None:
    path = system_dir / "components.manifest.json"
    data = extract_components_manifest(brand_id=system_dir.name, fixture_html=components_html, tokens_css=tokens_css)
    if data is None:
        declared = sorted(parse_token_declarations(extract_root_block(tokens_css) or tokens_css))
        data = {
            "schemaVersion": 1,
            "brandId": system_dir.name,
            "source": {"componentsHtml": "components.html", "tokensCss": "tokens.css"},
            "fixture": {"styleBlockCount": 0, "selectorCount": 0, "classCount": 0, "elementCount": 0},
            "tokens": {"declared": declared, "referenced": [], "unusedDeclared": declared, "undeclaredReferenced": []},
            "selectors": [],
            "classes": [],
            "elements": [],
            "groups": [],
            "literals": {"colorExpressions": 0, "pixelValues": 0, "hardcodedFontFamilies": 0},
        }
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    # Round-trip through the loader summarizer so malformed output is caught here.
    _summarize_components_manifest(json.dumps(data), system_id=system_dir.name)


def write_health_report(system_dir: Path) -> None:
    design_md = read_text(system_dir / "DESIGN.md")
    tokens_css = read_text(system_dir / "tokens.css")
    components_html = read_text(system_dir / "components.html")
    components_manifest = read_text(system_dir / "components.manifest.json")
    health = evaluate_design_system_health(
        design_system_id=system_dir.name,
        design_md=design_md,
        tokens_css=tokens_css,
        components_html=components_html,
        components_manifest=components_manifest,
    )
    write_text(system_dir / "source" / "token-contract.report.json", json.dumps(health.to_payload(), ensure_ascii=False, indent=2) + "\n")


def ensure_dirs(system_dir: Path) -> None:
    for name in ("assets", "fonts", "preview", "source"):
        (system_dir / name).mkdir(exist_ok=True)


def title_from_design(system_id: str, design_md: str) -> str:
    match = re.search(r"^#\s+(.+)$", design_md, flags=re.MULTILINE)
    return match.group(1).strip() if match else title_from_slug(system_id)


def description_from_design(title: str, design_md: str) -> str:
    match = re.search(r"^>\s*(?!Category:)(.+)$", design_md, flags=re.MULTILINE)
    return match.group(1).strip() if match else title


def category_from_design(design_md: str) -> str | None:
    match = re.search(r"^>\s*Category:\s*(.+)$", design_md, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def first_hex(value: str) -> str | None:
    match = re.search(r"#[0-9a-fA-F]{6}\b", value)
    return match.group(0).upper() if match else None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ensure_trailing_newline(text), encoding="utf-8")


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def snapshot(system_dir: Path) -> str:
    names = ["manifest.json", "USAGE.md", "DESIGN.md", "tokens.css", "components.manifest.json", "source/token-contract.report.json"]
    return "\0".join(read_text(system_dir / name) for name in names)


if __name__ == "__main__":
    main()
