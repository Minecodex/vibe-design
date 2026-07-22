import pytest

from app.services.agent_harness.runtime.eventing.audit_recorder import create_agent_audit_recorder


@pytest.mark.asyncio
async def test_harness_default_audit_recorder_is_noop():
    recorder = create_agent_audit_recorder("1776421922807_755492", "run_harness_1")

    await recorder.append_event(
        conversation_id="1776421922807_755492",
        agent_run_id="run_harness_1",
        event_type="run_started",
        phase="engine",
        payload={"web_search_enabled": True},
        source="harness",
    )
    await recorder.flush()
    await recorder.close()

    assert recorder is not None
