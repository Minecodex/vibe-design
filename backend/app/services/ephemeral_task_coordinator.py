from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.redis_coordination import get_redis_coordinator

DEFAULT_EPHEMERAL_TASK_TTL_SECONDS = 300.0
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(authorization|cookie|prompt|content|body|token|secret|password|api[_-]?key|signed[_-]?url|signature)"
)
_SIGNED_URL_RE = re.compile(r"(?i)(x-amz-signature|x-goog-signature|signature=|token=|access_token=)")
_SECRET_VALUE_RE = re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9_\-]{8,})\b")
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/[^/]+/)")


@dataclass(frozen=True)
class EphemeralTaskKey:
    domain: str
    kind: str
    resource_parts: tuple[str, ...] = ()
    version: str = "default"

    @classmethod
    def build(
        cls,
        *,
        domain: str,
        kind: str,
        resource_parts: list[object] | tuple[object, ...] = (),
        version: object = "default",
    ) -> "EphemeralTaskKey":
        return cls(
            domain=str(domain or "default"),
            kind=str(kind or "task"),
            resource_parts=tuple(str(part or "") for part in resource_parts),
            version=str(version or "default"),
        )


@dataclass(frozen=True)
class EphemeralTaskSnapshot:
    status: str
    owner: str | None = None
    version: str | None = None
    started_at: int | None = None
    finished_at: int | None = None
    result: dict[str, Any] | None = None
    error_type: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "EphemeralTaskSnapshot | None":
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        return cls(
            status=str(payload.get("status") or "unknown"),
            owner=str(payload.get("owner") or "") or None,
            version=str(payload.get("version") or "") or None,
            started_at=_int_or_none(payload.get("started_at")),
            finished_at=_int_or_none(payload.get("finished_at")),
            result=dict(result) if isinstance(result, dict) else None,
            error_type=str(payload.get("error_type") or "") or None,
            raw=dict(payload),
        )


@dataclass(frozen=True)
class EphemeralTaskLease:
    acquired: bool
    task: EphemeralTaskKey
    key: str
    status_key: str
    owner: str
    snapshot: EphemeralTaskSnapshot | None = None

    @property
    def status(self) -> dict[str, Any] | None:
        return self.snapshot.raw if self.snapshot is not None else None


class EphemeralTaskCoordinator:
    def __init__(self, *, ttl_seconds: float = DEFAULT_EPHEMERAL_TASK_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds

    def keys_for(self, task: EphemeralTaskKey) -> tuple[str, str]:
        coordinator = get_redis_coordinator()
        resource_parts = [task.kind, *task.resource_parts, task.version]
        lease_key = coordinator.keys.build(
            domain=task.domain,
            purpose="task-lease",
            resource_parts=resource_parts,
        )
        status_key = coordinator.keys.build(
            domain=task.domain,
            purpose="task-status",
            resource_parts=resource_parts,
        )
        return lease_key, status_key

    async def read(self, task: EphemeralTaskKey) -> EphemeralTaskSnapshot | None:
        _lease_key, status_key = self.keys_for(task)
        payload = await get_redis_coordinator().get_snapshot(status_key)
        return EphemeralTaskSnapshot.from_payload(payload)

    async def start(
        self,
        task: EphemeralTaskKey,
        *,
        ttl_seconds: float | None = None,
        owner_prefix: str = "task",
        status_payload: dict[str, Any] | None = None,
    ) -> EphemeralTaskLease:
        ttl = _ttl(ttl_seconds, self.ttl_seconds)
        lease_key, status_key = self.keys_for(task)
        existing = await self.read(task)
        if existing is not None and existing.status in {"running", "done"}:
            return EphemeralTaskLease(
                acquired=False,
                task=task,
                key=lease_key,
                status_key=status_key,
                owner=existing.owner or "",
                snapshot=existing,
            )
        owner = f"{owner_prefix}:{uuid.uuid4().hex}"
        lease = await get_redis_coordinator().try_acquire_lease(
            lease_key,
            owner=owner,
            ttl_seconds=ttl,
        )
        if not lease.get("acquired"):
            snapshot = await self.read(task)
            return EphemeralTaskLease(
                acquired=False,
                task=task,
                key=lease_key,
                status_key=status_key,
                owner=str(lease.get("owner") or ""),
                snapshot=snapshot,
            )

        await get_redis_coordinator().set_snapshot(
            status_key,
            _compact_payload(
                {
                    "status": "running",
                    "owner": owner,
                    "version": task.version,
                    "started_at": int(time.time()),
                    **(status_payload or {}),
                }
            ),
            ttl_seconds=ttl,
        )
        return EphemeralTaskLease(
            acquired=True,
            task=task,
            key=lease_key,
            status_key=status_key,
            owner=owner,
        )

    async def finish(
        self,
        lease: EphemeralTaskLease,
        *,
        status: str = "done",
        result: dict[str, Any] | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        await get_redis_coordinator().set_snapshot(
            lease.status_key,
            _compact_payload(
                {
                    "status": str(status or "done"),
                    "owner": lease.owner,
                    "version": lease.task.version,
                    "finished_at": int(time.time()),
                    "result": result or {},
                }
            ),
            ttl_seconds=_ttl(ttl_seconds, self.ttl_seconds),
        )
        await get_redis_coordinator().release_lease(lease.key, owner=lease.owner)

    async def fail(
        self,
        lease: EphemeralTaskLease,
        *,
        error_type: str,
        ttl_seconds: float | None = None,
    ) -> None:
        await get_redis_coordinator().set_snapshot(
            lease.status_key,
            _compact_payload(
                {
                    "status": "failed",
                    "owner": lease.owner,
                    "version": lease.task.version,
                    "error_type": str(error_type or "ephemeral_task_failed"),
                    "finished_at": int(time.time()),
                }
            ),
            ttl_seconds=_ttl(ttl_seconds, self.ttl_seconds),
        )
        await get_redis_coordinator().release_lease(lease.key, owner=lease.owner)

    def start_sync(self, task: EphemeralTaskKey, **kwargs: Any) -> EphemeralTaskLease:
        return _run_coro_sync(lambda: self.start(task, **kwargs))

    def finish_sync(self, lease: EphemeralTaskLease, **kwargs: Any) -> None:
        _run_coro_sync(lambda: self.finish(lease, **kwargs))

    def fail_sync(self, lease: EphemeralTaskLease, **kwargs: Any) -> None:
        _run_coro_sync(lambda: self.fail(lease, **kwargs))


def _run_coro_sync(factory: Callable[[], Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    # Called from an async context: a thread-trampoline would block the running
    # event loop via thread.join() and is almost always a programming error.
    # All current callers (workspace_preview_service, recall_sidecar,
    # context_projection_worker) are genuinely synchronous.
    raise RuntimeError(
        "EphemeralTaskCoordinator.*_sync must not be called from an async "
        "context; use the async API (start/finish/fail) instead"
    )


def _ttl(value: float | None, default: float) -> float:
    return max(float(default if value is None else value), 0.001)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "owner",
        "version",
        "started_at",
        "finished_at",
        "result",
        "error_type",
        "deduplicated",
        "source",
        "artifact_ref",
        "task_id",
        "transform_type",
    }
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed or value is None:
            continue
        scalar = _safe_json(value, key=key)
        if scalar is not None:
            compact[key] = scalar
    return compact


def _safe_json(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 4:
        return None
    if key and _SENSITIVE_KEY_RE.search(str(key)):
        return None
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if isinstance(value, str):
        text = value[:500]
        if _is_sensitive_string(text):
            return "[REDACTED]"
        if _ABSOLUTE_PATH_RE.match(text):
            return "[REDACTED_PATH]"
        return text
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for item_key, item_value in list(value.items())[:80]:
            if _SENSITIVE_KEY_RE.search(str(item_key)):
                continue
            safe_value = _safe_json(item_value, key=str(item_key), depth=depth + 1)
            if safe_value is not None:
                out[str(item_key)[:120]] = safe_value
        return out
    if isinstance(value, list):
        return [
            safe_value
            for item in value[:100]
            if (safe_value := _safe_json(item, depth=depth + 1)) is not None
        ]
    return None


def _is_sensitive_string(value: str) -> bool:
    return bool(_SIGNED_URL_RE.search(value) or _SECRET_VALUE_RE.search(value))
