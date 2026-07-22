from __future__ import annotations

import asyncio

import pytest

from app.services.agent_harness.runtime.eventing.conversation_event_subscription_pool import (
    ConversationEventSubscriptionPool,
)


class _FakeBus:
    def __init__(self) -> None:
        self.subscribe_calls: list[tuple[str, str, tuple[int, str]]] = []
        self.unsubscribe_count = 0
        self._dispatchers: dict[tuple[int, str], list] = {}

    async def subscribe(self, *, kind, name, scope, callback):
        key = (int(scope.user_id or 0), str(scope.conversation_id or ""))
        self.subscribe_calls.append((kind, name, key))
        self._dispatchers.setdefault(key, []).append(callback)

        def _unsubscribe():
            self.unsubscribe_count += 1
            self._dispatchers.get(key, []).remove(callback)

        return _unsubscribe

    async def deliver(self, user_id: int, conversation_id: str, envelope: dict) -> None:
        for callback in list(self._dispatchers.get((int(user_id), str(conversation_id)), [])):
            result = callback(envelope)
            if asyncio.iscoroutine(result):
                await result


@pytest.mark.asyncio
async def test_subscription_pool_shares_one_redis_subscription_across_callbacks():
    bus = _FakeBus()
    pool = ConversationEventSubscriptionPool(bus=bus)

    received_a: list[dict] = []
    received_b: list[dict] = []
    received_c: list[dict] = []

    unsubscribe_a = await pool.subscribe(7, "conv-x", lambda env: received_a.append(env))
    unsubscribe_b = await pool.subscribe(7, "conv-x", lambda env: received_b.append(env))
    unsubscribe_c = await pool.subscribe(7, "conv-x", lambda env: received_c.append(env))

    # Only ONE underlying Redis subscription regardless of three local callbacks.
    assert len(bus.subscribe_calls) == 1
    assert pool.active_conversation_count() == 1

    await bus.deliver(7, "conv-x", {"sequence": 1})
    assert received_a == received_b == received_c == [{"sequence": 1}]

    await unsubscribe_a()
    await unsubscribe_b()
    # Still one subscription as long as at least one callback remains.
    assert bus.unsubscribe_count == 0
    assert pool.active_conversation_count() == 1

    await unsubscribe_c()
    # Last detach tears down the underlying Redis subscription.
    assert bus.unsubscribe_count == 1
    assert pool.active_conversation_count() == 0


@pytest.mark.asyncio
async def test_subscription_pool_separates_per_conversation():
    bus = _FakeBus()
    pool = ConversationEventSubscriptionPool(bus=bus)

    received_x: list[dict] = []
    received_y: list[dict] = []

    await pool.subscribe(1, "conv-x", lambda env: received_x.append(env))
    await pool.subscribe(1, "conv-y", lambda env: received_y.append(env))

    assert len(bus.subscribe_calls) == 2
    assert pool.active_conversation_count() == 2

    await bus.deliver(1, "conv-x", {"sequence": 11})
    assert received_x == [{"sequence": 11}]
    assert received_y == []


@pytest.mark.asyncio
async def test_subscription_pool_can_share_runtime_notifications():
    bus = _FakeBus()
    pool = ConversationEventSubscriptionPool(
        bus=bus,
        notification_name="conversation.runtime.updated",
        log_label="conversation runtime",
    )
    received_a: list[dict] = []
    received_b: list[dict] = []

    unsubscribe_a = await pool.subscribe(7, "conv-x", lambda env: received_a.append(env))
    unsubscribe_b = await pool.subscribe(7, "conv-x", lambda env: received_b.append(env))

    assert bus.subscribe_calls == [("notify", "conversation.runtime.updated", (7, "conv-x"))]
    assert pool.active_conversation_count() == 1

    await bus.deliver(7, "conv-x", {"reason": "runtime_updated"})

    assert received_a == received_b == [{"reason": "runtime_updated"}]

    await unsubscribe_a()
    await unsubscribe_b()
    assert bus.unsubscribe_count == 1
    assert pool.active_conversation_count() == 0
