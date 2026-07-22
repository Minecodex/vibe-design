from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.apimart_client import ApimartClient
from app.services.ollama_client import OllamaClient


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, lines: list[str] | None = None):
        self._lines = lines or ["data: [DONE]"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""


class _FakeAsyncClient:
    last_timeout = None
    stream_lines = ["data: [DONE]"]

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        _FakeAsyncClient.last_timeout = self.timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        class _Response:
            status_code = 200
            text = "{}"

            def json(self):
                return {"choices": []}

        return _Response()

    def stream(self, *args, **kwargs):
        return _FakeStreamResponse(lines=list(self.stream_lines))


@pytest.mark.asyncio
async def test_apimart_stream_timeout_is_500_seconds(monkeypatch):
    monkeypatch.setattr("app.services.apimart_client.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.stream_lines = ["data: [DONE]"]

    client = ApimartClient("test-key")
    async for _chunk in client.chat_completions_stream_events(
        model_name="kimi-k2.5",
        messages=[{"role": "user", "content": "hello"}],
    ):
        pass

    assert _FakeAsyncClient.last_timeout == 500


@pytest.mark.asyncio
async def test_apimart_non_stream_timeout_uses_extended_read_budget(monkeypatch):
    monkeypatch.setattr("app.services.apimart_client.httpx.AsyncClient", _FakeAsyncClient)

    client = ApimartClient("test-key")
    await client.chat_completions(
        model_name="kimi-k2.5",
        messages=[{"role": "user", "content": "hello"}],
    )

    timeout = _FakeAsyncClient.last_timeout
    assert timeout.connect == 15.0
    assert timeout.read == 500
    assert timeout.write == 120.0
    assert timeout.pool == 15.0


@pytest.mark.asyncio
async def test_ollama_stream_timeout_is_500_seconds(monkeypatch):
    monkeypatch.setattr("app.services.ollama_client.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.stream_lines = ["data: [DONE]"]

    client = OllamaClient("http://localhost:11434")
    async for _chunk in client.chat_completions_stream(
        model_name="llama3",
        messages=[{"role": "user", "content": "hello"}],
    ):
        pass

    assert _FakeAsyncClient.last_timeout == 500


@pytest.mark.asyncio
async def test_ollama_stream_events_accepts_sse_data_lines_without_space(monkeypatch):
    monkeypatch.setattr("app.services.ollama_client.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.stream_lines = [
        'data:{"choices":[{"delta":{"content":"hello"}}]}',
        "",
        "data:[DONE]",
    ]

    client = OllamaClient("http://localhost:11434")
    chunks = [
        chunk
        async for chunk in client.stream_chat_completions_events_raw(
            model_name="llama3",
            messages=[{"role": "user", "content": "hello"}],
        )
    ]

    assert chunks == [{"choices": [{"delta": {"content": "hello"}}]}]


@pytest.mark.asyncio
async def test_apimart_stream_events_accepts_sse_data_lines_without_space(monkeypatch):
    monkeypatch.setattr("app.services.apimart_client.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.stream_lines = [
        'data:{"choices":[{"delta":{"content":"hello"}}]}',
        "",
        "data:[DONE]",
    ]

    client = ApimartClient("test-key")
    chunks = [
        chunk
        async for chunk in client.chat_completions_stream_events(
            model_name="kimi-k2.5",
            messages=[{"role": "user", "content": "hello"}],
        )
    ]

    assert chunks == [{"choices": [{"delta": {"content": "hello"}}]}]
