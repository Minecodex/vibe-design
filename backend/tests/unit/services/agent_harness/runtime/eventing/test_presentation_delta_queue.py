from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.eventing import presentation_delta_queue as queue


@pytest.fixture(autouse=True)
async def _reset_delta_queue():
    queue.reset_for_tests()
    yield
    await queue.aclose(flush=False)


def _payload(delta: str, *, block: str = "block-1") -> dict:
    return {
        "type": "presentation.block.delta",
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "block_key": block,
        "message_key": "message-1",
        "payload": {"field": "text", "delta": delta},
        "field": "text",
        "delta": delta,
    }


async def _enqueue(delta: str, *, block_id: str = "block-1") -> None:
    await queue.enqueue_presentation_delta(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        payload=_payload(delta, block=block_id),
        block_id=block_id,
        tool_call_id="call-1",
        parent_block_id="parent-1",
    )


@pytest.mark.asyncio
async def test_delta_queue_merges_same_block_before_flush(monkeypatch):
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS", 60.0)
    records: list[dict] = []

    def _append(*_args, **kwargs):
        records.append(kwargs)
        return {"lane": "user", "sequence": len(records), "conversation_id": "conv-1", "user_id": 7}

    monkeypatch.setattr(queue, "append_conversation_event", _append)
    monkeypatch.setattr(queue, "project_committed_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(queue, "publish_event_notification_sync", lambda *_args, **_kwargs: None)

    await _enqueue("hello ")
    await _enqueue("world")
    await queue.flush_pending()

    assert len(records) == 1
    assert records[0]["payload"]["delta"] == "hello world"


@pytest.mark.asyncio
async def test_delta_queue_splits_when_merged_chars_exceed_limit(monkeypatch):
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_MAX_MERGED_CHARS", 512)
    records: list[dict] = []

    def _append(*_args, **kwargs):
        records.append(kwargs)
        return {"lane": "user", "sequence": len(records), "conversation_id": "conv-1", "user_id": 7}

    monkeypatch.setattr(queue, "append_conversation_event", _append)
    monkeypatch.setattr(queue, "project_committed_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(queue, "publish_event_notification_sync", lambda *_args, **_kwargs: None)

    await _enqueue("a" * 400)
    await _enqueue("b" * 200)
    await queue.flush_pending()

    assert [record["payload"]["delta"] for record in records] == ["a" * 400, "b" * 200]


@pytest.mark.asyncio
async def test_delta_queue_retries_persist_once(monkeypatch):
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS", 60.0)
    calls = {"count": 0}

    def _append(*_args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary db outage")
        return {"lane": "user", "sequence": 1, "conversation_id": "conv-1", "user_id": 7}

    monkeypatch.setattr(queue, "append_conversation_event", _append)
    monkeypatch.setattr(queue, "project_committed_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(queue, "publish_event_notification_sync", lambda *_args, **_kwargs: None)

    await _enqueue("retry")
    await queue.flush_pending()

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_delta_queue_drops_oldest_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_MAX_BATCH_SIZE", 10)
    monkeypatch.setattr(queue, "HARNESS_PRESENTATION_DELTA_PERSIST_QUEUE_MAX_SIZE", 1)
    records: list[dict] = []

    def _append(*_args, **kwargs):
        records.append(kwargs)
        return {"lane": "user", "sequence": len(records), "conversation_id": "conv-1", "user_id": 7}

    monkeypatch.setattr(queue, "append_conversation_event", _append)
    monkeypatch.setattr(queue, "project_committed_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(queue, "publish_event_notification_sync", lambda *_args, **_kwargs: None)

    await _enqueue("first", block_id="block-1")
    await _enqueue("second", block_id="block-2")
    await queue.flush_pending()

    assert [record["payload"]["delta"] for record in records] == ["second"]
