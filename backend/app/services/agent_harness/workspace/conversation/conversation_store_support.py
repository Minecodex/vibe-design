"""Shared low-level helpers for HomeHarness conversation storage."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.core.config import settings


def is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def workspace_root() -> Path:
    root = getattr(settings, "HARNESS_WORKSPACE_ROOT", "workspace")
    return Path(root).expanduser().resolve()


def user_conversations_dir(user_id: int) -> Path:
    return workspace_root() / "users" / str(user_id) / "conversations"


def project_user_conversations_dir(user_id: int, project_id: int) -> Path:
    return workspace_root() / "project" / str(project_id) / "users" / str(user_id) / "conversations"


def normalize_runtime_scope(
    runtime_profile: str | None,
    project_id: int | None = None,
    *,
    require_project_for_canvas: bool = False,
) -> tuple[str, int | None]:
    normalized_profile = str(runtime_profile or "home").strip().lower() or "home"
    if normalized_profile not in {"home", "canvas"}:
        normalized_profile = "home"

    normalized_project_id: int | None = None
    if project_id is not None:
        try:
            normalized_project_id = int(project_id)
        except (TypeError, ValueError):
            normalized_project_id = None

    if normalized_profile == "canvas":
        if require_project_for_canvas and normalized_project_id is None:
            raise ValueError("project_id is required for canvas runtime profile")
        return "canvas", normalized_project_id

    return "home", None


def conversations_dir_for_scope(
    user_id: int,
    *,
    runtime_profile: str | None = None,
    project_id: int | None = None,
) -> Path:
    normalized_profile, normalized_project_id = normalize_runtime_scope(runtime_profile, project_id)
    if normalized_profile == "canvas":
        if normalized_project_id is None:
            raise ValueError("project_id is required for canvas runtime profile")
        return project_user_conversations_dir(user_id, normalized_project_id)
    return user_conversations_dir(user_id)


def infer_runtime_scope_from_conversation_dir(user_id: int, conversation_dir: Path) -> tuple[str, int | None]:
    resolved = conversation_dir.resolve()
    home_root = user_conversations_dir(user_id).resolve()
    try:
        resolved.relative_to(home_root)
        return "home", None
    except ValueError:
        pass

    projects_root = workspace_root() / "project"
    try:
        relative = resolved.relative_to(projects_root.resolve())
    except ValueError:
        return "home", None

    parts = relative.parts
    if len(parts) >= 5 and parts[1] == "users" and parts[2] == str(user_id) and parts[3] == "conversations":
        try:
            return "canvas", int(parts[0])
        except (TypeError, ValueError):
            return "canvas", None
    return "home", None


def _resolve_existing_conversation_dir(user_id: int, conversation_id: str) -> Path | None:
    home_dir = user_conversations_dir(user_id) / str(conversation_id)
    if home_dir.exists():
        return home_dir

    project_root = workspace_root() / "project"
    if not project_root.exists():
        return None

    matches = list(project_root.glob(f"*/users/{user_id}/conversations/{conversation_id}"))
    if not matches:
        return None
    return matches[0]


def get_conversation_dir(
    user_id: int,
    conversation_id: str,
    *,
    runtime_profile: str | None = None,
    project_id: int | None = None,
) -> Path:
    normalized_profile = str(runtime_profile or "").strip().lower()
    if normalized_profile:
        return conversations_dir_for_scope(
            user_id,
            runtime_profile=normalized_profile,
            project_id=project_id,
        ) / str(conversation_id)

    resolved = _resolve_existing_conversation_dir(user_id, conversation_id)
    if resolved is not None:
        return resolved
    return user_conversations_dir(user_id) / str(conversation_id)


def generate_conversation_id() -> str:
    ts = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}_{suffix}"


def read_json(path: Path) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.01 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Failed to read JSON from {path}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sanitize_persistent_payload(data), ensure_ascii=False, indent=2)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def guess_workspace_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".pptx": "pptx",
        ".ppt": "pptx",
        ".docx": "docx",
        ".doc": "docx",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".csv": "xlsx",
        ".html": "web",
        ".htm": "web",
        ".py": "code",
        ".js": "code",
        ".ts": "code",
        ".json": "code",
        ".md": "text",
        ".txt": "text",
        ".pdf": "docx",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".svg": "image",
        ".webp": "image",
        ".gif": "image",
        ".mp4": "video",
        ".mov": "video",
        ".avi": "video",
    }
    return mapping.get(suffix, "file")


__all__ = [
    "conversations_dir_for_scope",
    "generate_conversation_id",
    "get_conversation_dir",
    "guess_workspace_file_type",
    "infer_runtime_scope_from_conversation_dir",
    "is_within_path",
    "normalize_runtime_scope",
    "project_user_conversations_dir",
    "read_json",
    "user_conversations_dir",
    "workspace_root",
    "write_json",
]
