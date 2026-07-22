from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import threading
import time
import weakref
from collections.abc import Callable
from typing import Any

from app.core.config import (
    REDIS_NAMESPACE,
    Settings,
)
from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only when redis dependency is installed.
    import redis.asyncio as redis_asyncio
    from redis.exceptions import RedisError as _RedisError
except Exception:  # pragma: no cover - redis is optional at import time.
    redis_asyncio = None

    class _RedisError(Exception):
        """Placeholder when the redis dependency is not installed."""


_EXPECTED_REDIS_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    _RedisError,
    ConnectionError,
    OSError,
)


class RedisCoordinationDegradedError(RuntimeError):
    """Raised when REDIS_REQUIRED=True and a distributed-correctness operation
    (lease / duplicate guard / rate limit) cannot be served by Redis. The
    in-process fallback would silently lose the cross-worker guarantee, so the
    operation surfaces this error instead. Callers that have a safer local
    fallback (e.g. file leader lock) should catch and degrade explicitly.
    """

    def __init__(self, *, operation: str, reason: str) -> None:
        super().__init__(
            f"redis coordination required but degraded: operation={operation} reason={reason}"
        )
        self.operation = operation
        self.reason = reason


_KEY_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_segment(value: str) -> str:
    normalized = _KEY_SEGMENT_RE.sub("-", str(value or "").strip()).strip("-").lower()
    return normalized or "default"


def _empty_operation_summary() -> dict[str, Any]:
    return {
        "success_count": 0,
        "failure_count": 0,
        "fallback_count": 0,
        "recent_operations": [],
    }


def _domain_from_target(target: str | None) -> str:
    if not target:
        return "unknown"
    value = str(target)
    if value.startswith("wakeup:"):
        value = value.removeprefix("wakeup:")
    parts = value.split(":")
    if len(parts) >= 3:
        return _safe_segment(parts[1])
    return "unknown"


class RedisKeyBuilder:
    def __init__(self, *, namespace: str) -> None:
        self.namespace = _safe_segment(namespace)

    def build(
        self,
        *,
        domain: str,
        purpose: str,
        resource_parts: list[str] | tuple[str, ...] = (),
    ) -> str:
        segments = [self.namespace, _safe_segment(domain), _safe_segment(purpose)]
        if resource_parts:
            digest = hashlib.sha256(
                "\x1f".join(str(part) for part in resource_parts).encode("utf-8")
            ).hexdigest()[:32]
            segments.append(digest)
        return ":".join(segments)


class DisabledRedisCoordinator:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.keys = RedisKeyBuilder(namespace=REDIS_NAMESPACE)

    async def health(self) -> dict[str, Any]:
        return {
            "status": "disabled",
            "enabled": False,
            "required": bool(self.settings.REDIS_REQUIRED),
            "degraded": False,
            "reason": "redis_disabled",
            "latency_ms": None,
            "operation_summary": _empty_operation_summary(),
        }

    async def set_snapshot(self, key: str, value: Any, *, ttl_seconds: float) -> None:
        return None

    async def get_snapshot(self, key: str) -> Any | None:
        return None

    async def set_blob(self, key: str, value: bytes, *, ttl_seconds: float, max_bytes: int) -> None:
        del key, value, ttl_seconds, max_bytes
        return None

    async def set_blobs(self, values: dict[str, bytes], *, ttl_seconds: float, max_bytes: int) -> None:
        del values, ttl_seconds, max_bytes
        return None

    async def get_blob(self, key: str, *, max_bytes: int) -> bytes | None:
        del key, max_bytes
        return None

    async def delete_key(self, key: str) -> int:
        del key
        return 0

    async def delete_prefix(self, prefix: str) -> int:
        del prefix
        return 0

    async def enqueue_json(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> dict[str, Any]:
        del ttl_seconds
        return {"enqueued": False, "degraded": False, "reason": "redis_disabled"}

    async def pop_json(self, key: str) -> Any | None:
        del key
        return None

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        return {"acquired": True, "owner": str(owner), "reason": "redis_disabled"}

    async def renew_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        return {"renewed": True, "owner": str(owner), "reason": "redis_disabled"}

    async def release_lease(self, key: str, *, owner: str) -> bool:
        return False

    async def duplicate_guard(self, key: str, *, ttl_seconds: float) -> dict[str, Any]:
        return {"acquired": True, "reason": "redis_disabled"}

    async def rate_limit(self, bucket: str, *, limit: int, window_seconds: float) -> dict[str, Any]:
        return {"allowed": True, "retry_after_seconds": 0.0, "reason": "redis_disabled"}

    async def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        def unsubscribe() -> None:
            return None

        return unsubscribe

    async def publish(self, topic: str, envelope: dict[str, Any]) -> dict[str, Any]:
        return {"published": False, "delivered": 0, "degraded": False, "reason": "redis_disabled"}

    async def wakeup(self, key: str) -> dict[str, Any]:
        return {"woken": False, "degraded": False, "reason": "redis_disabled"}

    async def wait_wakeup(self, key: str, *, timeout_seconds: float) -> dict[str, Any]:
        return {"woken": False, "reason": "redis_disabled"}

    async def shutdown_wakeup_subscribers(self) -> None:
        return None


class InProcessRedisCoordinator:
    def __init__(self, *, settings: Settings, reason: str = "redis_unavailable") -> None:
        self.settings = settings
        self.reason = reason
        self.keys = RedisKeyBuilder(namespace=REDIS_NAMESPACE)
        self._snapshots: dict[str, tuple[Any, float]] = {}
        self._queues: dict[str, list[Any]] = {}
        self._leases: dict[str, tuple[str, float]] = {}
        self._guards: dict[str, float] = {}
        self._rate_limits: dict[str, list[float]] = {}
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}
        self._wakeups: dict[str, int] = {}
        self._wakeup_events: dict[str, asyncio.Event] = {}

    def _expires_at(self, ttl_seconds: float) -> float:
        return time.monotonic() + max(float(ttl_seconds), 0.001)

    def _is_alive(self, expires_at: float) -> bool:
        return expires_at > time.monotonic()

    async def health(self) -> dict[str, Any]:
        return {
            "status": "required-unavailable" if self.settings.REDIS_REQUIRED else "degraded",
            "enabled": True,
            "required": bool(self.settings.REDIS_REQUIRED),
            "degraded": True,
            "reason": self.reason,
            "latency_ms": None,
            "operation_summary": _empty_operation_summary(),
        }

    async def set_snapshot(self, key: str, value: Any, *, ttl_seconds: float) -> None:
        self._snapshots[str(key)] = (value, self._expires_at(ttl_seconds))

    async def get_snapshot(self, key: str) -> Any | None:
        item = self._snapshots.get(str(key))
        if item is None:
            return None
        value, expires_at = item
        if not self._is_alive(expires_at):
            self._snapshots.pop(str(key), None)
            return None
        return value

    async def set_blob(self, key: str, value: bytes, *, ttl_seconds: float, max_bytes: int) -> None:
        payload = bytes(value)
        if len(payload) > int(max_bytes):
            raise ValueError("redis blob payload exceeds configured limit")
        self._snapshots[str(key)] = (payload, self._expires_at(ttl_seconds))

    async def set_blobs(self, values: dict[str, bytes], *, ttl_seconds: float, max_bytes: int) -> None:
        payloads = {str(key): bytes(value) for key, value in dict(values).items()}
        for payload in payloads.values():
            if len(payload) > int(max_bytes):
                raise ValueError("redis blob payload exceeds configured limit")
        expires_at = self._expires_at(ttl_seconds)
        for key, payload in payloads.items():
            self._snapshots[key] = (payload, expires_at)

    async def get_blob(self, key: str, *, max_bytes: int) -> bytes | None:
        item = self._snapshots.get(str(key))
        if item is None:
            return None
        value, expires_at = item
        if not self._is_alive(expires_at):
            self._snapshots.pop(str(key), None)
            return None
        if not isinstance(value, bytes | bytearray):
            return None
        payload = bytes(value)
        if len(payload) > int(max_bytes):
            raise ValueError("redis blob payload exceeds configured limit")
        return payload

    async def delete_key(self, key: str) -> int:
        removed = 0
        if self._snapshots.pop(str(key), None) is not None:
            removed += 1
        self._queues.pop(str(key), None)
        self._leases.pop(str(key), None)
        self._guards.pop(str(key), None)
        self._rate_limits.pop(str(key), None)
        return removed

    async def delete_prefix(self, prefix: str) -> int:
        normalized_prefix = str(prefix)
        keys = set(self._snapshots) | set(self._queues) | set(self._leases) | set(self._guards) | set(self._rate_limits)
        keys |= set(self._wakeups) | set(self._wakeup_events)
        matches = [key for key in keys if key.startswith(normalized_prefix)]
        for key in matches:
            await self.delete_key(key)
            self._wakeups.pop(key, None)
            self._wakeup_events.pop(key, None)
        return len(matches)

    async def enqueue_json(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> dict[str, Any]:
        del ttl_seconds
        self._queues.setdefault(str(key), []).append(value)
        return {"enqueued": True, "degraded": True, "reason": self.reason}

    async def pop_json(self, key: str) -> Any | None:
        queue = self._queues.get(str(key))
        if not queue:
            return None
        item = queue.pop(0)
        if not queue:
            self._queues.pop(str(key), None)
        return item

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        normalized_key = str(key)
        item = self._leases.get(normalized_key)
        if item is not None:
            current_owner, expires_at = item
            if self._is_alive(expires_at):
                return {
                    "acquired": current_owner == str(owner),
                    "owner": current_owner,
                    "degraded": True,
                    "reason": self.reason,
                }
        self._leases[normalized_key] = (str(owner), self._expires_at(ttl_seconds))
        return {"acquired": True, "owner": str(owner), "degraded": True, "reason": self.reason}

    async def renew_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        normalized_key = str(key)
        item = self._leases.get(normalized_key)
        if item is None:
            return {"renewed": False, "owner": None}
        current_owner, expires_at = item
        if current_owner != str(owner) or not self._is_alive(expires_at):
            return {"renewed": False, "owner": current_owner}
        self._leases[normalized_key] = (str(owner), self._expires_at(ttl_seconds))
        return {"renewed": True, "owner": str(owner)}

    async def release_lease(self, key: str, *, owner: str) -> bool:
        normalized_key = str(key)
        item = self._leases.get(normalized_key)
        if item is None:
            return False
        current_owner, _expires_at = item
        if current_owner != str(owner):
            return False
        self._leases.pop(normalized_key, None)
        return True

    async def duplicate_guard(self, key: str, *, ttl_seconds: float) -> dict[str, Any]:
        normalized_key = str(key)
        expires_at = self._guards.get(normalized_key)
        if expires_at is not None and self._is_alive(expires_at):
            return {"acquired": False}
        self._guards[normalized_key] = self._expires_at(ttl_seconds)
        return {"acquired": True}

    async def rate_limit(self, bucket: str, *, limit: int, window_seconds: float) -> dict[str, Any]:
        now = time.monotonic()
        window_start = now - max(float(window_seconds), 0.001)
        events = [event_at for event_at in self._rate_limits.get(str(bucket), []) if event_at >= window_start]
        allowed = len(events) < max(int(limit), 0)
        if allowed:
            events.append(now)
        self._rate_limits[str(bucket)] = events
        retry_after = 0.0 if allowed or not events else max(events[0] + float(window_seconds) - now, 0.0)
        return {"allowed": allowed, "retry_after_seconds": retry_after}

    async def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        normalized_topic = str(topic)
        self._subscribers.setdefault(normalized_topic, []).append(callback)

        def unsubscribe() -> None:
            callbacks = self._subscribers.get(normalized_topic)
            if not callbacks:
                return
            try:
                callbacks.remove(callback)
            except ValueError:
                return
            if not callbacks:
                self._subscribers.pop(normalized_topic, None)

        return unsubscribe

    async def publish(self, topic: str, envelope: dict[str, Any]) -> dict[str, Any]:
        callbacks = list(self._subscribers.get(str(topic), ()))
        delivered = 0
        for callback in callbacks:
            result = callback(dict(envelope))
            if inspect.isawaitable(result):
                await result
            delivered += 1
        return {"published": True, "delivered": delivered, "degraded": True}

    async def wakeup(self, key: str) -> dict[str, Any]:
        normalized_key = str(key)
        self._wakeups[normalized_key] = self._wakeups.get(normalized_key, 0) + 1
        self._wakeup_events.setdefault(normalized_key, asyncio.Event()).set()
        return {"woken": True, "degraded": True}

    async def wait_wakeup(self, key: str, *, timeout_seconds: float) -> dict[str, Any]:
        normalized_key = str(key)
        count = self._wakeups.get(normalized_key, 0)
        if count > 0:
            if count == 1:
                self._wakeups.pop(normalized_key, None)
                event = self._wakeup_events.get(normalized_key)
                if event is not None:
                    event.clear()
            else:
                self._wakeups[normalized_key] = count - 1
            return {"woken": True}

        event = self._wakeup_events.setdefault(normalized_key, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout=max(float(timeout_seconds), 0.0))
        except TimeoutError:
            return {"woken": False}
        return await self.wait_wakeup(normalized_key, timeout_seconds=0)

    async def shutdown_wakeup_subscribers(self) -> None:
        return None


class _SharedWakeupSubscriber:
    # Per-(event loop, channel) long-lived pubsub subscriber. A single
    # background task owns the TCP connection and SUBSCRIBE; every
    # wait_wakeup caller awaits the shared asyncio.Event instead of opening
    # its own pubsub connection. This collapses what used to be N TCP +
    # CLIENT SETINFO + SUBSCRIBE round-trips per wait into one persistent
    # subscription per channel.
    #
    # Note: this poll interval doubles as the periodic event.set() cadence
    # (see _run below). It must be <= the shortest caller-side wait deadline
    # so that callers can observe a publish that arrived during the brief
    # window between two get_message rounds. Keep this <= typical
    # wait_wakeup timeout_seconds.
    _POLL_TIMEOUT_SECONDS = 1.0

    def __init__(self, client: Any, channel: str) -> None:
        self._client = client
        self._channel = channel
        self._event = asyncio.Event()
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._failed_reason: str | None = None

    @property
    def event(self) -> asyncio.Event:
        return self._event

    def is_failed(self) -> bool:
        return self._failed_reason is not None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def ensure_started(self, *, ready_timeout: float) -> bool:
        if not self.is_running():
            self._failed_reason = None
            self._ready.clear()
            self._task = asyncio.create_task(
                self._run(), name=f"redis-wakeup-sub-{self._channel}"
            )
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=max(ready_timeout, 0.001))
        except TimeoutError:
            return False
        return not self.is_failed()

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _run(self) -> None:
        pubsub = None
        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(self._channel)
            self._ready.set()
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=self._POLL_TIMEOUT_SECONDS,
                )
                if message is None:
                    # Periodic wake so wait_wakeup callers re-check the
                    # counter even if a publish was lost (e.g. brief
                    # connection blip before subscribe completed).
                    self._event.set()
                    continue
                if message.get("type") != "message":
                    continue
                self._event.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._failed_reason = type(exc).__name__
            self._ready.set()
            self._event.set()
            logger.info(
                "Shared wakeup subscriber failed: channel=%s error=%s",
                self._channel,
                type(exc).__name__,
            )
        finally:
            if pubsub is not None:
                try:
                    await pubsub.close()
                except Exception:  # noqa: BLE001
                    pass


class RedisCoordinator:
    _LEASE_RENEW_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
    end
    return 0
    """
    _LEASE_RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """
    _WAKEUP_CONSUME_SCRIPT = """
    local current = tonumber(redis.call("get", KEYS[1]) or "0")
    if current <= 0 then
        return 0
    end
    if current == 1 then
        redis.call("del", KEYS[1])
    else
        redis.call("decr", KEYS[1])
    end
    return 1
    """

    def __init__(self, *, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.keys = RedisKeyBuilder(namespace=REDIS_NAMESPACE)
        self._fallback = InProcessRedisCoordinator(settings=settings)
        self._explicit_client = client
        self._loop_clients: dict[int, tuple[weakref.ReferenceType[Any], Any]] = {}
        self._binary_loop_clients: dict[int, tuple[weakref.ReferenceType[Any], Any]] = {}
        self._pubsub_loop_clients: dict[int, tuple[weakref.ReferenceType[Any], Any]] = {}
        self._loop_clients_lock = threading.RLock()
        self._wakeup_subscribers: dict[int, dict[str, _SharedWakeupSubscriber]] = {}
        # Per-(loop, channel) lock to serialize subscriber creation/replacement
        # so concurrent _ensure_wakeup_subscriber callers don't leak duplicate
        # background tasks during failure-rebuild.
        self._wakeup_subscriber_locks: dict[int, dict[str, asyncio.Lock]] = {}
        # Channel-keyed (loop-independent) lifetime stats surfaced via
        # health(): rebuild count, last failure reason, last failure
        # timestamp. Persisted across rebuilds for observability.
        self._wakeup_subscriber_stats: dict[str, dict[str, Any]] = {}
        self._operation_history: list[dict[str, Any]] = []
        self._success_count = 0
        self._failure_count = 0
        self._fallback_count = 0

    @staticmethod
    def _create_client(
        settings: Settings,
        *,
        decode_responses: bool = True,
        socket_timeout: float | None | str = "settings",
    ) -> Any | None:
        if redis_asyncio is None:
            return None
        # socket_timeout: kernel-level read timeout. Required so a half-open
        # connection (NAT / LB silently dropped) does not stall an operation
        # indefinitely waiting for the application-level asyncio.wait_for to
        # fire — which, under an event-loop-busy condition, can be much later
        # than intended. Set comfortably larger than the per-operation
        # asyncio timeout so it only acts as a backstop.
        resolved_socket_timeout = (
            max(float(settings.REDIS_SOCKET_TIMEOUT_SECONDS), 0.001)
            if socket_timeout == "settings"
            else socket_timeout
        )
        socket_keepalive = bool(getattr(settings, "REDIS_SOCKET_KEEPALIVE", True))
        return redis_asyncio.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=max(float(settings.REDIS_CONNECT_TIMEOUT_SECONDS), 0.001),
            socket_timeout=resolved_socket_timeout,
            socket_keepalive=socket_keepalive,
            decode_responses=decode_responses,
            max_connections=max(int(settings.REDIS_MAX_CONNECTIONS), 1),
            health_check_interval=max(int(settings.REDIS_HEALTH_CHECK_INTERVAL_SECONDS), 0),
        )

    @property
    def _client(self) -> Any | None:
        # redis.asyncio clients are bound to the event loop that first uses them; the
        # *_sync helpers in this codebase spawn fresh loops via asyncio.run, so we
        # cache one client per running loop instead of sharing a single one.
        if self._explicit_client is not None:
            return self._explicit_client
        if redis_asyncio is None:
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        # Sweep entries whose loop has been GC'd. Without this the dict grows
        # unboundedly under repeated asyncio.run(...) usage (each fresh loop
        # leaves a dead weakref behind), eventually retaining many unreachable
        # redis client / connection pool objects.
        loop_id = id(loop)
        with self._loop_clients_lock:
            self._sweep_dead_loop_clients()
            entry = self._loop_clients.get(loop_id)
            if entry is not None:
                loop_ref, cached_client = entry
                if loop_ref() is loop:
                    return cached_client
            client = self._create_client(self.settings)
            if client is None:
                return None
            try:
                loop_ref = weakref.ref(loop)
            except TypeError:
                loop_ref = None
            if loop_ref is not None:
                self._loop_clients[loop_id] = (loop_ref, client)
            return client

    @property
    def _binary_client(self) -> Any | None:
        if self._explicit_client is not None:
            return self._explicit_client
        if redis_asyncio is None:
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        loop_id = id(loop)
        with self._loop_clients_lock:
            self._sweep_dead_loop_clients()
            entry = self._binary_loop_clients.get(loop_id)
            if entry is not None:
                loop_ref, cached_client = entry
                if loop_ref() is loop:
                    return cached_client
            client = self._create_client(self.settings, decode_responses=False)
            if client is None:
                return None
            try:
                loop_ref = weakref.ref(loop)
            except TypeError:
                loop_ref = None
            if loop_ref is not None:
                self._binary_loop_clients[loop_id] = (loop_ref, client)
            return client

    @property
    def _pubsub_client(self) -> Any | None:
        if self._explicit_client is not None:
            return self._explicit_client
        if redis_asyncio is None:
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        loop_id = id(loop)
        with self._loop_clients_lock:
            self._sweep_dead_loop_clients()
            entry = self._pubsub_loop_clients.get(loop_id)
            if entry is not None:
                loop_ref, cached_client = entry
                if loop_ref() is loop:
                    return cached_client
            # Pub/Sub listen is a long-lived blocking read. It must not inherit the
            # short command socket timeout, or idle subscriptions are closed before
            # the next notification arrives.
            client = self._create_client(self.settings, socket_timeout=None)
            if client is None:
                return None
            try:
                loop_ref = weakref.ref(loop)
            except TypeError:
                loop_ref = None
            if loop_ref is not None:
                self._pubsub_loop_clients[loop_id] = (loop_ref, client)
            return client

    def _sweep_dead_loop_clients(self) -> None:
        with self._loop_clients_lock:
            loop_items = list(self._loop_clients.items())
            pubsub_items = list(self._pubsub_loop_clients.items())
        stale_loop_ids = [
            loop_id
            for loop_id, (loop_ref, _client) in loop_items
            if loop_ref() is None
        ]
        stale_loop_ids.extend(
            loop_id
            for loop_id, (loop_ref, _client) in pubsub_items
            if loop_ref() is None
        )
        with self._loop_clients_lock:
            for loop_id in stale_loop_ids:
                self._loop_clients.pop(loop_id, None)
                self._binary_loop_clients.pop(loop_id, None)
                self._pubsub_loop_clients.pop(loop_id, None)
                # Wakeup subscribers / locks are bound to the same loop's client;
                # drop them too so we don't keep references to defunct
                # connections or stranded locks.
                self._wakeup_subscribers.pop(loop_id, None)
                self._wakeup_subscriber_locks.pop(loop_id, None)

    async def shutdown_wakeup_subscribers(self) -> None:
        # Cancel and close every long-lived wakeup subscriber. Safe to call
        # multiple times. Intended for graceful shutdown so we don't leak
        # pubsub TCP connections on reload.
        all_subscribers: list[_SharedWakeupSubscriber] = []
        for channels in self._wakeup_subscribers.values():
            all_subscribers.extend(channels.values())
        self._wakeup_subscribers.clear()
        self._wakeup_subscriber_locks.clear()
        for subscriber in all_subscribers:
            await subscriber.stop()

    def _wakeup_subscriber_stat(self, channel: str) -> dict[str, Any]:
        return self._wakeup_subscriber_stats.setdefault(
            channel,
            {
                "rebuild_count": 0,
                "last_failure_reason": None,
                "last_failure_at": None,
            },
        )

    async def _ensure_wakeup_subscriber(self, channel: str) -> _SharedWakeupSubscriber | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        client = self._client
        if client is None:
            return None
        loop_id = id(loop)
        locks = self._wakeup_subscriber_locks.setdefault(loop_id, {})
        lock = locks.get(channel)
        if lock is None:
            lock = asyncio.Lock()
            locks[channel] = lock
        async with lock:
            channels = self._wakeup_subscribers.setdefault(loop_id, {})
            subscriber = channels.get(channel)
            needs_rebuild = (
                subscriber is None
                or not subscriber.is_running()
                or subscriber.is_failed()
            )
            if needs_rebuild:
                if subscriber is not None and subscriber.is_failed():
                    stats = self._wakeup_subscriber_stat(channel)
                    stats["last_failure_reason"] = subscriber._failed_reason
                    stats["last_failure_at"] = time.time()
                    await subscriber.stop()
                if subscriber is not None:
                    # Count every rebuild (including initial fresh start
                    # after a previous successful stop on shutdown). The
                    # first-ever creation is not counted as a rebuild.
                    self._wakeup_subscriber_stat(channel)["rebuild_count"] += 1
                else:
                    # Touch stats so the channel shows up in health output
                    # even before the first failure.
                    self._wakeup_subscriber_stat(channel)
                subscriber = _SharedWakeupSubscriber(client, channel)
                channels[channel] = subscriber
            ready_timeout = max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 0.001)
            ok = await subscriber.ensure_started(ready_timeout=ready_timeout)
            if not ok:
                if subscriber.is_failed():
                    stats = self._wakeup_subscriber_stat(channel)
                    stats["last_failure_reason"] = subscriber._failed_reason
                    stats["last_failure_at"] = time.time()
                return None
        return subscriber

    def _connection_pool_summary(self, client: Any | None = None) -> dict[str, Any]:
        client = client if client is not None else self._explicit_client
        if client is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                with self._loop_clients_lock:
                    entry = self._loop_clients.get(id(loop))
                if entry is not None:
                    loop_ref, cached_client = entry
                    if loop_ref() is loop:
                        client = cached_client
        pool = getattr(client, "connection_pool", None) if client is not None else None
        if pool is None:
            return {"available": False}
        try:
            max_connections = int(getattr(pool, "max_connections", 0) or 0)
            in_use_attr = getattr(pool, "_in_use_connections", ())
            available_attr = getattr(pool, "_available_connections", ())
            in_use = len(in_use_attr) if in_use_attr is not None else 0
            available = len(available_attr) if available_attr is not None else 0
            created = in_use + available
            saturation: float | None = None
            if max_connections > 0:
                saturation = round(created / max_connections, 3)
            return {
                "available": True,
                "max_connections": max_connections,
                "created": created,
                "in_use": in_use,
                "idle": available,
                "saturation": saturation,
            }
        except Exception:  # noqa: BLE001
            return {"available": False}

    def _wakeup_subscribers_summary(self) -> dict[str, Any]:
        channels_summary: dict[str, dict[str, Any]] = {}
        live_states: dict[str, str] = {}
        for channels in self._wakeup_subscribers.values():
            for channel, subscriber in channels.items():
                if subscriber.is_failed():
                    live_states[channel] = "failed"
                elif subscriber.is_running():
                    live_states[channel] = "running"
                else:
                    live_states[channel] = "stopped"
        for channel, stats in self._wakeup_subscriber_stats.items():
            channels_summary[channel] = {
                "state": live_states.get(channel, "absent"),
                "rebuild_count": int(stats.get("rebuild_count", 0)),
                "last_failure_reason": stats.get("last_failure_reason"),
                "last_failure_at": stats.get("last_failure_at"),
            }
        return {
            "channel_count": len(channels_summary),
            "channels": channels_summary,
        }

    def _operation_summary(self) -> dict[str, Any]:
        return {
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "fallback_count": self._fallback_count,
            "recent_operations": list(self._operation_history[-20:]),
        }

    def _record_operation(
        self,
        *,
        operation: str,
        target: str | None,
        success: bool,
        fallback: bool,
        latency_ms: float,
        error_type: str | None = None,
    ) -> None:
        if success:
            self._success_count += 1
        else:
            self._failure_count += 1
        if fallback:
            self._fallback_count += 1
        record = {
            "operation": _safe_segment(operation),
            "domain": _domain_from_target(target),
            "success": bool(success),
            "fallback": bool(fallback),
            "latency_ms": round(float(latency_ms), 3),
        }
        if error_type:
            record["error_type"] = str(error_type)[:120]
        self._operation_history.append(record)
        del self._operation_history[:-20]

    async def _call(
        self,
        operation: str,
        func,
        fallback_func,
        *,
        target: str | None = None,
        timeout_seconds: float | None = None,
        strict: bool = False,
        apply_timeout: bool = True,
    ):
        started = time.perf_counter()
        operation_timeout = max(
            float(
                self.settings.REDIS_OPERATION_TIMEOUT_SECONDS
                if timeout_seconds is None
                else timeout_seconds
            ),
            0.001,
        )
        strict_required = bool(strict and self.settings.REDIS_REQUIRED)
        if self._client is None:
            latency_ms = (time.perf_counter() - started) * 1000
            self._record_operation(
                operation=operation,
                target=target,
                success=False,
                fallback=not strict_required,
                latency_ms=latency_ms,
                error_type="redis_dependency_unavailable",
            )
            if strict_required:
                raise RedisCoordinationDegradedError(
                    operation=operation,
                    reason="redis_dependency_unavailable",
                )
            result = await fallback_func()
            logger.info(
                "Redis coordination operation degraded: operation=%s domain=%s success=%s latency_ms=%.3f fallback=%s error=%s",
                operation,
                _domain_from_target(target),
                False,
                latency_ms,
                True,
                "redis_dependency_unavailable",
            )
            return result
        try:
            if apply_timeout:
                result = await asyncio.wait_for(
                    func(),
                    timeout=operation_timeout,
                )
            else:
                result = await func()
            latency_ms = (time.perf_counter() - started) * 1000
            self._record_operation(
                operation=operation,
                target=target,
                success=True,
                fallback=False,
                latency_ms=latency_ms,
            )
            return result
        except (ValueError, TypeError):
            # Caller-side validation / serialization errors (e.g. payload too
            # large, non-JSON-serialisable value). Surface to caller — falling
            # back to the in-process coordinator would bypass the limits that
            # raised the error in the first place.
            raise
        except Exception as exc:
            expected = isinstance(exc, _EXPECTED_REDIS_ERRORS)
            latency_ms = (time.perf_counter() - started) * 1000
            error_type = type(exc).__name__
            self._record_operation(
                operation=operation,
                target=target,
                success=False,
                fallback=not strict_required,
                latency_ms=latency_ms,
                error_type=error_type,
            )
            log_fn = logger.info if expected else logger.warning
            log_fn(
                "Redis coordination operation degraded: operation=%s domain=%s success=%s latency_ms=%.3f fallback=%s error=%s expected=%s",
                operation,
                _domain_from_target(target),
                False,
                latency_ms,
                not strict_required,
                error_type,
                expected,
            )
            if strict_required:
                raise RedisCoordinationDegradedError(
                    operation=operation,
                    reason=error_type,
                ) from exc
            return await fallback_func()

    async def health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if self._client is None:
                raise RuntimeError("redis_dependency_unavailable")
            await asyncio.wait_for(
                self._client.ping(),
                timeout=max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 0.001),
            )
            return {
                "status": "healthy",
                "enabled": True,
                "required": bool(self.settings.REDIS_REQUIRED),
                "degraded": False,
                "reason": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "operation_summary": self._operation_summary(),
                "wakeup_subscribers": self._wakeup_subscribers_summary(),
                "connection_pool": self._connection_pool_summary(),
            }
        except Exception as exc:
            fallback_health = await self._fallback.health()
            fallback_health["reason"] = type(exc).__name__
            fallback_health["operation_summary"] = self._operation_summary()
            fallback_health["wakeup_subscribers"] = self._wakeup_subscribers_summary()
            fallback_health["connection_pool"] = self._connection_pool_summary()
            return fallback_health

    async def set_snapshot(self, key: str, value: Any, *, ttl_seconds: float) -> None:
        async def _redis_set() -> None:
            payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            if len(payload.encode("utf-8")) > int(self.settings.REDIS_MAX_PAYLOAD_BYTES):
                raise ValueError("redis snapshot payload exceeds configured limit")
            await self._client.set(str(key), payload, ex=max(int(ttl_seconds), 1))

        await self._call(
            "set_snapshot",
            _redis_set,
            lambda: self._fallback.set_snapshot(key, value, ttl_seconds=ttl_seconds),
            target=key,
        )

    async def get_snapshot(self, key: str) -> Any | None:
        async def _redis_get() -> Any | None:
            raw = await self._client.get(str(key))
            if raw is None:
                return None
            return json.loads(raw)

        return await self._call("get_snapshot", _redis_get, lambda: self._fallback.get_snapshot(key), target=key)

    async def set_blob(self, key: str, value: bytes, *, ttl_seconds: float, max_bytes: int) -> None:
        async def _redis_set_blob() -> None:
            payload = bytes(value)
            if len(payload) > int(max_bytes):
                raise ValueError("redis blob payload exceeds configured limit")
            client = self._binary_client
            if client is None:
                raise RuntimeError("redis_dependency_unavailable")
            await client.set(str(key), payload, ex=max(int(ttl_seconds), 1))

        await self._call(
            "set_blob",
            _redis_set_blob,
            lambda: self._fallback.set_blob(
                key,
                value,
                ttl_seconds=ttl_seconds,
                max_bytes=max_bytes,
            ),
            target=key,
            strict=True,
        )

    async def set_blobs(self, values: dict[str, bytes], *, ttl_seconds: float, max_bytes: int) -> None:
        payloads = {str(key): bytes(value) for key, value in dict(values).items()}
        for payload in payloads.values():
            if len(payload) > int(max_bytes):
                raise ValueError("redis blob payload exceeds configured limit")

        async def _redis_set_blobs() -> None:
            client = self._binary_client
            if client is None:
                raise RuntimeError("redis_dependency_unavailable")
            pipe = client.pipeline(transaction=True)
            for key, payload in payloads.items():
                pipe.set(key, payload, ex=max(int(ttl_seconds), 1))
            await pipe.execute()

        await self._call(
            "set_blobs",
            _redis_set_blobs,
            lambda: self._fallback.set_blobs(
                payloads,
                ttl_seconds=ttl_seconds,
                max_bytes=max_bytes,
            ),
            target="agent-catalog:set-blobs",
            strict=True,
        )

    async def get_blob(self, key: str, *, max_bytes: int) -> bytes | None:
        async def _redis_get_blob() -> bytes | None:
            client = self._binary_client
            if client is None:
                raise RuntimeError("redis_dependency_unavailable")
            raw = await client.get(str(key))
            if raw is None:
                return None
            if not isinstance(raw, bytes | bytearray):
                raise TypeError("redis blob response must be bytes")
            payload = bytes(raw)
            if len(payload) > int(max_bytes):
                raise ValueError("redis blob payload exceeds configured limit")
            return payload

        return await self._call(
            "get_blob",
            _redis_get_blob,
            lambda: self._fallback.get_blob(key, max_bytes=max_bytes),
            target=key,
            strict=True,
        )

    async def delete_key(self, key: str) -> int:
        async def _redis_delete() -> int:
            return int(await self._client.delete(str(key)) or 0)

        return await self._call(
            "delete_key",
            _redis_delete,
            lambda: self._fallback.delete_key(key),
            target=key,
            strict=True,
        )

    async def delete_prefix(self, prefix: str) -> int:
        normalized_prefix = str(prefix)

        async def _redis_delete_prefix() -> int:
            keys = [key async for key in self._client.scan_iter(match=f"{normalized_prefix}*")]
            if not keys:
                return 0
            return int(await self._client.delete(*keys) or 0)

        return await self._call(
            "delete_prefix",
            _redis_delete_prefix,
            lambda: self._fallback.delete_prefix(normalized_prefix),
            target=normalized_prefix,
            strict=True,
        )

    async def enqueue_json(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> dict[str, Any]:
        async def _redis_enqueue() -> dict[str, Any]:
            payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            if len(payload.encode("utf-8")) > int(self.settings.REDIS_MAX_PAYLOAD_BYTES):
                raise ValueError("redis queue payload exceeds configured limit")
            await self._client.rpush(str(key), payload)
            if ttl_seconds is not None:
                await self._client.expire(str(key), max(int(ttl_seconds), 1))
            return {"enqueued": True, "degraded": False}

        return await self._call(
            "enqueue_json",
            _redis_enqueue,
            lambda: self._fallback.enqueue_json(key, value, ttl_seconds=ttl_seconds),
            target=key,
        )

    async def pop_json(self, key: str) -> Any | None:
        async def _redis_pop() -> Any | None:
            raw = await self._client.lpop(str(key))
            if raw is None:
                return None
            return json.loads(raw)

        return await self._call("pop_json", _redis_pop, lambda: self._fallback.pop_json(key), target=key)

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        async def _redis_lease() -> dict[str, Any]:
            acquired = await self._client.set(str(key), str(owner), nx=True, px=max(int(ttl_seconds * 1000), 1))
            current_owner = str(owner) if acquired else await self._client.get(str(key))
            return {"acquired": bool(acquired), "owner": current_owner}

        return await self._call(
            "try_acquire_lease",
            _redis_lease,
            lambda: self._fallback.try_acquire_lease(key, owner=owner, ttl_seconds=ttl_seconds),
            target=key,
            strict=True,
        )

    async def renew_lease(self, key: str, *, owner: str, ttl_seconds: float) -> dict[str, Any]:
        async def _redis_renew() -> dict[str, Any]:
            renewed = await self._client.eval(
                self._LEASE_RENEW_SCRIPT,
                1,
                str(key),
                str(owner),
                str(max(int(ttl_seconds * 1000), 1)),
            )
            return {"renewed": bool(renewed), "owner": str(owner) if renewed else await self._client.get(str(key))}

        return await self._call(
            "renew_lease",
            _redis_renew,
            lambda: self._fallback.renew_lease(key, owner=owner, ttl_seconds=ttl_seconds),
            target=key,
            strict=True,
        )

    async def release_lease(self, key: str, *, owner: str) -> bool:
        async def _redis_release() -> bool:
            released = await self._client.eval(self._LEASE_RELEASE_SCRIPT, 1, str(key), str(owner))
            return bool(released)

        return await self._call(
            "release_lease",
            _redis_release,
            lambda: self._fallback.release_lease(key, owner=owner),
            target=key,
            strict=True,
        )

    async def duplicate_guard(self, key: str, *, ttl_seconds: float) -> dict[str, Any]:
        async def _redis_guard() -> dict[str, Any]:
            acquired = await self._client.set(str(key), "1", nx=True, px=max(int(ttl_seconds * 1000), 1))
            return {"acquired": bool(acquired)}

        return await self._call(
            "duplicate_guard",
            _redis_guard,
            lambda: self._fallback.duplicate_guard(key, ttl_seconds=ttl_seconds),
            target=key,
            strict=True,
        )

    async def rate_limit(self, bucket: str, *, limit: int, window_seconds: float) -> dict[str, Any]:
        async def _redis_limit() -> dict[str, Any]:
            key = str(bucket)
            count = await self._client.incr(key)
            if int(count) == 1:
                await self._client.expire(key, max(int(window_seconds), 1))
            allowed = int(count) <= int(limit)
            ttl = await self._client.ttl(key)
            return {"allowed": allowed, "retry_after_seconds": 0.0 if allowed else max(float(ttl), 0.0)}

        return await self._call(
            "rate_limit",
            _redis_limit,
            lambda: self._fallback.rate_limit(bucket, limit=limit, window_seconds=window_seconds),
            target=bucket,
            strict=True,
        )

    async def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        fallback_unsubscribe = await self._fallback.subscribe(topic, callback)
        client = self._pubsub_client
        if client is None:
            logger.warning(
                "Redis subscribe degraded: topic=%s error=%s pid=%s pool=%s",
                topic,
                "redis_dependency_unavailable",
                os.getpid(),
                self._connection_pool_summary(client),
            )
            return fallback_unsubscribe

        pubsub = client.pubsub()
        stopped = asyncio.Event()
        started = time.perf_counter()
        logger.debug(
            "Redis subscribe begin: topic=%s pid=%s timeout_seconds=%.3f pool=%s",
            topic,
            os.getpid(),
            max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 0.001),
            self._connection_pool_summary(client),
        )

        try:
            await asyncio.wait_for(
                pubsub.subscribe(str(topic)),
                timeout=max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 0.001),
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "Redis subscribe degraded: topic=%s error=%s pid=%s latency_ms=%.3f pool=%s",
                topic,
                type(exc).__name__,
                os.getpid(),
                latency_ms,
                self._connection_pool_summary(client),
            )
            close_started = time.perf_counter()
            try:
                await pubsub.close()
            except Exception:
                logger.warning(
                    "Redis subscribe degraded close failed: topic=%s pid=%s pool=%s",
                    topic,
                    os.getpid(),
                    self._connection_pool_summary(client),
                    exc_info=True,
                )
            else:
                logger.debug(
                    "Redis subscribe degraded close completed: topic=%s pid=%s latency_ms=%.3f pool=%s",
                    topic,
                    os.getpid(),
                    (time.perf_counter() - close_started) * 1000,
                    self._connection_pool_summary(client),
                )
            return fallback_unsubscribe
        logger.debug(
            "Redis subscribe ready: topic=%s pid=%s latency_ms=%.3f pool=%s",
            topic,
            os.getpid(),
            (time.perf_counter() - started) * 1000,
            self._connection_pool_summary(client),
        )

        async def _listen() -> None:
            try:
                async for message in pubsub.listen():
                    if stopped.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    envelope = json.loads(data) if isinstance(data, str) else {}
                    result = callback(envelope)
                    if inspect.isawaitable(result):
                        await result
            except Exception as exc:
                logger.warning(
                    "Redis subscribe listener degraded: topic=%s error=%s pid=%s pool=%s",
                    topic,
                    type(exc).__name__,
                    os.getpid(),
                    self._connection_pool_summary(client),
                )
            finally:
                close_started = time.perf_counter()
                try:
                    await pubsub.close()
                except Exception:
                    logger.warning(
                        "Redis subscribe listener close failed: topic=%s pid=%s pool=%s",
                        topic,
                        os.getpid(),
                        self._connection_pool_summary(client),
                        exc_info=True,
                    )
                else:
                    logger.debug(
                        "Redis subscribe listener closed: topic=%s pid=%s latency_ms=%.3f pool=%s",
                        topic,
                        os.getpid(),
                        (time.perf_counter() - close_started) * 1000,
                        self._connection_pool_summary(client),
                    )

        task = asyncio.create_task(_listen(), name=f"redis-subscribe-{topic}")

        def unsubscribe() -> asyncio.Task | None:
            stopped.set()
            fallback_unsubscribe()
            if task.done():
                return None
            task.cancel()
            return task

        return unsubscribe

    async def publish(self, topic: str, envelope: dict[str, Any]) -> dict[str, Any]:
        async def _redis_publish() -> dict[str, Any]:
            payload = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
            if len(payload.encode("utf-8")) > int(self.settings.REDIS_MAX_PAYLOAD_BYTES):
                raise ValueError("redis publish payload exceeds configured limit")
            delivered = await self._client.publish(str(topic), payload)
            return {"published": True, "delivered": int(delivered), "degraded": False}

        return await self._call("publish", _redis_publish, lambda: self._fallback.publish(topic, envelope), target=topic)

    async def wakeup(self, key: str) -> dict[str, Any]:
        async def _redis_wakeup() -> dict[str, Any]:
            wake_key = str(key)
            await self._client.incr(wake_key)
            await self._client.expire(wake_key, 60)
            delivered = await self._client.publish(f"wakeup:{wake_key}", "1")
            return {"woken": True, "delivered": int(delivered), "degraded": False}

        return await self._call("wakeup", _redis_wakeup, lambda: self._fallback.wakeup(key), target=key)

    async def wait_wakeup(self, key: str, *, timeout_seconds: float) -> dict[str, Any]:
        async def _redis_wait() -> dict[str, Any]:
            deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
            wake_key = str(key)
            channel = f"wakeup:{wake_key}"
            redis_operation_timeout = max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 0.001)

            async def _consume_wakeup() -> int:
                return int(
                    await asyncio.wait_for(
                        self._client.eval(self._WAKEUP_CONSUME_SCRIPT, 1, wake_key),
                        timeout=redis_operation_timeout,
                    )
                    or 0
                )

            subscriber = await self._ensure_wakeup_subscriber(channel)
            if subscriber is None:
                # Subscriber could not be established (no client / failed to
                # subscribe within the operation timeout). Fall back to a
                # plain consume attempt — we'll either find a pre-existing
                # counter or return woken=False without ever creating an
                # ephemeral pubsub connection.
                consumed = await _consume_wakeup()
                return {"woken": bool(consumed)}
            while True:
                # Clear the event *before* attempting consume so that a
                # publish racing with this consume still leaves the event
                # set and is observed by the subsequent wait.
                subscriber.event.clear()
                consumed = await _consume_wakeup()
                if consumed:
                    return {"woken": True}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"woken": False}
                try:
                    await asyncio.wait_for(subscriber.event.wait(), timeout=remaining)
                except TimeoutError:
                    return {"woken": False}
                if subscriber.is_failed():
                    # Subscription died mid-wait. Try one last consume in
                    # case a publish slipped through, then exit.
                    consumed = await _consume_wakeup()
                    return {"woken": bool(consumed)}

        # Outer safety timeout: the inner _redis_wait already enforces a
        # monotonic-clock deadline, so under normal conditions it will return
        # within ~timeout_seconds. We still wrap with apply_timeout=True as a
        # backstop in case a bug, a stuck EVAL on a dead connection, or a
        # blocked event loop pushes runtime well past the intended deadline.
        # Buffer = max(REDIS_OPERATION_TIMEOUT_SECONDS, 1s) gives _redis_wait
        # room for one extra consume cycle after the deadline.
        safety_buffer = max(float(self.settings.REDIS_OPERATION_TIMEOUT_SECONDS), 1.0)
        outer_timeout = max(float(timeout_seconds), 0.0) + safety_buffer
        return await self._call(
            "wait_wakeup",
            _redis_wait,
            lambda: self._fallback.wait_wakeup(key, timeout_seconds=timeout_seconds),
            target=key,
            timeout_seconds=outer_timeout,
            apply_timeout=True,
        )


_COORDINATOR: DisabledRedisCoordinator | InProcessRedisCoordinator | RedisCoordinator | None = None


def create_redis_coordinator(settings: Settings = app_settings) -> DisabledRedisCoordinator | InProcessRedisCoordinator | RedisCoordinator:
    if not settings.REDIS_ENABLED:
        return DisabledRedisCoordinator(settings=settings)
    return RedisCoordinator(settings=settings)


def get_redis_coordinator() -> DisabledRedisCoordinator | InProcessRedisCoordinator | RedisCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = create_redis_coordinator(app_settings)
    return _COORDINATOR


def reset_redis_coordinator_for_tests() -> None:
    global _COORDINATOR
    _COORDINATOR = None
