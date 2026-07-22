from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CRAFT_DIR = Path(__file__).resolve().parent / "craft"


def _normalize_requested_slugs(requested: Any) -> list[str]:
    if not isinstance(requested, list):
        return []
    slugs: list[str] = []
    seen: set[str] = set()
    for raw in requested:
        if not isinstance(raw, str):
            continue
        slug = raw.strip().lower()
        if not _SLUG_RE.fullmatch(slug) or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def load_craft_reference_block(requested: Any) -> tuple[str, list[str]]:
    """Load requested craft markdown files.

    Missing or unreadable sections are skipped for open-design-compatible
    forward references.
    """
    parts: list[str] = []
    resolved: list[str] = []
    for slug in _normalize_requested_slugs(requested):
        try:
            text = (_CRAFT_DIR / f"{slug}.md").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if not text:
            continue
        parts.append(f"### {slug}\n\n{text}")
        resolved.append(slug)
    if not parts:
        return "", []

    section_label = f" - {', '.join(resolved)}" if resolved else ""
    header = (
        f"## Active craft references{section_label}\n\n"
        "The following craft rules are universal. They apply on top of the active design system, "
        "regardless of brand. The DESIGN.md decides which token values to use; craft rules decide "
        "how to use them. On any conflict between a craft rule and a brand DESIGN.md, the brand "
        "wins for token values; craft rules still apply to details the brand does not override."
    )
    return f"{header}\n\n" + "\n\n---\n\n".join(parts), resolved
