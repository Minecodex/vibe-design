from __future__ import annotations

import json
from threading import Lock
from typing import Any

from app.services.agent_harness.capabilities.skill_protocols import ProtocolRuntimeContext, resolve_skill_protocol
from app.services.agent_harness.capabilities.skills import list_skills, skills_generation

_CATALOG_CACHE_LOCK = Lock()
_CATALOG_CACHE: tuple[int, bytes] | None = None


def _secondary_outputs(skill: Any) -> list[dict | str]:
    output_schema = getattr(skill, "output_schema", None)
    secondary = (output_schema or {}).get("secondary") if isinstance(output_schema, dict) else None
    if isinstance(secondary, list):
        return list(secondary)
    if secondary is None:
        return []
    return [secondary]


def _skill_payload(skill: Any) -> dict[str, Any]:
    protocol = resolve_skill_protocol(
        skill,
        ProtocolRuntimeContext(
            artifact_mode=skill.artifact_mode,
            project_kind=skill.artifact_mode,
        ),
    )
    protocol_metadata = {
        **dict(protocol.metadata or {}),
        "execution_strategy": skill.execution_strategy,
        "directions": list(skill.directions or []),
        "seed_assets": list(skill.seed_assets or []),
        "design_system": {
            "requires": bool(skill.design_system.requires),
            "sections": list(skill.design_system.sections or []),
        },
        "craft": {"requires": list(skill.craft.requires or [])},
        "upstream": skill.upstream,
        "template_roots": list(getattr(skill, "template_roots", []) or []),
        "fragment_roots": list(getattr(skill, "fragment_roots", []) or []),
    }
    capabilities = {
        **dict(getattr(skill, "runtime_capabilities", {}) or {}),
        "parameters": list(skill.parameters or []),
        "secondary_outputs": _secondary_outputs(skill),
    }
    return {
        "id": skill.id,
        "name": skill.name,
        "name_en": skill.name_en,
        "name_zh": skill.name_zh,
        "description": skill.description,
        "description_en": skill.description_en,
        "description_zh": skill.description_zh,
        "icon": skill.icon,
        "color": skill.color,
        "triggers": skill.triggers,
        "mode": skill.mode,
        "surface": skill.surface,
        "platform": skill.platform,
        "scenario": skill.scenario,
        "artifact_mode": skill.artifact_mode,
        "default_for": skill.default_for,
        "featured": skill.featured,
        "preview_type": skill.preview.type,
        "preview_entry": skill.preview.entry,
        "primary_output": skill.primary_output,
        "parameters": skill.parameters,
        "outputs_secondary": _secondary_outputs(skill),
        "metadata_health": skill.metadata_health,
        "protocol_provider": protocol.provider,
        "protocol_family": protocol.family,
        "protocol_metadata": protocol_metadata,
        "capabilities": capabilities,
        "example_prompt": skill.example_prompt,
        "has_example_html": bool(skill.skill_dir and (skill.skill_dir / "example.html").is_file()),
    }


def build_skill_catalog_payload() -> list[dict[str, Any]]:
    return [_skill_payload(skill) for skill in list_skills()]


def skill_catalog_json_bytes() -> bytes:
    global _CATALOG_CACHE
    generation = skills_generation()
    cached = _CATALOG_CACHE
    if cached is not None and cached[0] == generation:
        return cached[1]
    with _CATALOG_CACHE_LOCK:
        cached = _CATALOG_CACHE
        if cached is not None and cached[0] == generation:
            return cached[1]
        payload = json.dumps(build_skill_catalog_payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _CATALOG_CACHE = (generation, payload)
        return payload
