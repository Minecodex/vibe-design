from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.core.config import settings


_LEASE_GRACE_NS = 2_000_000_000


@dataclass(frozen=True)
class SystemWriteLease:
    lease_id: str
    user_id: int
    conversation_id: str
    owner: str
    paths: tuple[str, ...]
    started_at_ns: int
    expires_at_ns: int
    finished_at_ns: int | None = None
    run_id: str | None = None
    tool_call_id: str | None = None


def _lease_root(workspace_root: Path | None = None) -> Path:
    root = Path(workspace_root or getattr(settings, "HARNESS_WORKSPACE_ROOT", "uploads/harness")).expanduser().resolve()
    return root / ".system" / "effect_leases"


def _lease_path(lease_id: str, *, workspace_root: Path | None = None) -> Path:
    return _lease_root(workspace_root) / f"{lease_id}.json"


def _write_lease(lease: SystemWriteLease, *, workspace_root: Path | None = None) -> None:
    root = _lease_root(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "lease_id": lease.lease_id,
        "user_id": lease.user_id,
        "conversation_id": lease.conversation_id,
        "owner": lease.owner,
        "paths": list(lease.paths),
        "started_at_ns": lease.started_at_ns,
        "expires_at_ns": lease.expires_at_ns,
        "finished_at_ns": lease.finished_at_ns,
        "run_id": lease.run_id,
        "tool_call_id": lease.tool_call_id,
    }
    target = _lease_path(lease.lease_id, workspace_root=workspace_root)
    temp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(target)


def _cleanup_expired_leases(*, now_ns: int | None = None, workspace_root: Path | None = None) -> None:
    now = int(now_ns if now_ns is not None else time.time_ns())
    root = _lease_root(workspace_root)
    if not root.exists():
        return
    for path in list(root.glob("*.json")):
        lease = _load_lease(path)
        if lease is None:
            continue
        if lease.expires_at_ns + _LEASE_GRACE_NS < now:
            _best_effort_unlink(path)


def register_system_write_lease(
    *,
    user_id: int,
    conversation_id: str,
    owner: str,
    paths: list[str] | tuple[str, ...],
    ttl_seconds: float = 30.0,
    run_id: str | None = None,
    tool_call_id: str | None = None,
    workspace_root: Path | None = None,
) -> SystemWriteLease:
    now = time.time_ns()
    _cleanup_expired_leases(now_ns=now, workspace_root=workspace_root)
    normalized_paths = tuple(sorted({_normalize_conversation_path(path) for path in paths if _normalize_conversation_path(path)}))
    lease = SystemWriteLease(
        lease_id=uuid.uuid4().hex,
        user_id=int(user_id),
        conversation_id=str(conversation_id),
        owner=str(owner),
        paths=normalized_paths,
        started_at_ns=now,
        expires_at_ns=now + int(max(float(ttl_seconds or 1), 1.0) * 1_000_000_000),
        run_id=str(run_id) if run_id else None,
        tool_call_id=str(tool_call_id) if tool_call_id else None,
    )
    _write_lease(lease, workspace_root=workspace_root)
    return lease


def finish_system_write_lease(lease: SystemWriteLease, *, workspace_root: Path | None = None) -> SystemWriteLease:
    finished = SystemWriteLease(
        lease_id=lease.lease_id,
        user_id=lease.user_id,
        conversation_id=lease.conversation_id,
        owner=lease.owner,
        paths=lease.paths,
        started_at_ns=lease.started_at_ns,
        expires_at_ns=lease.expires_at_ns,
        finished_at_ns=time.time_ns(),
        run_id=lease.run_id,
        tool_call_id=lease.tool_call_id,
    )
    _write_lease(finished, workspace_root=workspace_root)
    return finished


@contextmanager
def system_write_lease(
    *,
    user_id: int,
    conversation_id: str,
    owner: str,
    paths: list[str] | tuple[str, ...],
    ttl_seconds: float = 30.0,
    run_id: str | None = None,
    tool_call_id: str | None = None,
    workspace_root: Path | None = None,
) -> Iterator[SystemWriteLease]:
    lease = register_system_write_lease(
        user_id=user_id,
        conversation_id=conversation_id,
        owner=owner,
        paths=paths,
        ttl_seconds=ttl_seconds,
        run_id=run_id,
        tool_call_id=tool_call_id,
        workspace_root=workspace_root,
    )
    try:
        yield lease
    finally:
        finish_system_write_lease(lease, workspace_root=workspace_root)


def is_system_write_leased(
    *,
    user_id: int,
    conversation_id: str,
    conversation_path: str,
    changed_mtime_ns: int | None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
    workspace_root: Path | None = None,
) -> bool:
    normalized_path = _normalize_conversation_path(conversation_path)
    if not normalized_path:
        return False
    now = time.time_ns()
    root = _lease_root(workspace_root)
    if not root.exists():
        return False
    for path in list(root.glob("*.json")):
        lease = _load_lease(path)
        if lease is None:
            continue
        if lease.expires_at_ns + _LEASE_GRACE_NS < now:
            _best_effort_unlink(path)
            continue
        if lease.user_id != int(user_id) or lease.conversation_id != str(conversation_id):
            continue
        if lease.run_id is not None and lease.run_id != (str(run_id) if run_id else None):
            continue
        if lease.tool_call_id is not None and lease.tool_call_id != (str(tool_call_id) if tool_call_id else None):
            continue
        if not _path_matches_leased_path(normalized_path, lease.paths):
            continue
        if changed_mtime_ns is None:
            continue
        window_end = lease.finished_at_ns or lease.expires_at_ns
        if lease.started_at_ns - _LEASE_GRACE_NS <= int(changed_mtime_ns) <= window_end + _LEASE_GRACE_NS:
            return True
    return False


def _load_lease(path: Path) -> SystemWriteLease | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return SystemWriteLease(
            lease_id=str(payload.get("lease_id") or path.stem),
            user_id=int(payload.get("user_id")),
            conversation_id=str(payload.get("conversation_id")),
            owner=str(payload.get("owner") or "system"),
            paths=tuple(str(item) for item in list(payload.get("paths") or [])),
            started_at_ns=int(payload.get("started_at_ns")),
            expires_at_ns=int(payload.get("expires_at_ns")),
            finished_at_ns=int(payload["finished_at_ns"]) if payload.get("finished_at_ns") is not None else None,
            run_id=str(payload.get("run_id")) if payload.get("run_id") else None,
            tool_call_id=str(payload.get("tool_call_id")) if payload.get("tool_call_id") else None,
        )
    except (TypeError, ValueError):
        return None


def _normalize_conversation_path(path: str | Path | None) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _path_matches_leased_path(path: str, leased_paths: tuple[str, ...]) -> bool:
    if path in leased_paths:
        return True
    for leased in leased_paths:
        if _is_sqlite_sidecar(path, leased):
            return True
    return False


def _is_sqlite_sidecar(path: str, leased_path: str) -> bool:
    if not leased_path.endswith((".sqlite", ".sqlite3", ".db")):
        return False
    return path in {
        f"{leased_path}-journal",
        f"{leased_path}-wal",
        f"{leased_path}-shm",
    }


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
