from __future__ import annotations

import asyncio

import pytest

from app.services.agent_harness.runtime.eventing import notification_coalescer
from app.services.agent_harness.runtime.eventing.notification_coalescer import (
    NotificationCoalescer,
)

pytestmark = pytest.mark.asyncio


def _envelope(seq: int, event_type: str = "presentation.block.delta", *, uid: int = 1, cid: str = "conv-a"):
    return {
        "conversation_id": cid,
        "user_id": uid,
        "sequence": seq,
        "event_type": event_type,
        "run_id": "run-1",
    }


class _Recorder:
    def __init__(self) -> None:
        self.envelopes: list[dict] = []

    async def __call__(self, envelope: dict) -> None:
        self.envelopes.append(envelope)


async def _drain(coalescer: NotificationCoalescer) -> None:
    if coalescer._inflight:
        await asyncio.gather(*list(coalescer._inflight), return_exceptions=True)


async def test_burst_within_window_publishes_once_with_highest_sequence():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.05,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    for seq in range(1, 6):
        coalescer.submit(_envelope(seq))

    assert recorder.envelopes == []
    await asyncio.sleep(0.08)
    await _drain(coalescer)

    assert len(recorder.envelopes) == 1
    assert recorder.envelopes[0]["sequence"] == 5
    assert coalescer.coalesced_count == 4
    assert coalescer.flush_count == 1


async def test_events_separated_by_more_than_window_emit_twice():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.02,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(1))
    await asyncio.sleep(0.05)
    coalescer.submit(_envelope(2))
    await asyncio.sleep(0.05)
    await _drain(coalescer)

    assert [e["sequence"] for e in recorder.envelopes] == [1, 2]
    assert coalescer.flush_count == 2


async def test_lifecycle_event_flushes_pending_then_passthrough():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.05,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(1))
    coalescer.submit(_envelope(2))
    coalescer.submit(_envelope(3, event_type="presentation.block.complete"))

    await asyncio.sleep(0)
    await _drain(coalescer)

    # Order: flushed delta envelope (seq=2, the highest pending) then the
    # lifecycle envelope (seq=3) — preserving monotonic sequence at consumer.
    sequences = [(e["sequence"], e["event_type"]) for e in recorder.envelopes]
    assert sequences == [(2, "presentation.block.delta"), (3, "presentation.block.complete")]
    assert coalescer.passthrough_count == 1


async def test_different_conversations_do_not_share_keys():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.05,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(1, uid=1, cid="conv-a"))
    coalescer.submit(_envelope(2, uid=1, cid="conv-a"))
    coalescer.submit(_envelope(3, uid=2, cid="conv-b"))

    await asyncio.sleep(0.08)
    await _drain(coalescer)

    seqs = sorted(e["sequence"] for e in recorder.envelopes)
    assert seqs == [2, 3]
    convs = {(e["user_id"], e["conversation_id"]) for e in recorder.envelopes}
    assert convs == {(1, "conv-a"), (2, "conv-b")}


async def test_aclose_flushes_remaining_pending():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=1.0,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(7))
    coalescer.submit(_envelope(8, cid="conv-b"))
    assert recorder.envelopes == []

    await coalescer.aclose()

    seqs = sorted(e["sequence"] for e in recorder.envelopes)
    assert seqs == [7, 8]


async def test_non_whitelisted_event_passes_through_immediately():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.05,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(1, event_type="turn_completed"))
    await asyncio.sleep(0)
    await _drain(coalescer)

    assert [e["sequence"] for e in recorder.envelopes] == [1]
    assert coalescer.passthrough_count == 1
    assert coalescer.coalesced_count == 0


async def test_envelope_missing_required_fields_is_published_as_is():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.05,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit({"event_type": "presentation.block.delta", "sequence": 99})
    await asyncio.sleep(0)
    await _drain(coalescer)

    assert len(recorder.envelopes) == 1
    assert recorder.envelopes[0]["sequence"] == 99


async def test_zero_window_publishes_immediately():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()
    coalescer = NotificationCoalescer(
        loop=asyncio.get_running_loop(),
        window_seconds=0.0,
        coalesce_types=frozenset({"presentation.block.delta"}),
        publish=recorder,
    )

    coalescer.submit(_envelope(1))
    coalescer.submit(_envelope(2))
    await asyncio.sleep(0)
    await _drain(coalescer)

    assert [e["sequence"] for e in recorder.envelopes] == [1, 2]


async def test_get_or_create_returns_same_instance_per_loop():
    notification_coalescer.reset_for_tests()

    async def _pub(_env):
        return None

    a = notification_coalescer.get_or_create_for_running_loop(
        publish=_pub,
        window_seconds=0.01,
        coalesce_types=frozenset({"presentation.block.delta"}),
    )
    b = notification_coalescer.get_or_create_for_running_loop(
        publish=_pub,
        window_seconds=0.01,
        coalesce_types=frozenset({"presentation.block.delta"}),
    )
    assert a is b


async def test_metrics_snapshot_aggregates():
    notification_coalescer.reset_for_tests()
    recorder = _Recorder()

    async def _pub(env):
        await recorder(env)

    coalescer = notification_coalescer.get_or_create_for_running_loop(
        publish=_pub,
        window_seconds=0.02,
        coalesce_types=frozenset({"presentation.block.delta"}),
    )
    assert coalescer is not None
    coalescer.submit(_envelope(1))
    coalescer.submit(_envelope(2))
    await asyncio.sleep(0.05)
    await _drain(coalescer)

    snapshot = notification_coalescer.metrics_snapshot()
    assert snapshot["loops"] >= 1
    assert snapshot["coalesced"] >= 1
    assert snapshot["flushed"] >= 1
