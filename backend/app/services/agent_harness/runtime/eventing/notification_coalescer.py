from __future__ import annotations

import asyncio
import logging
import weakref
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PublishEnvelopeFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _Pending:
    envelope: dict[str, Any]
    timer: asyncio.TimerHandle


class NotificationCoalescer:
    """Short-window publish coalescer for high-frequency conversation event
    notifications.

    Per-(loop) instance. For every `(user_id, conversation_id, event_type)`
    key, a 50ms timer collects the highest-sequence envelope seen and fires a
    single publish when it expires. Lifecycle / non-whitelisted event types
    bypass the timer and ALSO flush any pending entries for the same
    conversation first, so downstream consumers always observe notifications
    in monotonic sequence order.

    Safe because the pubsub envelope is metadata-only: SSE consumers re-fetch
    by `after_sequence` on any notification, so collapsing N notifications
    into 1 just means consumers fetch all N events in one round-trip.
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        window_seconds: float,
        coalesce_types: frozenset[str],
        publish: PublishEnvelopeFn,
    ) -> None:
        self._loop = loop
        self._window = max(float(window_seconds), 0.0)
        self._types = frozenset(coalesce_types)
        self._publish = publish
        self._pending: dict[tuple[int, str, str], _Pending] = {}
        self._by_conv: dict[tuple[int, str], set[tuple[int, str, str]]] = defaultdict(set)
        self._inflight: set[asyncio.Task] = set()
        self._closed = False
        self.coalesced_count = 0
        self.flush_count = 0
        self.passthrough_count = 0

    def metrics(self) -> dict[str, int]:
        return {
            "coalesced": int(self.coalesced_count),
            "flushed": int(self.flush_count),
            "passthrough": int(self.passthrough_count),
            "pending": len(self._pending),
            "inflight": len(self._inflight),
        }

    def submit(self, envelope: dict[str, Any]) -> None:
        if not isinstance(envelope, dict):
            return
        event_type = str(envelope.get("event_type") or "")
        try:
            user_id = int(envelope.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0
        conversation_id = str(envelope.get("conversation_id") or "")
        if not user_id or not conversation_id or not event_type:
            self._fire(envelope)
            return
        conv_key = (user_id, conversation_id)
        if self._closed or event_type not in self._types:
            self._flush_conv(conv_key)
            self.passthrough_count += 1
            self._fire(envelope)
            return
        key = (user_id, conversation_id, event_type)
        existing = self._pending.get(key)
        if existing is not None:
            try:
                incoming_seq = int(envelope.get("sequence") or 0)
                existing_seq = int(existing.envelope.get("sequence") or 0)
            except (TypeError, ValueError):
                incoming_seq = 0
                existing_seq = 0
            if incoming_seq >= existing_seq:
                existing.envelope = envelope
            self.coalesced_count += 1
            return
        if self._window <= 0:
            self.flush_count += 1
            self._fire(envelope)
            return
        timer = self._loop.call_later(self._window, self._on_timer, key)
        self._pending[key] = _Pending(envelope=envelope, timer=timer)
        self._by_conv[conv_key].add(key)

    def _on_timer(self, key: tuple[int, str, str]) -> None:
        entry = self._pending.pop(key, None)
        if entry is None:
            return
        conv_key = (key[0], key[1])
        peers = self._by_conv.get(conv_key)
        if peers is not None:
            peers.discard(key)
            if not peers:
                self._by_conv.pop(conv_key, None)
        self.flush_count += 1
        self._fire(entry.envelope)

    def _flush_conv(self, conv_key: tuple[int, str]) -> None:
        keys = self._by_conv.pop(conv_key, None)
        if not keys:
            return
        for key in list(keys):
            entry = self._pending.pop(key, None)
            if entry is None:
                continue
            entry.timer.cancel()
            self.flush_count += 1
            self._fire(entry.envelope)

    def _fire(self, envelope: dict[str, Any]) -> None:
        try:
            task = self._loop.create_task(self._publish(dict(envelope)))
        except RuntimeError:
            # Loop is closing — best-effort drop, the durable event_log row
            # remains and downstream consumers can still re-fetch by sequence.
            return
        self._inflight.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._inflight.discard(task)
        try:
            task.result()
        except Exception:  # noqa: BLE001
            logger.info("Conversation event coalesced publish failed", exc_info=True)

    async def aclose(self) -> None:
        self._closed = True
        for entry in list(self._pending.values()):
            entry.timer.cancel()
        pending_envelopes = [entry.envelope for entry in self._pending.values()]
        self._pending.clear()
        self._by_conv.clear()
        for envelope in pending_envelopes:
            self.flush_count += 1
            self._fire(envelope)
        if self._inflight:
            await asyncio.gather(*list(self._inflight), return_exceptions=True)


_coalescers: dict[int, tuple[weakref.ReferenceType[asyncio.AbstractEventLoop], NotificationCoalescer]] = {}


def _sweep_dead_loops() -> None:
    stale = [loop_id for loop_id, (loop_ref, _) in _coalescers.items() if loop_ref() is None]
    for loop_id in stale:
        _coalescers.pop(loop_id, None)


def get_or_create_for_running_loop(
    *,
    publish: PublishEnvelopeFn,
    window_seconds: float,
    coalesce_types: frozenset[str],
) -> NotificationCoalescer | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _sweep_dead_loops()
    loop_id = id(loop)
    entry = _coalescers.get(loop_id)
    if entry is not None:
        loop_ref, cached = entry
        if loop_ref() is loop:
            return cached
    coalescer = NotificationCoalescer(
        loop=loop,
        window_seconds=window_seconds,
        coalesce_types=coalesce_types,
        publish=publish,
    )
    try:
        loop_ref = weakref.ref(loop)
    except TypeError:
        return coalescer
    _coalescers[loop_id] = (loop_ref, coalescer)
    return coalescer


def all_coalescers() -> list[NotificationCoalescer]:
    _sweep_dead_loops()
    return [coalescer for _loop_ref, coalescer in _coalescers.values()]


def metrics_snapshot() -> dict[str, int]:
    totals = {"coalesced": 0, "flushed": 0, "passthrough": 0, "pending": 0, "inflight": 0}
    for coalescer in all_coalescers():
        for k, v in coalescer.metrics().items():
            totals[k] = totals.get(k, 0) + int(v)
    totals["loops"] = len(_coalescers)
    return totals


def reset_for_tests() -> None:
    _coalescers.clear()
