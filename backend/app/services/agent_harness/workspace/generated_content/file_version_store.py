from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir
from app.services.agent_harness.runtime.state.versioned_file_state import (
    HarnessFileVersion,
    HarnessVersionedFile,
    versioned_file_from_dict,
    versioned_file_to_dict,
)


_TYPE_BY_SUFFIX = {
    ".md": "markdown",
    ".txt": "text",
    ".doc": "document",
    ".docx": "document",
    ".xls": "sheet",
    ".xlsx": "sheet",
    ".csv": "sheet",
    ".ppt": "presentation",
    ".pptx": "presentation",
    ".html": "html",
    ".htm": "html",
    ".js": "js_module",
    ".mjs": "js_module",
    ".cjs": "js_module",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
}

_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conversation_root(user_id: int, conversation_id: str) -> Path:
    return get_conversation_dir(user_id, conversation_id).resolve()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _ensure_inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guess_file_type(name: str) -> str:
    return _TYPE_BY_SUFFIX.get(Path(name).suffix.lower(), "other")


def _safe_file_id(name: str) -> str:
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:10]
    return f"f_{digest}"


def _manifest_path(root: Path, file_id: str) -> Path:
    return root / "published" / file_id / "manifest.json"


@contextmanager
def _version_lock(root: Path, lock_key: str):
    locks_dir = root / ".meta" / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    safe_key = hashlib.sha1(lock_key.encode("utf-8")).hexdigest()[:16]
    lock_path = locks_dir / f"file_version_{safe_key}.lock"
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    handle: int | None = None
    while True:
        try:
            handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(handle, f"{os.getpid()}\n".encode("ascii", errors="ignore"))
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for file version lock: {lock_key}")
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        if handle is not None:
            os.close(handle)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _load_manifest(root: Path, file_id: str) -> HarnessVersionedFile | None:
    path = _manifest_path(root, file_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return versioned_file_from_dict(payload)


def _save_manifest(root: Path, file: HarnessVersionedFile) -> None:
    path = _manifest_path(root, file.file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(versioned_file_to_dict(file), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _next_version_id(file: HarnessVersionedFile | None) -> str:
    if file is None:
        return "v0001"
    return f"v{len(file.versions) + 1:04d}"


def _unique_file_id(root: Path, name: str) -> str:
    base = _safe_file_id(name)
    candidate = base
    counter = 2
    while _manifest_path(root, candidate).exists():
        existing = _load_manifest(root, candidate)
        if existing and existing.name == name:
            return candidate
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def list_versioned_files(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    root = _conversation_root(user_id, conversation_id)
    versions_root = root / "published"
    if not versions_root.exists():
        return []
    files: list[dict[str, Any]] = []
    for manifest in sorted(versions_root.glob("*/manifest.json")):
        item = _load_manifest(root, manifest.parent.name)
        if item is None:
            continue
        current = get_current_version(item)
        files.append(_to_workspace_file(root, item, current))
    return files


def get_versioned_file(user_id: int, conversation_id: str, file_id: str) -> HarnessVersionedFile:
    root = _conversation_root(user_id, conversation_id)
    file = _load_manifest(root, file_id)
    if file is None:
        raise FileNotFoundError(file_id)
    return file


def get_current_version(file: HarnessVersionedFile) -> HarnessFileVersion | None:
    for version in file.versions:
        if version.version_id == file.current_version_id:
            return version
    return file.versions[-1] if file.versions else None


def resolve_version_path(
    user_id: int,
    conversation_id: str,
    file_id: str,
    version_id: str | None = None,
) -> Path:
    root = _conversation_root(user_id, conversation_id)
    file = get_versioned_file(user_id, conversation_id, file_id)
    target_version_id = version_id or file.current_version_id
    for version in file.versions:
        if version.version_id == target_version_id:
            path = _ensure_inside(root, root / version.file_path)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(version.file_path)
            return path
    raise FileNotFoundError(target_version_id or file_id)


def append_file_version(
    user_id: int,
    conversation_id: str,
    *,
    source_path: Path,
    name: str | None = None,
    file_id: str | None = None,
    file_type: str | None = None,
    run_id: str | None = None,
    parent_version_id: str | None = None,
    parent_input_asset_ids: list[str] | None = None,
    referenced_asset_ids: list[str] | None = None,
    note: str | None = None,
    artifact_metadata: dict[str, Any] | None = None,
    created_by: str = "agent",
) -> dict[str, Any]:
    root = _conversation_root(user_id, conversation_id)
    resolved_source = _ensure_inside(root, source_path)
    if not resolved_source.exists() or not resolved_source.is_file():
        raise FileNotFoundError(str(source_path))
    display_name = name or resolved_source.name
    lock_key = file_id or _safe_file_id(display_name)
    with _version_lock(root, lock_key):
        target_file_id = file_id or _unique_file_id(root, display_name)
        existing = _load_manifest(root, target_file_id)
        if existing is not None and existing.name != display_name:
            raise ValueError(f"file_id belongs to another file: {target_file_id}")

        now = _now()
        version_id = _next_version_id(existing)
        suffix = Path(display_name).suffix or resolved_source.suffix
        version_dir = root / "published" / target_file_id / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        version_path = version_dir / f"source{suffix}"
        shutil.copy2(resolved_source, version_path)

        version = HarnessFileVersion(
            version_id=version_id,
            label=f"版本 {int(version_id.removeprefix('v'))}",
            file_path=_relative(root, version_path),
            mirror_path=None,
            size=version_path.stat().st_size,
            sha256=_sha256_file(version_path),
            created_at=now,
            created_by=created_by,
            run_id=run_id,
            parent_version_id=parent_version_id,
            parent_input_asset_ids=parent_input_asset_ids or [],
            referenced_asset_ids=referenced_asset_ids or [],
            note=note,
            artifact_metadata=dict(artifact_metadata or {}),
        )

        if existing is None:
            file = HarnessVersionedFile(
                file_id=target_file_id,
                name=display_name,
                type=file_type or guess_file_type(display_name),
                current_version_id=version_id,
                created_at=now,
                updated_at=now,
                versions=[version],
            )
        else:
            file = HarnessVersionedFile(
                file_id=existing.file_id,
                name=existing.name,
                type=file_type or existing.type,
                current_version_id=version_id,
                created_at=existing.created_at,
                updated_at=now,
                versions=[*existing.versions, version],
            )
        _save_manifest(root, file)
        workspace_file = _to_workspace_file(root, file, version)
        from app.services.agent_harness.workspace.session_v2.service import upsert_workspace_file

        upsert_workspace_file(user_id, conversation_id, {**workspace_file, "source": "versioned_file"})
        return workspace_file


def set_current_version(
    user_id: int,
    conversation_id: str,
    file_id: str,
    version_id: str,
) -> dict[str, Any]:
    root = _conversation_root(user_id, conversation_id)
    with _version_lock(root, file_id):
        file = get_versioned_file(user_id, conversation_id, file_id)
        selected = None
        for version in file.versions:
            if version.version_id == version_id:
                selected = version
                break
        if selected is None:
            raise FileNotFoundError(version_id)

        updated = HarnessVersionedFile(
            file_id=file.file_id,
            name=file.name,
            type=file.type,
            current_version_id=version_id,
            created_at=file.created_at,
            updated_at=_now(),
            versions=file.versions,
        )
        _save_manifest(root, updated)
        workspace_file = _to_workspace_file(root, updated, selected)
        from app.services.agent_harness.workspace.session_v2.service import upsert_workspace_file

        upsert_workspace_file(user_id, conversation_id, {**workspace_file, "source": "versioned_file"})
        return workspace_file


def _to_workspace_file(
    root: Path,
    file: HarnessVersionedFile,
    current: HarnessFileVersion | None,
) -> dict[str, Any]:
    size = current.size if current else 0
    current_path = current.file_path if current else None
    current_artifact_metadata = current.artifact_metadata if current else {}
    artifact_kind = str(current_artifact_metadata.get("artifact_kind") or "file")
    return {
        "file_id": file.file_id,
        "name": file.name,
        "path": current_path,
        "type": file.type,
        "size": size,
        "created_at": file.created_at,
        "updated_at": file.updated_at,
        "current_version_id": file.current_version_id,
        "current_version_path": current_path,
        "artifact_kind": artifact_kind,
        "artifact_metadata": current_artifact_metadata,
        "versions": [
            {
                "version_id": version.version_id,
                "label": version.label,
                "size": version.size,
                "sha256": version.sha256,
                "created_at": version.created_at,
                "created_by": version.created_by,
                "run_id": version.run_id,
                "parent_version_id": version.parent_version_id,
                "parent_input_asset_ids": version.parent_input_asset_ids,
                "referenced_asset_ids": version.referenced_asset_ids,
                "note": version.note,
                "artifact_metadata": version.artifact_metadata,
            }
            for version in file.versions
        ],
    }


def workspace_file_event_payload(file: dict[str, Any]) -> dict[str, Any]:
    versions = file.get("versions") or []
    current_version_id = str(file.get("current_version_id") or "")
    current_version = next(
        (
            version
            for version in versions
            if str(version.get("version_id") or "") == current_version_id
        ),
        None,
    )
    version = current_version or (versions[-1] if versions else None)
    return {
        "file_id": file.get("file_id"),
        "name": file.get("name"),
        "path": file.get("path"),
        "type": file.get("type"),
        "size": file.get("size"),
        "created_at": file.get("updated_at") or file.get("created_at"),
        "current_version_id": file.get("current_version_id"),
        "artifact_kind": file.get("artifact_kind"),
        "artifact_metadata": file.get("artifact_metadata") or {},
        "entry": (file.get("artifact_metadata") or {}).get("entry"),
        "versions": versions,
        "current_version": current_version,
        "version": version,
    }
