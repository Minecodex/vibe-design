"""Canonical artifact-work-root path helpers shared across the critique runtime.

Historically each module normalized ``artifact_work_root`` / entry paths with its
own rules: critique eligibility stripped a leading ``project/`` segment, while the
workspace-snapshot layer rejected any value containing a ``/`` outright. That
divergence let an eligibility check admit a value (e.g. ``project/html-ppt-prepared``)
that the snapshot layer then rejected, crashing the run on restore. These helpers
are the single source of truth so every caller agrees on what a valid single
path-component work root is and how a work root is derived from an entry path.
"""

from __future__ import annotations


def normalize_relpath(value: str | None) -> str:
    """Normalize a workspace-relative path.

    Converts backslashes, trims surrounding whitespace/slashes, drops a leading
    ``project/`` segment, and rejects parent-escaping (``..``) paths. Returns an
    empty string when nothing safe remains.
    """
    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if parts and parts[0] == "project":
        parts = parts[1:]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def safe_work_root(value: str | None) -> str:
    """Return ``value`` as a single safe path component, or ``""`` if it is not one."""
    normalized = normalize_relpath(value)
    return normalized if normalized and "/" not in normalized else ""


def work_root_from_entry(entry: str | None) -> str:
    """Derive the work root from a nested entry's top-level directory.

    A bare top-level file (no directory) yields ``""`` so it is never treated as a
    work root on its own.
    """
    normalized = normalize_relpath(entry)
    parts = [part for part in normalized.split("/") if part]
    return parts[0] if len(parts) >= 2 else ""
