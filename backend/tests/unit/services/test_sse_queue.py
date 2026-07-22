from __future__ import annotations

import logging

import pytest

from app.services.sse_queue import bounded_queue, put_coalesced_nowait, put_marker_nowait


@pytest.mark.asyncio
async def test_put_coalesced_nowait_keeps_latest_item_when_queue_is_full():
    queue = bounded_queue(1)
    put_coalesced_nowait(queue, {"seq": 1}, name="test.realtime")
    put_coalesced_nowait(queue, {"seq": 2}, name="test.realtime")

    assert queue.qsize() == 1
    assert queue.get_nowait() == {"seq": 2}


@pytest.mark.asyncio
async def test_put_marker_nowait_keeps_one_user_marker_under_repeated_notifications():
    queue = bounded_queue(1000)

    for seq in range(1000):
        put_marker_nowait(queue, {"lane": "user", "seq": seq}, name="test.marker")

    assert queue.qsize() == 1
    assert queue.get_nowait() == {"lane": "user", "seq": 999}


@pytest.mark.asyncio
async def test_put_marker_nowait_keeps_one_user_and_one_runtime_marker():
    queue = bounded_queue(2)
    put_marker_nowait(queue, {"lane": "user", "seq": 1}, name="test.marker")
    put_marker_nowait(queue, {"kind": "runtime", "seq": 2}, name="test.marker")
    put_marker_nowait(queue, {"lane": "user", "seq": 3}, name="test.marker")
    put_marker_nowait(queue, {"kind": "runtime", "seq": 4}, name="test.marker")

    assert queue.qsize() == 2
    assert queue.get_nowait() == {"lane": "user", "seq": 3}
    assert queue.get_nowait() == {"kind": "runtime", "seq": 4}


@pytest.mark.asyncio
async def test_put_marker_nowait_coalesces_duplicate_markers_without_overflow_warning(caplog):
    queue = bounded_queue(1)

    with caplog.at_level(logging.WARNING, logger="app.services.sse_queue"):
        for seq in range(1000):
            put_marker_nowait(queue, {"lane": "user", "seq": seq}, name="test.marker")

    assert queue.qsize() == 1
    assert queue.get_nowait() == {"lane": "user", "seq": 999}
    assert "SSE queue overflow" not in caplog.text
