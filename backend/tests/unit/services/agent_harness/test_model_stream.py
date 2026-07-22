from __future__ import annotations

from app.services.llm_runtime import LlmStreamChunk as StreamChunk
from app.services.agent_harness.runtime.execution_support.model_stream import ModelStreamTurn


def test_model_stream_turn_accumulates_chunks():
    turn = ModelStreamTurn()

    first = turn.observe(StreamChunk(content="hel"))
    second = turn.observe(StreamChunk(content="lo", usage={"input_tokens": 1, "output_tokens": 2}))
    third = turn.observe(StreamChunk(finish_reason="stop"))

    assert first["has_content"] is True
    assert second["has_usage"] is True
    assert third["has_finish_reason"] is True
    assert turn.text == "hello"
    assert turn.text_parts == ["hel", "lo"]
    assert turn.usage == {"input_tokens": 1, "output_tokens": 2}
    assert turn.finish_reason == "stop"
    assert turn.chunk_count == 3
    assert turn.content_chunk_count == 2
    assert turn.had_activity is True


def test_model_stream_turn_tracks_tool_argument_diagnostics():
    turn = ModelStreamTurn()

    effect = turn.observe(
        StreamChunk(
            diagnostics={
                "provider_event_kind": "tool_call_arguments_delta",
                "tool_call_id": "call-1",
                "tool_name": "bash",
                "argument_delta_chars": 7,
                "argument_chars": 7,
                "argument_chunk_count": 1,
            },
        )
    )

    assert effect["provider_event_kind"] == "tool_call_arguments_delta"
    assert turn.provider_tool_call_argument_delta_count == 1
    payload = turn.diagnostics_payload()
    assert payload["tool_call_argument_delta_count"] == 1
    assert payload["last_tool_argument_delta"]["tool_name"] == "bash"


def test_model_stream_turn_keeps_content_that_arrives_after_tool_argument_streaming():
    turn = ModelStreamTurn()

    turn.observe(StreamChunk(content="我现在开始创建 PPT。"))
    turn.observe(
        StreamChunk(
            diagnostics={
                "provider_event_kind": "tool_call_arguments_delta",
                "tool_call_id": "call-1",
                "tool_name": "write_file",
                "argument_delta_chars": 12,
                "argument_chars": 12,
                "argument_chunk_count": 1,
            },
        )
    )
    turn.observe(StreamChunk(content='class="hero"'))
    turn.observe(
        StreamChunk(
            tool_calls=[{"id": "call-1", "name": "write_file", "arguments": {"path": "index.html"}}]
        )
    )
    turn.observe(StreamChunk(finish_reason="tool_calls"))

    # Content streamed alongside tool-call arguments is retained so the persisted
    # assistant_text matches exactly what was streamed to the client.
    assert turn.text == '我现在开始创建 PPT。class="hero"'
    assert turn.tool_calls == [{"id": "call-1", "name": "write_file", "arguments": {"path": "index.html"}}]


def test_model_stream_turn_restores_buffered_content_when_turn_finishes_without_tool_call():
    turn = ModelStreamTurn()

    turn.observe(StreamChunk(content="说明："))
    turn.observe(
        StreamChunk(
            diagnostics={
                "provider_event_kind": "tool_call_arguments_delta",
                "tool_call_id": "call-1",
                "tool_name": "write_file",
                "argument_delta_chars": 5,
                "argument_chars": 5,
                "argument_chunk_count": 1,
            },
        )
    )
    turn.observe(StreamChunk(content="后续正文"))
    turn.observe(StreamChunk(finish_reason="stop"))

    assert turn.text == "说明：后续正文"

