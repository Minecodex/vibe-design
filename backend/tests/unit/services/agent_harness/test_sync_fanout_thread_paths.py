from __future__ import annotations

import asyncio

from app.services.agent_harness.runtime.agent_run_signal import publish_cancel_signal_sync
from app.services.agent_harness.runtime.context_projection_wakeup import wake_context_projection_workers_sync
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import (
    publish_event_notification_sync,
    publish_runtime_notification_sync,
)


def test_sync_fanout_helpers_do_not_create_throwaway_event_loops(monkeypatch):
    called: list[object] = []

    def _forbidden_run(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("asyncio.run must not be used from sync fanout helpers")

    monkeypatch.setattr(asyncio, "run", _forbidden_run)

    assert publish_event_notification_sync(
        {
            "conversation_id": "conv",
            "user_id": 1,
            "sequence": 1,
            "event_type": "message",
            "lane": "user",
        }
    ) is None
    assert publish_runtime_notification_sync(1, "conv") is None
    assert wake_context_projection_workers_sync("conv") is None
    assert publish_cancel_signal_sync(1, "conv") is None
    assert called == []
