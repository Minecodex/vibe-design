from __future__ import annotations

import pytest

from app.services.llm_runtime.apimart import ApimartLlmStreamClient
from app.services.llm_runtime.types import LlmStreamRequest


class _FakeApimartClient:
    code = "fake"
    last_stream_provider_headers = {}

    def __init__(self) -> None:
        self.kwargs = None

    async def stream_chat_completions_events_raw(self, **kwargs):
        self.kwargs = kwargs
        yield {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}


class _UsageApimartClient(_FakeApimartClient):
    async def stream_chat_completions_events_raw(self, **kwargs):
        self.kwargs = kwargs
        yield {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 7,
                "prompt_tokens_details": {"cached_tokens": 64},
                "cache_read_input_tokens": 32,
                "cache_creation_input_tokens": 16,
            },
            "request_id": "req-1",
        }


@pytest.mark.asyncio
async def test_apimart_llm_stream_client_forwards_prompt_cache_key():
    raw_client = _FakeApimartClient()
    client = ApimartLlmStreamClient(raw_client)

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(
                model="GPT-5.4",
                messages=[{"role": "user", "content": "hello"}],
                prompt_cache_key="agent:conv-1",
            )
        )
    ]

    assert chunks[0].content == "ok"
    assert raw_client.kwargs["prompt_cache_key"] == "agent:conv-1"


@pytest.mark.asyncio
async def test_apimart_llm_stream_client_preserves_prompt_cache_usage_fields():
    raw_client = _UsageApimartClient()
    raw_client.last_stream_provider_headers = {"x_oneapi_request_id": "oneapi-1"}
    client = ApimartLlmStreamClient(raw_client)

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(
                model="GPT-5.4",
                messages=[{"role": "user", "content": "hello"}],
            )
        )
    ]

    usage_chunks = [chunk for chunk in chunks if chunk.usage]
    assert usage_chunks[-1].usage == {
        "input_tokens": 100,
        "output_tokens": 7,
        "cached_tokens": 64,
        "cache_read_tokens": 32,
        "cache_creation_tokens": 16,
        "provider_code": "fake",
        "oneapi_request_id": "oneapi-1",
        "request_id": "req-1",
    }
