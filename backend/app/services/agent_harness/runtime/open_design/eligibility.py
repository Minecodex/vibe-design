from __future__ import annotations

from typing import Any

HTML_ARTIFACT_MODES = {"html", "web", "slides", "deck"}
MEDIA_MODES = {"image", "video", "audio"}
OFFICE_MODES = {"docx", "xlsx", "pptx", "document", "spreadsheet"}


def is_home_open_design_html_run(ctx_or_conversation: Any, protocol: Any | None = None) -> bool:
    runtime_profile = _value(ctx_or_conversation, "runtime_profile", "home")
    if str(runtime_profile or "home").strip().lower() != "home":
        return False

    artifact_mode = str(_value(ctx_or_conversation, "artifact_mode", "") or "").strip().lower()
    skill_id = str(
        _value(ctx_or_conversation, "skill_id", "")
        or _value(ctx_or_conversation, "resolved_skill_id", "")
        or ""
    ).strip().lower()
    protocol_mode = str(getattr(protocol, "mode", "") or "").strip().lower()
    protocol_surface = str(getattr(protocol, "surface", "") or "").strip().lower()
    provider = str(getattr(protocol, "provider", "") or "").strip().lower()

    if provider and provider != "open_design":
        return False
    if protocol is not None and provider != "open_design":
        return False

    candidates = {artifact_mode, protocol_mode, protocol_surface, skill_id}
    if candidates & MEDIA_MODES:
        return False
    if candidates & OFFICE_MODES or skill_id in OFFICE_MODES:
        return False
    return bool(candidates & HTML_ARTIFACT_MODES)


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)

