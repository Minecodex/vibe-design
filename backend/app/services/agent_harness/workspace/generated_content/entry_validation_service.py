from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, unquote

from app.services.agent_harness.workspace.conversation.workspace_preview_service import analyze_html_bundle_entry


def validate_entry_path(path: Path, *, kind: str | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    detected_kind = _normalize_kind(kind or _kind_from_path(resolved))
    if not resolved.exists() or not resolved.is_file():
        return _result(False, detected_kind, ["entry file does not exist"])
    if resolved.stat().st_size <= 0:
        return _result(False, detected_kind, ["entry file is empty"])

    try:
        if detected_kind == "json":
            json.loads(resolved.read_text(encoding="utf-8"))
            return _result(True, detected_kind)
        if detected_kind == "jsonl":
            return _validate_jsonl_text(resolved.read_text(encoding="utf-8"), detected_kind)
        if detected_kind in {"text", "markdown"}:
            resolved.read_text(encoding="utf-8")
            return _result(True, detected_kind)
        if detected_kind == "html":
            return _validate_html_text(resolved.read_text(encoding="utf-8"), detected_kind, base_dir=resolved.parent)
        if detected_kind == "js_module":
            return _validate_js_module(resolved, detected_kind)
        if detected_kind in {"document", "sheet", "presentation"}:
            return _validate_office_zip(resolved, detected_kind)
        return _result(True, detected_kind)
    except UnicodeDecodeError:
        return _result(False, detected_kind, ["entry file is not valid utf-8 text"])
    except json.JSONDecodeError as exc:
        return _result(False, detected_kind, [f"invalid json: {exc.msg}"])
    except ValueError as exc:
        return _result(False, detected_kind, [str(exc)])


def validate_serialized_content(content: str, *, kind: str, path_hint: str, base_dir: Path | None = None) -> dict[str, Any]:
    detected_kind = _normalize_kind(kind or _kind_from_path(Path(path_hint)))
    try:
        if detected_kind == "json":
            json.loads(content)
            return _result(True, detected_kind)
        if detected_kind == "jsonl":
            return _validate_jsonl_text(content, detected_kind)
        if detected_kind in {"text", "markdown"}:
            return _result(True, detected_kind)
        if detected_kind == "html":
            resolved_base_dir = base_dir if base_dir is not None else Path(path_hint).resolve().parent
            return _validate_html_text(content, detected_kind, base_dir=resolved_base_dir)
        if detected_kind == "js_module":
            return _validate_js_module_text(content, detected_kind)
        return _result(True, detected_kind)
    except json.JSONDecodeError as exc:
        return _result(False, detected_kind, [f"invalid json: {exc.msg}"])
    except ValueError as exc:
        return _result(False, detected_kind, [str(exc)])


def validate_html_bundle_entry_path(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        return _result(False, "html_bundle", ["entry file does not exist"])
    if resolved.suffix.lower() not in {".html", ".htm"}:
        return _result(False, "html_bundle", ["html bundle entry must be an .html or .htm file"])
    base_validation = validate_entry_path(resolved, kind="html")
    if not base_validation.get("valid"):
        return _result(False, "html_bundle", list(base_validation.get("errors") or []))
    analysis = analyze_html_bundle_entry(resolved)
    errors = [str(item) for item in analysis.get("errors") or []]
    if errors:
        return _result(False, "html_bundle", errors)
    members = analysis.get("members") or set()
    return {
        "valid": True,
        "kind": "html_bundle",
        "errors": [],
        "entry": str(analysis.get("entry") or ""),
        "bundle_member_count": len(members),
        "bundle_members": [
            str(member.resolve().relative_to(Path(analysis["files_root"]).resolve())).replace("\\", "/")
            for member in sorted(members)
        ],
    }


def _validate_jsonl_text(content: str, kind: str) -> dict[str, Any]:
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        return _result(False, kind, ["jsonl must contain at least one non-empty line"])
    for index, line in enumerate(lines, start=1):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            return _result(False, kind, [f"invalid jsonl at line {index}: {exc.msg}"])
    return _result(True, kind)


def _validate_html_text(content: str, kind: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    lowered = content.lower()
    has_structure = "<html" in lowered or "<body" in lowered or "<!doctype html" in lowered
    has_any_tag = bool(re.search(r"<[a-zA-Z][^>]*>", content))
    if not has_structure and not has_any_tag:
        return _result(False, kind, ["html entry must contain at least one html tag"])
    html_errors = _validate_html_dependencies(content, base_dir=base_dir)
    if html_errors:
        return _result(False, kind, html_errors)
    return _result(True, kind)


def _validate_html_dependencies(content: str, base_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"""(?P<attr>href|src)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""", content, re.IGNORECASE):
        raw_value = str(match.group("value") or "").strip()
        if not raw_value:
            continue
        if _is_external_or_special_html_reference(raw_value):
            continue

        decoded_value = unquote(raw_value)
        normalized_value = decoded_value.replace("\\", "/")
        normalized_lower = normalized_value.lower()

        if "skill_dir" in normalized_lower or "harness_skill_root" in normalized_lower:
            errors.append(_html_dependency_guidance("skill_root", raw_value))
            continue
        if ".skill_runtime/" in normalized_lower or normalized_lower.startswith(".skill_runtime"):
            errors.append(_html_dependency_guidance("skill_root", raw_value))
            continue
        if _looks_like_absolute_local_reference(normalized_value):
            errors.append(_html_dependency_guidance("absolute_local", raw_value))
            continue
        if base_dir is None:
            continue

        dependency_path = _resolve_local_html_dependency(base_dir, normalized_value)
        if dependency_path is None:
            errors.append(_html_dependency_guidance("escapes_entry_dir", raw_value))
            continue
        if not dependency_path.exists() or not dependency_path.is_file():
            errors.append(_html_dependency_guidance("missing_from_entry_dir", raw_value))
    return errors


def _html_dependency_guidance(reason: str, raw_value: str) -> str:
    if reason == "skill_root":
        return (
            f"html dependency may not reference a skill root directly: {raw_value}. "
            "Final HTML must not reference skill files directly; copy the required files from skill/ "
            "into the entry directory under project/, then reference those copied files with entry-relative paths."
        )
    if reason == "absolute_local":
        return (
            f"html dependency may not reference an absolute local path: {raw_value}. "
            "Copy the required files into the entry directory under project/ and reference them with entry-relative paths instead."
        )
    if reason == "escapes_entry_dir":
        return (
            f"html dependency escapes the entry directory: {raw_value}. "
            "Final HTML may only depend on files inside its entry directory tree under project/. "
            "Copy the required files from skill/ or another allowed input source into that entry directory, then reference those copied files with entry-relative paths."
        )
    if reason == "missing_from_entry_dir":
        return (
            f"html dependency does not exist in the entry directory: {raw_value}. "
            "If this local file should ship with the HTML, copy the required files into the entry directory under project/ first "
            "and then reference those copied files with entry-relative paths."
        )
    return f"html dependency is invalid: {raw_value}"


def _is_external_or_special_html_reference(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped.startswith(("#", "data:", "blob:")):
        return True
    if stripped.startswith("//"):
        return True
    return (
        _looks_like_email_reference(stripped)
        or _looks_like_external_url_reference(stripped)
        or _has_non_file_scheme(stripped)
    )


def _looks_like_email_reference(value: str) -> bool:
    if any(separator in value for separator in ("/", "\\", "?", "#")):
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def _has_non_file_scheme(value: str) -> bool:
    if _looks_like_absolute_local_reference(value):
        return False
    split = urlsplit(value)
    return bool(split.scheme or split.netloc)


_COMMON_EXTERNAL_TLDS = {
    "app",
    "biz",
    "cn",
    "co",
    "com",
    "dev",
    "edu",
    "io",
    "me",
    "net",
    "org",
    "site",
    "top",
    "xyz",
}


def _looks_like_external_url_reference(value: str) -> bool:
    if value.startswith(("./", "../", "/", "\\")):
        return False
    first_segment = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip().lower()
    if not first_segment or "." not in first_segment:
        return False
    tld = first_segment.rsplit(".", 1)[-1]
    return tld in _COMMON_EXTERNAL_TLDS


def _looks_like_absolute_local_reference(value: str) -> bool:
    if value.startswith("/"):
        return True
    if value.lower().startswith("file://"):
        return True
    return bool(re.match(r"^[a-zA-Z]:[/\\]", value))


def _resolve_local_html_dependency(base_dir: Path, value: str) -> Path | None:
    relative_part = urlsplit(value).path
    normalized = relative_part.replace("\\", "/").strip()
    if not normalized:
        return None
    entry = (base_dir / normalized).resolve()
    try:
        entry.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return entry


def _validate_js_module(path: Path, kind: str) -> dict[str, Any]:
    if shutil.which("node"):
        completed = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "invalid javascript module").strip()
            return _result(False, kind, [message])
        return _result(True, kind)
    return _validate_js_module_text(path.read_text(encoding="utf-8"), kind)


def _validate_js_module_text(content: str, kind: str) -> dict[str, Any]:
    if not content.strip():
        return _result(False, kind, ["javascript module content is empty"])
    if "\x00" in content:
        return _result(False, kind, ["javascript module contains binary data"])
    return _result(True, kind)


def _validate_office_zip(path: Path, kind: str) -> dict[str, Any]:
    if not zipfile.is_zipfile(path):
        return _result(False, kind, ["office entry is not a valid zip package"])
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    if "[Content_Types].xml" not in names:
        return _result(False, kind, ["office entry is missing [Content_Types].xml"])
    return _result(True, kind)


def _kind_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".js", ".mjs", ".cjs"}:
        return "js_module"
    if suffix == ".docx":
        return "document"
    if suffix in {".xlsx", ".csv"}:
        return "sheet"
    if suffix == ".pptx":
        return "presentation"
    return "text"


def _normalize_kind(kind: str) -> str:
    mapping = {
        "text": "text",
        "json": "json",
        "jsonl": "jsonl",
        "markdown": "markdown",
        "html": "html",
        "js_module": "js_module",
        "javascript": "js_module",
        "document": "document",
        "sheet": "sheet",
        "presentation": "presentation",
    }
    return mapping.get(str(kind or "").strip().lower(), "text")


def _result(valid: bool, kind: str, errors: list[str] | None = None) -> dict[str, Any]:
    return {"valid": valid, "kind": kind, "errors": errors or []}
