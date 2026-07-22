from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.services.agent_harness.isolation.sandbox.path_guard import validate_cwd

from .types import ResolvedWorkspacePath
from .workspace_v2 import WorkspacePathIntent, WorkspacePathResolver

WorkspaceLocation = str

_PROJECT_RESERVED_ROOTS = {"references", "published", ".meta", "meta", ".agent", "logs", "skill", "files", "work"}
_ALLOWED_TOOL_BASES = {"work", "project", "skill", "references", "published"}
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")
MAX_TEXT_FILE_READ_BYTES = 5 * 1024 * 1024
BINARY_DETECTION_BYTES = 8192


def resolve_semantic_path(location: WorkspaceLocation, path: str, ctx) -> Path | None:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    if ".." in Path(normalized).parts:
        return None
    if location in {"root", "workspace"}:
        candidate = (ctx.conversation_dir / normalized).resolve()
    elif location == "references":
        candidate = (ctx.references_dir / normalized).resolve()
    elif location == "project":
        candidate = (ctx.project_dir / normalized).resolve()
    elif location == "published":
        candidate = (ctx.published_dir / normalized).resolve()
    elif location == "meta":
        candidate = (ctx.meta_dir / normalized).resolve()
    elif location == "skill":
        active_skill_dir = getattr(ctx, "active_skill_dir", None) or getattr(ctx, "skill_dir", None)
        if not active_skill_dir:
            return None
        skill_root = Path(active_skill_dir).resolve()
        candidate = (skill_root / normalized).resolve()
        try:
            candidate.relative_to(skill_root)
        except ValueError:
            return None
        return candidate
    else:
        return None
    try:
        candidate.relative_to(ctx.conversation_dir.resolve())
    except ValueError:
        return None
    return candidate


def resolve_work_file_path(file_path: str, ctx, *, base: str | None = None) -> ResolvedWorkspacePath | None:
    return resolve_project_file_path(file_path, ctx, base=base)


def resolve_project_file_path(file_path: str, ctx, *, base: str | None = None) -> ResolvedWorkspacePath | None:
    raw = str(file_path or "").strip()
    if not raw:
        return None
    workspace_path = workspace_path_for_base_tool(base, raw, ctx, default_base="work") if base else workspace_path_for_project_tool(raw, ctx)
    decision = WorkspacePathResolver(ctx).resolve(workspace_path, WorkspacePathIntent.WRITE)
    if not decision.allowed or decision.resolved_path is None:
        return None
    normalized_workspace_path = str(decision.normalized_path or "")
    if not normalized_workspace_path.startswith("project/"):
        return None
    normalized = normalized_workspace_path.split("/", 1)[1]
    if not normalized or normalized in {".", "./"}:
        return None
    normalization = (decision.metadata or {}).get("path_normalization")
    warning = None
    if isinstance(normalization, dict) and normalization.get("correction_applied"):
        warning = (
            f"Normalized structured workspace path from {str(normalization.get('original_path') or raw)!r} "
            f"to {normalized!r} ({normalization.get('normalization_kind')}, "
            f"confidence={normalization.get('confidence') or 'high'})."
        )
    return ResolvedWorkspacePath(
        resolved=decision.resolved_path,
        normalized_path=normalized.replace("\\", "/"),
        location="project",
        warning=warning,
        original_path=str((normalization or {}).get("original_path") or raw) if isinstance(normalization, dict) else raw,
        audit_metadata=normalization if isinstance(normalization, dict) else None,
    )


def resolve_workspace_file_path(file_path: str, ctx) -> Path | None:
    normalized = str(file_path or "").replace("\\", "/").strip()
    if normalized.startswith("files/") or normalized in {"files", "plan.md", "./plan.md"}:
        return None
    workspace_roots = {"project", "references", "published", "skill"}
    if (
        normalized
        and normalized not in workspace_roots
        and not normalized.startswith(("project/", "references/", "published/", "skill/"))
    ):
        normalized = workspace_path_for_project_tool(normalized, ctx)
    return ctx.resolve_workspace_path(
        normalized,
        default_scope="code",
        allow_fallback_to_files=False,
    )


def normalize_tool_base(base: str | None, *, default: str = "work") -> str:
    raw = str(base if base is not None else default).replace("\\", "/").strip().strip("/")
    if raw in {"", "."}:
        raise ValueError("base must be one of work, project, skill, references, published, or project:<relative-dir>")
    if raw in _ALLOWED_TOOL_BASES:
        return raw
    if raw.startswith("project:"):
        fragment = raw.split(":", 1)[1].strip().strip("/")
        if not fragment:
            raise ValueError("project:<relative-dir> base must include a project subdirectory")
        if _invalid_relative_base_fragment(fragment):
            raise ValueError("project:<relative-dir> base must be a safe relative path under project/")
        return f"project:{fragment}"
    if raw.startswith("/") or _WINDOWS_DRIVE_RE.match(raw) or ":" in raw:
        raise ValueError("base must be a semantic root, not a filesystem path")
    raise ValueError("base must be one of work, project, skill, references, published, or project:<relative-dir>")


def resolve_tool_base(ctx, base: str | None) -> Path | None:
    try:
        raw = normalize_tool_base(base, default="work")
    except ValueError:
        return None
    if raw == "work":
        return artifact_work_dir(ctx).resolve()
    if raw == "project":
        return ctx.project_dir.resolve()
    if raw.startswith("project:"):
        project_fragment = raw.split(":", 1)[1]
        candidate = (ctx.project_dir / project_fragment).resolve()
        try:
            candidate.relative_to(ctx.project_dir.resolve())
        except ValueError:
            return None
        return candidate
    if raw == "skill":
        active_skill_dir = getattr(ctx, "active_skill_dir", None) or getattr(ctx, "skill_dir", None)
        return Path(active_skill_dir).resolve() if active_skill_dir else None
    if raw == "references":
        return ctx.references_dir.resolve()
    if raw == "published":
        return ctx.published_dir.resolve()
    return None


def workspace_path_for_base_tool(base: str | None, path: str, ctx, *, default_base: str = "work") -> str:
    raw_base = normalize_tool_base(base, default=default_base or "work")
    original_path = str(path or "").strip().lstrip("/")
    normalized_path = original_path.replace("\\", "/").strip().lstrip("/")
    while normalized_path.startswith("./"):
        normalized_path = normalized_path[2:]
    if raw_base == "work" and _has_semantic_root(normalized_path):
        return original_path
    if raw_base in {"", ".", "work"}:
        return workspace_path_for_project_tool(normalized_path or ".", ctx)
    if raw_base == "project":
        return f"project/{normalized_path}".strip("/") if normalized_path else "project"
    if raw_base.startswith("project:"):
        project_fragment = raw_base.split(":", 1)[1].strip().strip("/")
        joined = "/".join(part for part in (project_fragment, normalized_path) if part)
        return f"project/{joined}".strip("/") if joined else "project"
    if raw_base in {"skill", "references", "published"}:
        return f"{raw_base}/{normalized_path}".strip("/") if normalized_path else raw_base
    return workspace_path_for_project_tool(normalized_path or ".", ctx)


def resolve_command_cwd(ctx, cwd: str) -> Path | None:
    candidate = resolve_tool_base(ctx, cwd)
    if candidate is None:
        return None
    if not _is_under_any(candidate, allowed_cwd_roots(ctx)):
        return None
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def validate_allowed_cwd(ctx, cwd: Path) -> str | None:
    return validate_cwd(cwd, allowed_cwd_roots(ctx))


def allowed_cwd_roots(ctx) -> tuple[Path, ...]:
    active_skill_dir = getattr(ctx, "active_skill_dir", None)
    roots = [
        ctx.project_dir.resolve(),
        ctx.references_dir.resolve(),
        ctx.published_dir.resolve(),
        ctx.skill_dir.resolve(),
    ]
    if active_skill_dir:
        roots.append(Path(active_skill_dir).resolve())
    return tuple(roots)


def read_text_file(resolved: Path) -> str:
    data = resolved.read_bytes()
    if b"\x00" in data:
        raise ValueError("Binary files are not supported by this text tool")
    return data.decode("utf-8", errors="replace")


def read_text_file_window(
    resolved: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
    max_size_bytes: int = MAX_TEXT_FILE_READ_BYTES,
) -> dict[str, object]:
    size = resolved.stat().st_size
    with resolved.open("rb") as fh:
        probe = fh.read(BINARY_DETECTION_BYTES)
    if b"\x00" in probe:
        raise ValueError("Binary files are not supported by this text tool")

    if limit is not None:
        return _read_text_file_window_streaming(
            resolved,
            source_size_bytes=size,
            offset=offset,
            limit=limit,
            max_size_bytes=max_size_bytes,
        )

    if size > max_size_bytes:
        raise ValueError(
            f"File is too large ({size} bytes, max {max_size_bytes} bytes). "
            "Use offset and limit to read a smaller window, or use grep_files to search for specific content."
        )

    content = resolved.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    start_index = min(max(offset, 0), len(lines))
    end_index = len(lines)
    selected = "\n".join(lines[start_index:end_index])
    return {
        "content": selected,
        "start_line": start_index + 1,
        "num_lines": end_index - start_index,
        "total_lines": len(lines),
        "truncated_by_window": start_index > 0 or end_index < len(lines),
        "size_bytes": size,
        "max_read_size_bytes": max_size_bytes,
    }


def _read_text_file_window_streaming(
    resolved: Path,
    *,
    source_size_bytes: int,
    offset: int,
    limit: int,
    max_size_bytes: int,
) -> dict[str, object]:
    start_index = max(offset, 0)
    end_index = start_index + max(limit, 0)
    selected_lines: list[str] = []
    total_lines = 0

    with resolved.open("r", encoding="utf-8", errors="replace", newline=None) as fh:
        for line_index, line in enumerate(fh):
            total_lines = line_index + 1
            if line_index < start_index or line_index >= end_index:
                continue
            if line.endswith("\n"):
                line = line[:-1]
            if line.endswith("\r"):
                line = line[:-1]
            if line_index == 0 and line.startswith("\ufeff"):
                line = line[1:]
            selected_lines.append(line)

    actual_start = min(start_index, total_lines)
    actual_end = actual_start + len(selected_lines)
    return {
        "content": "\n".join(selected_lines),
        "start_line": actual_start + 1,
        "num_lines": len(selected_lines),
        "total_lines": total_lines,
        "truncated_by_window": actual_start > 0 or actual_end < total_lines,
        "size_bytes": source_size_bytes,
        "max_read_size_bytes": max_size_bytes,
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_under_any(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def active_artifact_work_root(ctx) -> str | None:
    workspace_session = getattr(ctx, "workspace_runtime_session", None)
    if isinstance(workspace_session, dict):
        value = _normalize_workspace_fragment(workspace_session.get("artifact_work_root"))
        if value:
            return value.removeprefix("project/").strip("/")
        agent_cwd = _normalize_workspace_fragment(workspace_session.get("agent_cwd"))
        if agent_cwd.startswith("project/"):
            return agent_cwd.removeprefix("project/").strip("/") or None
    session = getattr(ctx, "prepared_workspace", None)
    value = _normalize_workspace_fragment(getattr(session, "artifact_work_root", None))
    if value:
        return value.removeprefix("project/").strip("/")
    value = _normalize_workspace_fragment(getattr(ctx, "artifact_work_root", None))
    if value:
        return value.removeprefix("project/").strip("/")
    return None


def artifact_work_project_path(ctx) -> str | None:
    root = active_artifact_work_root(ctx)
    return f"project/{root}" if root else None


def artifact_work_dir(ctx) -> Path:
    root = active_artifact_work_root(ctx)
    return (ctx.project_dir / root).resolve() if root else ctx.project_dir.resolve()


def workspace_path_for_project_tool(raw: str, ctx) -> str:
    original = str(raw or "").strip().lstrip("/")
    collapsed = original.replace("\\", "/")
    first = collapsed.split("/", 1)[0]
    if first in {"project", "references", "skill", "published", ".agent", ".meta", "logs", "work"}:
        return original
    root = active_artifact_work_root(ctx)
    if root:
        if collapsed in {"", "."}:
            return f"project/{root}"
        while collapsed.startswith("./"):
            collapsed = collapsed[2:]
        if collapsed == root or collapsed.startswith(f"{root}/"):
            return f"project/{collapsed}".strip("/")
        return f"project/{root}/{collapsed}".strip("/")
    return f"project/{original}".strip("/")


def workspace_path_for_location(location: str, path: str, ctx) -> str:
    normalized_location = str(location or "root").strip().strip("/") or "root"
    normalized_path = str(path or "").replace("\\", "/").strip().lstrip("/")
    if normalized_location in {"root", "workspace"}:
        if _has_semantic_root(normalized_path):
            return normalized_path
        return workspace_path_for_project_tool(normalized_path or ".", ctx)
    if normalized_location == "project":
        if _has_semantic_root(normalized_path):
            return normalized_path
        return workspace_path_for_project_tool(normalized_path or ".", ctx)
    if normalized_path == normalized_location or normalized_path.startswith(f"{normalized_location}/"):
        return normalized_path
    return f"{normalized_location}/{normalized_path}".strip("/")


def _has_semantic_root(path: str) -> bool:
    first = str(path or "").replace("\\", "/").strip().lstrip("/").split("/", 1)[0]
    return first in {"project", "references", "skill", "published", ".agent", ".meta", "logs", "work"}


def _invalid_relative_base_fragment(fragment: str) -> bool:
    normalized = str(fragment or "").replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or _WINDOWS_DRIVE_RE.match(normalized):
        return True
    return ".." in Path(normalized).parts


def _normalize_workspace_fragment(value) -> str:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")
