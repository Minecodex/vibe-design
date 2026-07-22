"""Design-system asset-bundle loader for Home Harness."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .components_manifest import (
    extract_components_manifest,
    summarize_components_manifest_for_prompt,
    summarize_components_manifest_json,
)
from .token_contract import DesignSystemHealth, evaluate_design_system_health, extract_palette_from_tokens

logger = logging.getLogger(__name__)

_DESIGN_SYSTEMS_DIR = Path(__file__).parent


@dataclass(slots=True)
class DesignSystemDefinition:
    id: str
    title: str
    description: str
    category: str | None = None
    sections: list[str] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    preview: str | None = None
    featured: int | None = None
    is_default: bool = False
    body: str = ""
    design_md: str = ""
    usage_md: str | None = None
    tokens_css: str | None = None
    fixture_html: str | None = None
    components_manifest: str | None = None
    pull_index: str | None = None
    manifest: dict[str, Any] | None = None
    import_mode: str | None = None
    craft_applies: list[str] = field(default_factory=list)
    craft_exemptions: list[str] = field(default_factory=list)
    health: DesignSystemHealth | None = None
    asset_paths: dict[str, str] = field(default_factory=dict)
    source_digest: str = ""
    directory: Path | None = None


_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)
_CATEGORY_RE = re.compile(r"^>\s*Category:\s*(.+)$", re.MULTILINE)
_SECTION_RE = re.compile(r"^##\s+\d+\.\s+(.+)$", re.MULTILINE)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
_FALLBACK_PALETTE = ["#F8FAFC", "#E2E8F0", "#94A3B8", "#0F172A"]


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _extract_palette(body: str) -> list[str]:
    palette: list[str] = []
    seen: set[str] = set()
    for match in _HEX_COLOR_RE.finditer(body):
        color = match.group(0).upper()
        if color in seen:
            continue
        palette.append(color)
        seen.add(color)
        if len(palette) >= 4:
            break
    return palette or list(_FALLBACK_PALETTE)


def _manifest_list(manifest: dict[str, Any] | None, key: str) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    value = manifest.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _manifest_craft(manifest: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    craft = manifest.get("craft") if isinstance(manifest, dict) else None
    if not isinstance(craft, dict):
        return [], []
    applies = craft.get("applies") or craft.get("requires")
    exemptions = craft.get("exemptions") or craft.get("exempt")
    return _string_items(applies), _string_items(exemptions)


def _load_manifest(system_dir: Path) -> dict[str, Any] | None:
    manifest_path = system_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to load design system manifest %s", manifest_path, exc_info=True)
        return None
    return raw if isinstance(raw, dict) else None


def _manifest_file(manifest: dict[str, Any] | None, key: str, default: str) -> str:
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if isinstance(files, dict):
        value = str(files.get(key) or "").strip()
        if value:
            return value
    return default


def _manifest_scalar(manifest: dict[str, Any] | None, key: str, default: str) -> str:
    if isinstance(manifest, dict):
        value = str(manifest.get(key) or "").strip()
        if value:
            return value
    return default


def _resolve_asset_path(system_dir: Path, relative_path: str, *, system_id: str, asset_key: str) -> Path | None:
    raw = str(relative_path or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return None
    root = system_dir.resolve()
    candidate = (root / raw).resolve()
    try:
        inside = candidate.is_relative_to(root)
    except AttributeError:
        inside = str(candidate).startswith(str(root))
    if not inside:
        logger.warning("Rejected design system asset outside directory: %s %s=%s", system_id, asset_key, raw)
        return None
    return candidate


def _read_optional_asset(
    system_dir: Path,
    relative_path: str,
    *,
    system_id: str,
    asset_key: str,
) -> tuple[str | None, str | None]:
    path = _resolve_asset_path(system_dir, relative_path, system_id=system_id, asset_key=asset_key)
    if path is None or not path.is_file():
        return None, None
    try:
        return path.read_text(encoding="utf-8"), f"design_system/{system_id}/{path.relative_to(system_dir.resolve()).as_posix()}"
    except Exception:
        logger.warning("Failed to read design system asset %s", path, exc_info=True)
        return None, None


def _summarize_components_manifest(raw: str | None, *, system_id: str) -> str | None:
    summary = summarize_components_manifest_json(raw, system_id=system_id)
    if summary is None and raw:
        logger.warning("Failed to parse components manifest for %s", system_id, exc_info=True)
    return summary


def _summarize_components_fixture(fixture_html: str | None, tokens_css: str | None, *, system_id: str) -> str | None:
    manifest = extract_components_manifest(brand_id=system_id, fixture_html=fixture_html, tokens_css=tokens_css)
    return summarize_components_manifest_for_prompt(manifest) if manifest else None


def _build_design_system_pull_index(manifest: dict[str, Any] | None) -> str | None:
    if not isinstance(manifest, dict):
        return None
    entries: list[str] = []

    def add(file_path: Any, label: str) -> None:
        if not isinstance(file_path, str) or not _is_safe_manifest_path(file_path):
            return
        entries.append(f"- {file_path}: {label}")

    preview = manifest.get("preview")
    if isinstance(preview, dict) and isinstance(preview.get("pages"), list):
        for page in preview.get("pages") or []:
            if not isinstance(page, dict):
                continue
            path = page.get("path")
            if not isinstance(path, str) or not _is_safe_manifest_path(path):
                continue
            label_parts = [str(page.get(key) or "").strip() for key in ("title", "role")]
            label = "; ".join(part for part in label_parts if part) or "preview page"
            entries.append(f"- {path}: {label}")
    elif manifest.get("previewDir") == "preview":
        entries.append("- preview/: preview pages")

    if manifest.get("assetsDir") == "assets":
        entries.append("- assets/: brand assets")
    for font in manifest.get("fonts") or []:
        if not isinstance(font, dict):
            continue
        family = str(font.get("family") or "font").strip()
        suffix = " ".join(str(font.get(key) or "").strip() for key in ("weight", "style")).strip()
        add(font.get("file"), f"font: {family}{(' ' + suffix) if suffix else ''}")

    source_files = manifest.get("sourceFiles") if isinstance(manifest.get("sourceFiles"), dict) else {}
    add(source_files.get("scanned"), "scanned source file inventory")
    add(source_files.get("evidence"), "import evidence notes")
    add(source_files.get("tokens"), "source-token evidence")
    add(source_files.get("report"), "token contract quality report")
    add(source_files.get("snippets"), "source snippet index")
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    add(files.get("designTokens"), "derived Design Tokens JSON")
    add(files.get("tailwind"), "derived Tailwind v4 theme CSS")
    return "\n".join(["Additional design-system files declared by manifest.json:", *entries]) if entries else None


def _is_safe_manifest_path(path: str) -> bool:
    raw = str(path or "").strip()
    if not raw or raw.startswith("/") or "\\" in raw or re.match(r"^[A-Za-z]:[\\/]", raw):
        return False
    parts = raw.split("/")
    return not any(part in {"", ".", ".."} for part in parts)


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _digest(*parts: str | None) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        if part:
            hasher.update(part.encode("utf-8"))
            hasher.update(b"\0")
    return hasher.hexdigest()


def _load_design_system_from_dir(system_dir: Path) -> DesignSystemDefinition | None:
    if not system_dir.is_dir() or system_dir.name.startswith("_") or system_dir.name == "__pycache__":
        return None

    manifest = _load_manifest(system_dir)
    design_path = _manifest_file(manifest, "design", "DESIGN.md")
    usage_path = _manifest_scalar(manifest, "usage", "USAGE.md")
    tokens_path = _manifest_file(manifest, "tokens", "tokens.css")
    fixture_path = _manifest_file(manifest, "components", "components.html")
    components_manifest_path = _manifest_scalar(manifest, "componentsManifest", "components.manifest.json")

    asset_paths: dict[str, str] = {}
    body, loaded_design_path = _read_optional_asset(
        system_dir,
        design_path,
        system_id=system_dir.name,
        asset_key="design",
    )
    if not body:
        return None
    if loaded_design_path:
        asset_paths["design"] = loaded_design_path

    usage_md, loaded_usage_path = _read_optional_asset(
        system_dir,
        usage_path,
        system_id=system_dir.name,
        asset_key="usage",
    )
    if loaded_usage_path:
        asset_paths["usage"] = loaded_usage_path

    tokens_css, loaded_tokens_path = _read_optional_asset(
        system_dir,
        tokens_path,
        system_id=system_dir.name,
        asset_key="tokens",
    )
    if loaded_tokens_path:
        asset_paths["tokens"] = loaded_tokens_path

    fixture_html, loaded_fixture_path = _read_optional_asset(
        system_dir,
        fixture_path,
        system_id=system_dir.name,
        asset_key="components",
    )
    if loaded_fixture_path:
        asset_paths["components"] = loaded_fixture_path

    components_manifest_raw, loaded_manifest_path = _read_optional_asset(
        system_dir,
        components_manifest_path,
        system_id=system_dir.name,
        asset_key="componentsManifest",
    )
    components_manifest = _summarize_components_manifest(components_manifest_raw, system_id=system_dir.name)
    if components_manifest and loaded_manifest_path:
        asset_paths["components_manifest"] = loaded_manifest_path
    if components_manifest is None:
        components_manifest = _summarize_components_fixture(fixture_html, tokens_css, system_id=system_dir.name)

    heading_match = _HEADING_RE.search(body)
    title = heading_match.group(1).strip() if heading_match else _slug_to_title(system_dir.name)
    summary_match = _BLOCKQUOTE_RE.search(body)
    description = summary_match.group(1).strip() if summary_match else title
    category_match = _CATEGORY_RE.search(body)
    category = category_match.group(1).strip() if category_match else None
    sections = [match.group(1).strip() for match in _SECTION_RE.finditer(body)]
    palette = extract_palette_from_tokens(tokens_css) or _extract_palette(body)
    import_mode = str((manifest or {}).get("importMode") or "").strip() or None
    craft_applies, craft_exemptions = _manifest_craft(manifest)
    pull_index = _build_design_system_pull_index(manifest)
    health = evaluate_design_system_health(
        design_system_id=system_dir.name,
        design_md=body,
        tokens_css=tokens_css,
        components_html=fixture_html,
        components_manifest=components_manifest,
    )

    return DesignSystemDefinition(
        id=system_dir.name,
        title=title,
        description=description,
        category=category,
        sections=sections,
        palette=palette,
        is_default=system_dir.name == "default",
        body=body,
        design_md=body,
        usage_md=usage_md.strip() if usage_md else None,
        tokens_css=tokens_css.strip() if tokens_css else None,
        fixture_html=fixture_html,
        components_manifest=components_manifest,
        pull_index=pull_index,
        manifest=manifest,
        import_mode=import_mode,
        craft_applies=craft_applies,
        craft_exemptions=craft_exemptions,
        health=health,
        asset_paths=asset_paths,
        source_digest=_digest(body, usage_md, tokens_css, components_manifest, pull_index, json.dumps(health.to_payload(), sort_keys=True)),
        directory=system_dir.resolve(),
    )


def _load_design_systems() -> dict[str, DesignSystemDefinition]:
    systems: dict[str, DesignSystemDefinition] = {}
    for system_dir in sorted(_DESIGN_SYSTEMS_DIR.iterdir()):
        system = _load_design_system_from_dir(system_dir)
        if system is not None:
            systems[system.id] = system
    return systems


DESIGN_SYSTEMS: dict[str, DesignSystemDefinition] | None = None
DESIGN_SYSTEM_CACHE: dict[str, DesignSystemDefinition] = {}


def _ensure_design_systems_loaded() -> dict[str, DesignSystemDefinition]:
    global DESIGN_SYSTEMS
    if DESIGN_SYSTEMS is None:
        DESIGN_SYSTEMS = _load_design_systems()
    return DESIGN_SYSTEMS


def list_design_systems() -> list[DesignSystemDefinition]:
    return list(_ensure_design_systems_loaded().values())


def _is_valid_design_system_id(design_system_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", design_system_id))


def get_design_system(design_system_id: str | None) -> DesignSystemDefinition | None:
    normalized = str(design_system_id or "").strip()
    if not normalized:
        return None
    if DESIGN_SYSTEMS is not None:
        return DESIGN_SYSTEMS.get(normalized)
    if normalized in DESIGN_SYSTEM_CACHE:
        return DESIGN_SYSTEM_CACHE[normalized]
    if not _is_valid_design_system_id(normalized):
        return None
    system = _load_design_system_from_dir(_DESIGN_SYSTEMS_DIR / normalized)
    if system is None:
        return None
    DESIGN_SYSTEM_CACHE[normalized] = system
    return system


def reload_design_systems() -> None:
    global DESIGN_SYSTEMS, DESIGN_SYSTEM_CACHE
    DESIGN_SYSTEMS = None
    DESIGN_SYSTEM_CACHE = {}
    try:
        from app.services.agent_harness.catalog import invalidate_agent_catalog_cache_sync

        invalidate_agent_catalog_cache_sync()
    except Exception:
        logger.debug("Failed to invalidate agent catalog cache after design system reload", exc_info=True)
    try:
        from .resolver_registry import clear_design_system_resolver_registry_cache

        clear_design_system_resolver_registry_cache()
    except Exception:
        logger.debug("Failed to clear design system resolver registry cache", exc_info=True)
