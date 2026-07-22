from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir

AssetKind = Literal["input", "reference"]
_ASSET_LOCK_TIMEOUT_SECONDS = 10.0
_ASSET_LOCK_POLL_SECONDS = 0.05


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _conversation_root(user_id: int, conversation_id: str) -> Path:
    return get_conversation_dir(user_id, conversation_id).resolve()


def _manifest_path(root: Path) -> Path:
    return root / ".meta" / "assets_manifest.json"


def _load_manifest(root: Path) -> dict[str, Any]:
    path = _manifest_path(root)
    if not path.exists():
        return {"assets": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"assets": []}
    if not isinstance(payload, dict):
        return {"assets": []}
    assets = payload.get("assets")
    return {"assets": assets if isinstance(assets, list) else []}


def _save_manifest(root: Path, payload: dict[str, Any]) -> None:
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp_path.write_text(
        json.dumps(sanitize_persistent_payload(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


@contextmanager
def _asset_manifest_lock(root: Path):
    locks_dir = root / ".meta" / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / "assets_manifest.lock"
    deadline = time.monotonic() + _ASSET_LOCK_TIMEOUT_SECONDS
    handle: int | None = None
    while True:
        try:
            handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(handle, f"{os.getpid()}\n".encode("ascii", errors="ignore"))
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for asset manifest lock")
            time.sleep(_ASSET_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        if handle is not None:
            os.close(handle)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _next_asset_id(root: Path, prefix: str) -> str:
    manifest = _load_manifest(root)
    existing = {
        str(asset.get("asset_id"))
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict)
    }
    counter = 1
    while True:
        candidate = f"{prefix}_{counter:03d}"
        if candidate not in existing:
            return candidate
        counter += 1


def planned_reference_asset_path(
    user_id: int,
    conversation_id: str,
    *,
    asset_id: str,
    extension: str,
) -> str:
    root = _conversation_root(user_id, conversation_id)
    suffix = extension if extension.startswith(".") else f".{extension}"
    return (_asset_folder(root, "reference", "generated") / asset_id / f"original{suffix}").relative_to(root).as_posix()


def _asset_prefix(kind: AssetKind, source: str | None) -> str:
    if kind == "input":
        return "upload"
    if source == "image":
        return "generated_image"
    if source == "video":
        return "generated_video"
    return "web_image"


def _reference_bucket(source: str | None) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in {"image", "video", "audio", "chart"}:
        return "generated"
    if normalized.startswith("generated_"):
        return "generated"
    return "sources"


def _asset_folder(root: Path, kind: AssetKind, source: str | None) -> Path:
    if kind == "input":
        return root / "references" / "inputs"
    if _reference_bucket(source) == "generated":
        return root / "references" / "generated"
    return root / "references" / "sources"


def list_assets(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    root = _conversation_root(user_id, conversation_id)
    return [
        asset
        for asset in _load_manifest(root).get("assets", [])
        if isinstance(asset, dict)
    ]


def register_asset(
    user_id: int,
    conversation_id: str,
    *,
    source_path: Path,
    kind: AssetKind,
    original_name: str,
    mime_type: str | None = None,
    source: str | None = None,
    source_url: str | None = None,
    run_id: str | None = None,
    asset_id: str | None = None,
) -> dict[str, Any]:
    root = _conversation_root(user_id, conversation_id)
    resolved_source = source_path.resolve()
    resolved_source.relative_to(root)
    if not resolved_source.exists() or not resolved_source.is_file():
        raise FileNotFoundError(str(source_path))

    with _asset_manifest_lock(root):
        prefix = _asset_prefix(kind, source)
        asset_id = asset_id or _next_asset_id(root, prefix)
        suffix = Path(original_name).suffix or resolved_source.suffix
        folder = _asset_folder(root, kind, source) / asset_id
        folder.mkdir(parents=True, exist_ok=True)
        filename = "original" if kind == "reference" else "source"
        target = folder / f"{filename}{suffix}"
        shutil.copy2(resolved_source, target)

        payload = {
            "asset_id": asset_id,
            "kind": kind,
            "original_name": original_name,
            "path": target.relative_to(root).as_posix(),
            "mime_type": mime_type,
            "sha256": _sha256_file(target),
            "size": target.stat().st_size,
            "source": source or kind,
            "source_url": source_url,
            "run_id": run_id,
            "created_at": _now(),
        }
        (folder / "metadata.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest = _load_manifest(root)
        manifest["assets"] = [
            item for item in manifest.get("assets", [])
            if not isinstance(item, dict) or item.get("asset_id") != asset_id
        ]
        manifest["assets"].append(payload)
        _save_manifest(root, manifest)
    from app.services.agent_harness.workspace.session_v2.service import upsert_workspace_asset

    upsert_workspace_asset(user_id, conversation_id, payload)
    return payload


def register_asset_bytes(
    user_id: int,
    conversation_id: str,
    *,
    content: bytes,
    kind: AssetKind,
    original_name: str,
    mime_type: str | None = None,
    source: str | None = None,
    source_url: str | None = None,
    run_id: str | None = None,
    asset_id: str | None = None,
) -> dict[str, Any]:
    root = _conversation_root(user_id, conversation_id)
    with _asset_manifest_lock(root):
        prefix = _asset_prefix(kind, source)
        asset_id = asset_id or _next_asset_id(root, prefix)
        suffix = Path(original_name).suffix
        folder = _asset_folder(root, kind, source) / asset_id
        folder.mkdir(parents=True, exist_ok=True)
        filename = "original" if kind == "reference" else "source"
        target = folder / f"{filename}{suffix}"
        tmp_target = folder / f".{target.name}.part"
        tmp_target.write_bytes(content)
        tmp_target.replace(target)

        payload = {
            "asset_id": asset_id,
            "kind": kind,
            "original_name": original_name,
            "path": target.relative_to(root).as_posix(),
            "mime_type": mime_type,
            "sha256": _sha256_bytes(content),
            "size": len(content),
            "source": source or kind,
            "source_url": source_url,
            "run_id": run_id,
            "created_at": _now(),
        }
        (folder / "metadata.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest = _load_manifest(root)
        manifest["assets"] = [
            item for item in manifest.get("assets", [])
            if not isinstance(item, dict) or item.get("asset_id") != asset_id
        ]
        manifest["assets"].append(payload)
        _save_manifest(root, manifest)
    from app.services.agent_harness.workspace.session_v2.service import upsert_workspace_asset

    upsert_workspace_asset(user_id, conversation_id, payload)
    return payload
