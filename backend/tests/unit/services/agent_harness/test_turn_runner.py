import pytest

from app.services.agent_harness.runtime.execution_support.turn_runner import ModelTurnError, TurnRunner
from app.services.llm_runtime import LlmStreamChunk as StreamChunk


class FakeProvider:
    def __init__(self, chunks=None, exc: Exception | None = None):
        self.chunks = chunks or []
        self.exc = exc
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_turn_runner_collects_text_tool_calls_usage_and_finish_reason():
    provider = FakeProvider(
        [
            StreamChunk(content="hello "),
            StreamChunk(content="world"),
            StreamChunk(tool_calls=[{"id": "call-1", "name": "artifact_session", "arguments": {"action": "list"}}]),
            StreamChunk(finish_reason="tool_calls", usage={"input_tokens": 3, "output_tokens": 4}),
        ]
    )

    result = await TurnRunner(provider).run(
        messages=[{"role": "user", "content": "hi"}],
        system="system",
        tools=[{"type": "function"}],
        model="test-model",
    )

    assert result.assistant_text == "hello world"
    assert result.tool_calls == [{"id": "call-1", "name": "artifact_session", "arguments": {"action": "list"}}]
    assert result.finish_reason == "tool_calls"
    assert result.usage == {"input_tokens": 3, "output_tokens": 4}
    assert result.elapsed_ms >= 0
    assert provider.calls[0]["model"] == "test-model"


@pytest.mark.asyncio
async def test_turn_runner_keeps_mixed_content_that_arrives_after_tool_argument_streaming():
    provider = FakeProvider(
        [
            StreamChunk(content="我现在开始创建PPT结构。"),
            StreamChunk(
                diagnostics={
                    "provider_event_kind": "tool_call_arguments_delta",
                    "tool_call_id": "call-1",
                    "tool_name": "write_file",
                    "argument_delta_chars": 8,
                    "argument_chars": 8,
                    "argument_chunk_count": 1,
                }
            ),
            StreamChunk(content='data-theme="ink"'),
            StreamChunk(tool_calls=[{"id": "call-1", "name": "write_file", "arguments": {"path": "index.html"}}]),
            StreamChunk(finish_reason="tool_calls", usage={"input_tokens": 3, "output_tokens": 4}),
        ]
    )

    result = await TurnRunner(provider).run(
        messages=[{"role": "user", "content": "hi"}],
        system="system",
        tools=[{"type": "function"}],
        model="test-model",
    )

    # Content interleaved with tool-call argument streaming is retained so the
    # persisted assistant_text matches exactly what was streamed to the client.
    assert result.assistant_text == '我现在开始创建PPT结构。data-theme="ink"'
    assert result.tool_calls == [{"id": "call-1", "name": "write_file", "arguments": {"path": "index.html"}}]


@pytest.mark.asyncio
async def test_turn_runner_wraps_provider_errors_with_elapsed_ms():
    provider = FakeProvider(exc=RuntimeError("boom"))

    with pytest.raises(ModelTurnError) as exc_info:
        await TurnRunner(provider).run(messages=[], system=None, tools=[], model="test-model")

    assert isinstance(exc_info.value.original, RuntimeError)
    assert exc_info.value.elapsed_ms >= 0


def test_model_turn_runner_keeps_compatibility_aliases():
    from app.services.agent_harness.runtime.execution_support.turn_runner import (
        ModelTurnRunner,
        ModelTurnResult,
        TurnResult,
    )

    assert ModelTurnRunner is TurnRunner
    assert ModelTurnResult is TurnResult

