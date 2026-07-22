from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.execution_support.harness_model_provider import HarnessModelProvider
from app.services.llm_runtime import LlmConnectionFailure, LlmStreamChunk


class _ReadErrorThenSuccessClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_chat(self, request):
        self.calls += 1
        if self.calls == 1:
            raise LlmConnectionFailure(
                failure_kind="midstream_disconnect",
                retryable=True,
                raw_error_type="ReadError",
                raw_message="peer closed connection without sending complete message body",
                provider_name="builtin",
                model=request.model,
            )
        yield LlmStreamChunk(content="done")
        yield LlmStreamChunk(finish_reason="stop")


class _ReadErrorAfterContentClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_chat(self, request):
        self.calls += 1
        yield LlmStreamChunk(content="partial")
        raise LlmConnectionFailure(
            failure_kind="midstream_disconnect",
            retryable=True,
            raw_error_type="ReadError",
            raw_message="peer closed connection without sending complete message body",
            provider_name="builtin",
            model=request.model,
            stream_started=True,
            meaningful_output_seen=True,
        )


@pytest.mark.asyncio
async def test_chat_stream_retries_read_error_before_yielding(monkeypatch):
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.harness_model_provider.asyncio.sleep",
        _no_sleep,
    )
    stream_client = _ReadErrorThenSuccessClient()
    provider = HarnessModelProvider(stream_client=stream_client)

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="kimi-k2.5",
        )
    ]

    assert stream_client.calls == 2
    assert [chunk.content for chunk in chunks if chunk.content] == ["done"]


@pytest.mark.asyncio
async def test_chat_stream_does_not_retry_read_error_after_content(monkeypatch):
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.harness_model_provider.asyncio.sleep",
        _no_sleep,
    )
    stream_client = _ReadErrorAfterContentClient()
    provider = HarnessModelProvider(stream_client=stream_client)
    chunks: list[LlmStreamChunk] = []

    with pytest.raises(LlmConnectionFailure):
        async for chunk in provider.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="kimi-k2.5",
        ):
            chunks.append(chunk)

    assert stream_client.calls == 1
    assert [chunk.content for chunk in chunks if chunk.content] == ["partial"]


