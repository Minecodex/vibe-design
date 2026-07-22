from __future__ import annotations

from typing import Any

from . import DesignSystemDefinition

ACTIVE_DESIGN_SYSTEM_CONTEXT_VERSION = 1


def build_active_design_system_context(design_system: DesignSystemDefinition) -> dict[str, Any]:
    loaded_paths = [
        path
        for key, path in sorted(design_system.asset_paths.items())
        if key != "components" and str(path or "").strip()
    ]
    if not loaded_paths and design_system.body:
        loaded_paths = [f"design_system/{design_system.id}/DESIGN.md"]
    health = design_system.health.to_payload() if design_system.health is not None else None
    return {
        "version": ACTIVE_DESIGN_SYSTEM_CONTEXT_VERSION,
        "kind": "active_design_system_context",
        "design_system_id": design_system.id,
        "title": design_system.title,
        "source_digest": design_system.source_digest,
        "loaded_paths": loaded_paths,
        "design_md": design_system.design_md or design_system.body,
        "usage_md": design_system.usage_md,
        "tokens_css": design_system.tokens_css,
        "components_manifest": design_system.components_manifest,
        "pull_index": design_system.pull_index,
        "fixture_html": None,
        "import_mode": design_system.import_mode or "normalized",
        "craft_applies": list(design_system.craft_applies),
        "craft_exemptions": list(design_system.craft_exemptions),
        "health": health,
    }
