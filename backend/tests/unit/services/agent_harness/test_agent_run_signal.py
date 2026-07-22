from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.agent_harness.runtime import agent_run_signal


@pytest.mark.asyncio
async def test_agent_run_cancel_signal_wakes_waiter_without_sensitive_payload(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(agent_run_signal, "get_redis_coordinator", lambda: coordinator)

    waiter = asyncio.create_task(
        agent_run_signal.wait_cancel_signal(7, "conv-cancel-signal", timeout_seconds=1)
    )
    await asyncio.sleep(0)

    publish_result = await agent_run_signal.publish_cancel_signal(7, "conv-cancel-signal")
    wait_result = await asyncio.wait_for(waiter, timeout=1)

    assert publish_result["published"] is True
    assert wait_result["woken"] is True
    assert wait_result["payload"] == {
        "type": "cancel_requested",
        "user_id": 7,
        "conversation_id": "conv-cancel-signal",
    }
    payload_text = repr(wait_result["payload"]).lower()
    assert "prompt" not in payload_text
    assert "workspace" not in payload_text


@pytest.mark.asyncio
async def test_agent_run_cancel_signal_timeout_keeps_database_polling_fallback(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(agent_run_signal, "get_redis_coordinator", lambda: coordinator)

    result = await agent_run_signal.wait_cancel_signal(7, "conv-no-signal", timeout_seconds=0.001)

    assert result == {"woken": False}


@pytest.mark.asyncio
async def test_cancel_signal_pool_shares_subscription_across_repeated_waits(monkeypatch):
    """Repeated wait_cancel_signal calls on the same (user, conv) must reuse a
    single underlying coordinator.subscribe, instead of opening/closing one
    pubsub per poll iteration."""
    agent_run_signal.reset_cancel_signal_pool_for_tests()
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))

    subscribe_calls: list[str] = []
    original_subscribe = coordinator.subscribe

    async def counting_subscribe(topic, callback):
        subscribe_calls.append(str(topic))
        return await original_subscribe(topic, callback)

    coordinator.subscribe = counting_subscribe  # type: ignore[assignment]
    monkeypatch.setattr(agent_run_signal, "get_redis_coordinator", lambda: coordinator)

    # Pre-warm: open a long-lived waiter so the pool entry persists across
    # the burst below (otherwise each ephemeral wait closes the underlying
    # subscription on its own and re-opens on the next call).
    keeper_event = asyncio.Event()

    async def keeper() -> dict:
        return await agent_run_signal.wait_cancel_signal(11, "conv-shared", timeout_seconds=2)

    keeper_task = asyncio.create_task(keeper())
    await asyncio.sleep(0)

    # Five quick waits with tiny timeouts — each enters and leaves the pool;
    # the underlying subscribe must still only run once (the initial open).
    for _ in range(5):
        result = await agent_run_signal.wait_cancel_signal(11, "conv-shared", timeout_seconds=0.001)
        assert result == {"woken": False}

    assert len(subscribe_calls) == 1
    assert subscribe_calls[0].endswith(_pool_topic_suffix(11, "conv-shared"))

    await agent_run_signal.publish_cancel_signal(11, "conv-shared")
    keeper_result = await asyncio.wait_for(keeper_task, timeout=1)
    assert keeper_result["woken"] is True


@pytest.mark.asyncio
async def test_cancel_signal_pool_isolates_different_conversations(monkeypatch):
    """Each (user, conv) pair must subscribe independently — pool keys do not
    collapse across conversations."""
    agent_run_signal.reset_cancel_signal_pool_for_tests()
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))

    subscribe_calls: list[str] = []
    original_subscribe = coordinator.subscribe

    async def counting_subscribe(topic, callback):
        subscribe_calls.append(str(topic))
        return await original_subscribe(topic, callback)

    coordinator.subscribe = counting_subscribe  # type: ignore[assignment]
    monkeypatch.setattr(agent_run_signal, "get_redis_coordinator", lambda: coordinator)

    async def quick_wait(uid, cid):
        return await agent_run_signal.wait_cancel_signal(uid, cid, timeout_seconds=0.001)

    await quick_wait(1, "conv-a")
    await quick_wait(2, "conv-b")

    assert len(subscribe_calls) == 2
    assert subscribe_calls[0] != subscribe_calls[1]


def _pool_topic_suffix(user_id: int, conversation_id: str) -> str:
    # Stable suffix of the cancel topic key so the test can assert on it
    # without depending on the full namespace prefix.
    from app.services.agent_harness.runtime.agent_run_signal import _cancel_topic

    full = _cancel_topic(user_id, conversation_id)
    return full[full.rfind(":"):]
