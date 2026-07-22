from __future__ import annotations

from app.services.agent_harness.runtime.execution_support.stream_diagnostics import (
    build_stream_diagnostics_payload,
    new_stream_diagnostics_state,
    record_stream_chunk_diagnostics,
)


def test_stream_diagnostics_tracks_tool_argument_deltas():
    state = new_stream_diagnostics_state()

    record_stream_chunk_diagnostics(
        state,
        {
            "provider_event_kind": "tool_call_arguments_delta",
            "tool_call_id": "call-1",
            "tool_call_index": 0,
            "tool_name": "bash",
            "argument_delta_chars": 4,
            "argument_chars": 4,
            "argument_chunk_count": 1,
        },
    )
    record_stream_chunk_diagnostics(
        state,
        {
            "provider_event_kind": "content_delta",
            "delta_chars": 3,
        },
    )

    payload = build_stream_diagnostics_payload(
        chunk_count=2,
        content_chunk_count=1,
        tool_call_chunk_count=1,
        usage_chunk_count=0,
        usage_only_chunk_count=0,
        finish_reason_chunk_count=0,
        provider_usage_only_without_choices_count=0,
        provider_tool_call_argument_delta_count=1,
        provider_diagnostics_state=state,
    )

    assert payload["provider_diagnostics_summary"]["event_counts"]["tool_call_arguments_delta"] == 1
    assert payload["provider_diagnostics_summary"]["tool_argument_streams"][0]["tool_name"] == "bash"
    assert payload["last_tool_argument_delta"]["argument_delta_chars"] == 4



