from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.eventing.conversation_event_fanout import publish_transient_event


@pytest.mark.asyncio
async def test_publish_transient_event_keeps_full_event_outside_metadata():
    published: list[dict] = []

    class _FakeBus:
        async def publish(self, envelope):
            published.append(envelope.to_payload())
            return {"published": True}

    long_delta = "x" * 1024
    await publish_transient_event(
        {
            "conversation_id": "conv-1",
            "user_id": 7,
            "type": "presentation.block.delta",
            "event_type": "presentation.block.delta",
            "lane": "user",
            "payload": {"payload": {"field": "text", "delta": long_delta}},
            "transient": True,
        },
        bus=_FakeBus(),
    )

    assert published
    assert published[0]["event"]["payload"]["payload"]["delta"] == long_delta
    assert published[0]["metadata"] == {"event_type": "presentation.block.delta"}
