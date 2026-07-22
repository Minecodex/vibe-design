from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import REDIS_MAX_PAYLOAD_BYTES, REDIS_NAMESPACE
from app.core.redis_coordination import get_redis_coordinator

logger = logging.getLogger(__name__)

REALTIME_SCHEMA_VERSION = 2
REALTIME_KIND_NOTIFY = "notify"
REALTIME_KIND_WAKEUP = "wakeup"
REALTIME_KIND_INVALIDATE = "invalidate"
REALTIME_KINDS = {REALTIME_KIND_NOTIFY, REALTIME_KIND_WAKEUP, REALTIME_KIND_INVALIDATE}

_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_TEXT_FIELDS_MAX_LENGTH = 256


@dataclass(frozen=True)
class RealtimeScope:
    user_id: int | None = None
    project_id: int | None = None
    conversation_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
        }

    def to_hash_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_payload().items() if value is not None}


@dataclass(frozen=True)
class RealtimeResource:
    type: str
    id: str | None = None
    version: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "version": self.version,
        }


@dataclass(frozen=True)
class RealtimeEnvelope:
    kind: str
    name: str
    scope: RealtimeScope
    resource: RealtimeResource | None = None
    reason: str | None = None
    worker: str = "api"
    metadata: dict[str, Any] | None = None
    extra_payload: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        _validate_kind(self.kind)
        safe_name = _safe_name(self.name)
        if not safe_name:
            raise ValueError("realtime name is required")
        payload = {
            "v": REALTIME_SCHEMA_VERSION,
            "kind": self.kind,
            "name": safe_name,
            "scope": self.scope.to_payload(),
            "resource": self.resource.to_payload() if self.resource is not None else None,
            "reason": _optional_safe_text(self.reason),
            "metadata": _safe_metadata(self.metadata),
            "origin": {
                "pid": os.getpid(),
                "worker": _safe_name(self.worker) or "api",
            },
            "emitted_at": datetime.now(UTC).isoformat(),
        }
        if self.extra_payload:
            for raw_key, raw_value in self.extra_payload.items():
                key = _safe_name(str(raw_key))
                if key and key not in payload:
                    payload[key] = raw_value
        _validate_payload(payload)
        return payload


class RealtimeBus:
    def __init__(self, coordinator: Any | None = None, *, namespace: str | None = None) -> None:
        self.coordinator = coordinator or get_redis_coordinator()
        self.namespace = _safe_name(namespace or REDIS_NAMESPACE) or "ai-code"

    def topic(self, *, kind: str, name: str, scope: RealtimeScope) -> str:
        _validate_kind(kind)
        safe_name = _safe_name(name)
        if not safe_name:
            raise ValueError("realtime topic name is required")
        return f"{self.namespace}:rt:v2:{kind}:{safe_name}:{_scope_hash(scope)}"

    def wakeup_key(self, *, name: str, scope: RealtimeScope) -> str:
        safe_name = _safe_name(name)
        if not safe_name:
            raise ValueError("realtime wakeup name is required")
        return f"{self.namespace}:rt:v2:wakeup:{safe_name}:{_scope_hash(scope)}"

    async def publish(self, envelope: RealtimeEnvelope) -> dict[str, Any]:
        payload = envelope.to_payload()
        topic = self.topic(kind=envelope.kind, name=envelope.name, scope=envelope.scope)
        try:
            return await self.coordinator.publish(topic, payload)
        except Exception as exc:
            logger.info(
                "Realtime publish degraded: kind=%s name=%s error=%s",
                envelope.kind,
                envelope.name,
                type(exc).__name__,
            )
            return {"published": False, "delivered": 0, "degraded": True, "reason": type(exc).__name__}

    async def subscribe(
        self,
        *,
        kind: str,
        name: str,
        scope: RealtimeScope,
        callback: Callable[[dict[str, Any]], Any],
    ) -> Callable[[], None]:
        topic = self.topic(kind=kind, name=name, scope=scope)
        return await self.coordinator.subscribe(topic, callback)

    async def wakeup(
        self,
        *,
        name: str,
        scope: RealtimeScope,
        resource: RealtimeResource | None = None,
        reason: str | None = None,
        worker: str = "api",
    ) -> dict[str, Any]:
        payload = RealtimeEnvelope(
            kind=REALTIME_KIND_WAKEUP,
            name=name,
            scope=scope,
            resource=resource,
            reason=reason,
            worker=worker,
        ).to_payload()
        key = self.wakeup_key(name=name, scope=scope)
        _validate_payload(payload)
        try:
            return await self.coordinator.wakeup(key)
        except Exception as exc:
            logger.info("Realtime wakeup degraded: name=%s error=%s", name, type(exc).__name__)
            return {"woken": False, "degraded": True, "reason": type(exc).__name__}

    async def wait_wakeup(self, *, name: str, scope: RealtimeScope, timeout_seconds: float) -> dict[str, Any]:
        key = self.wakeup_key(name=name, scope=scope)
        return await self.coordinator.wait_wakeup(key, timeout_seconds=max(float(timeout_seconds), 0.0))


def publish_realtime_sync(envelope: RealtimeEnvelope) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(RealtimeBus().publish(envelope))
        except Exception:
            logger.info("Realtime publish failed", exc_info=True)
        return None

    task = loop.create_task(RealtimeBus().publish(envelope), name=f"realtime-publish-{envelope.name}")

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Realtime publish failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


async def publish_notification(
    name: str,
    *,
    scope: RealtimeScope,
    resource: RealtimeResource | None = None,
    reason: str | None = None,
    worker: str = "api",
    metadata: dict[str, Any] | None = None,
    extra_payload: dict[str, Any] | None = None,
    bus: RealtimeBus | None = None,
) -> dict[str, Any]:
    return await (bus or RealtimeBus()).publish(
        RealtimeEnvelope(
            kind=REALTIME_KIND_NOTIFY,
            name=name,
            scope=scope,
            resource=resource,
            reason=reason,
            worker=worker,
            metadata=metadata,
            extra_payload=extra_payload,
        )
    )


async def publish_invalidation(
    name: str,
    *,
    scope: RealtimeScope,
    resource: RealtimeResource | None = None,
    reason: str | None = None,
    worker: str = "api",
    bus: RealtimeBus | None = None,
) -> dict[str, Any]:
    return await (bus or RealtimeBus()).publish(
        RealtimeEnvelope(
            kind=REALTIME_KIND_INVALIDATE,
            name=name,
            scope=scope,
            resource=resource,
            reason=reason,
            worker=worker,
        )
    )


def publish_notification_sync(
    name: str,
    *,
    scope: RealtimeScope,
    resource: RealtimeResource | None = None,
    reason: str | None = None,
    worker: str = "api",
    metadata: dict[str, Any] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> asyncio.Task | None:
    return publish_realtime_sync(
        RealtimeEnvelope(
            kind=REALTIME_KIND_NOTIFY,
            name=name,
            scope=scope,
            resource=resource,
            reason=reason,
            worker=worker,
            metadata=metadata,
            extra_payload=extra_payload,
        )
    )


async def wakeup_realtime(
    name: str,
    *,
    scope: RealtimeScope | None = None,
    resource: RealtimeResource | None = None,
    reason: str | None = None,
    worker: str = "api",
    bus: RealtimeBus | None = None,
) -> dict[str, Any]:
    return await (bus or RealtimeBus()).wakeup(
        name=name,
        scope=scope or RealtimeScope(),
        resource=resource,
        reason=reason,
        worker=worker,
    )


async def wait_realtime_wakeup(
    name: str,
    *,
    scope: RealtimeScope | None = None,
    timeout_seconds: float,
    bus: RealtimeBus | None = None,
) -> dict[str, Any]:
    return await (bus or RealtimeBus()).wait_wakeup(
        name=name,
        scope=scope or RealtimeScope(),
        timeout_seconds=timeout_seconds,
    )


def _safe_name(value: str | None) -> str:
    normalized = _NAME_RE.sub("-", str(value or "").strip()).strip("-").lower()
    return normalized[:_TEXT_FIELDS_MAX_LENGTH]


def _optional_safe_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    _reject_secret_or_path(text)
    return text[:_TEXT_FIELDS_MAX_LENGTH]


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise ValueError("realtime metadata must be an object")
    safe: dict[str, Any] = {}
    for raw_key, raw_value in list(metadata.items())[:32]:
        key = _safe_name(str(raw_key))
        if not key:
            continue
        safe[key] = _safe_metadata_value(raw_value, depth=0)
    return safe or None


def _safe_metadata_value(value: Any, *, depth: int) -> Any:
    if depth > 4:
        raise ValueError("realtime metadata is too deeply nested")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        _reject_secret_marker(text)
        return text[:_TEXT_FIELDS_MAX_LENGTH]
    if isinstance(value, list):
        return [_safe_metadata_value(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:32]:
            key = _safe_name(str(raw_key))
            if not key:
                continue
            safe[key] = _safe_metadata_value(raw_value, depth=depth + 1)
        return safe
    raise ValueError("realtime metadata contains unsupported value")


def _validate_kind(kind: str) -> None:
    if kind not in REALTIME_KINDS:
        raise ValueError(f"unsupported realtime kind: {kind}")


def _scope_hash(scope: RealtimeScope) -> str:
    payload = json.dumps(scope.to_hash_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _validate_payload(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > int(REDIS_MAX_PAYLOAD_BYTES):
        raise ValueError("realtime payload exceeds configured Redis payload limit")
    _walk_payload(payload)


def _walk_payload(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _walk_payload(item)
        return
    if isinstance(value, list):
        for item in value:
            _walk_payload(item)
        return
    if isinstance(value, str):
        _reject_secret_marker(value)


def _reject_secret_marker(value: str) -> None:
    # Soft check applied to every string in the payload: only block obvious
    # secret/token shapes. Paths and URLs are tolerated here because legitimate
    # resource ids, versions and trace strings can contain `/`.
    lowered = value.strip().lower()
    if any(marker in lowered for marker in ("authorization", "cookie", "api_key", "license_token")):
        raise ValueError("realtime payload contains sensitive marker")
    if "sk-" in lowered:
        raise ValueError("realtime payload contains token-like value")


def _reject_secret_or_path(value: str) -> None:
    # Strict check reserved for free-text fields supplied by callers (e.g.
    # `reason`). These have no structural reason to contain paths or URLs.
    _reject_secret_marker(value)
    text = value.strip()
    if "/" in text or "\\" in text:
        raise ValueError("realtime payload must not contain paths or URLs")
