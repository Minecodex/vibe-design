from __future__ import annotations

import pytest

from app.services.ollama_client import OllamaClient
from app.services.llm_runtime.ollama import OllamaLlmStreamClient
from app.services.llm_runtime.types import LlmStreamRequest


class _FakeOllamaClient:
    def __init__(self, events):
        self._events = events

    async def stream_chat_completions_events_raw(self, **_kwargs):
        for event in self._events:
            yield event


def test_ollama_client_keeps_openai_tool_choice_shape_by_default():
    client = OllamaClient("http://localhost:11434")
    tool_choice = {"type": "function", "function": {"name": "submit_quick_brief_schema"}}

    assert client._prepare_tool_choice(tool_choice) == tool_choice


def test_ollama_client_can_flatten_tool_choice_for_legacy_gateways():
    client = OllamaClient("http://localhost:11434", tool_choice_format="flat")

    assert client._prepare_tool_choice(
        {"type": "function", "function": {"name": "submit_quick_brief_schema"}}
    ) == {"type": "function", "name": "submit_quick_brief_schema"}


@pytest.mark.asyncio
async def test_ollama_llm_stream_client_emits_tool_calls_from_stream_deltas():
    client = OllamaLlmStreamClient(
        _FakeOllamaClient(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {
                                            "name": "shell_command",
                                            "arguments": '{"command":"Get-ChildItem"}',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [{"finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                },
            ]
        )
    )

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(model="GPT-5.4", messages=[{"role": "user", "content": "list files"}])
        )
    ]

    tool_call_chunks = [chunk for chunk in chunks if chunk.tool_calls]
    finish_chunks = [chunk for chunk in chunks if chunk.finish_reason]
    diagnostic_chunks = [chunk for chunk in chunks if chunk.diagnostics]

    assert diagnostic_chunks
    assert len(tool_call_chunks) == 1
    assert tool_call_chunks[0].tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "name": "shell_command",
            "arguments": {"command": "Get-ChildItem"},
        }
    ]
    assert finish_chunks[-1].finish_reason == "tool_calls"
    assert finish_chunks[-1].usage == {"input_tokens": 12, "output_tokens": 3, "provider_code": "ollama"}


@pytest.mark.asyncio
async def test_ollama_llm_stream_client_keeps_content_before_tool_call():
    client = OllamaLlmStreamClient(
        _FakeOllamaClient(
            [
                {"choices": [{"delta": {"content": "完整阶段成果：\n1. 主商品判断...\n"}}]},
                {"choices": [{"delta": {"content": "2. 结构细节...\n"}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_ask",
                                        "function": {
                                            "name": "ask_user",
                                            "arguments": (
                                                '{"title":"确认","submit_label":"提交","questions":[]}'
                                            ),
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [{"finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8},
                },
            ]
        )
    )

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(model="gpt-5.5", messages=[{"role": "user", "content": "确认前先输出正文"}])
        )
    ]

    assert "".join(chunk.content or "" for chunk in chunks) == "完整阶段成果：\n1. 主商品判断...\n2. 结构细节...\n"
    assert [chunk.tool_calls for chunk in chunks if chunk.tool_calls] == [
        [
            {
                "id": "call_ask",
                "type": "function",
                "name": "ask_user",
                "arguments": {
                    "title": "确认",
                    "submit_label": "提交",
                    "questions": [],
                },
            }
        ]
    ]


@pytest.mark.asyncio
async def test_ollama_llm_stream_client_flushes_tool_calls_without_explicit_finish_reason():
    client = OllamaLlmStreamClient(
        _FakeOllamaClient(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_2",
                                        "function": {
                                            "name": "write_file",
                                            "arguments": '{"path":"demo.txt"}',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        )
    )

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(model="GPT-5.4", messages=[{"role": "user", "content": "write demo"}])
        )
    ]

    tool_call_chunks = [chunk for chunk in chunks if chunk.tool_calls]
    finish_chunks = [chunk for chunk in chunks if chunk.finish_reason]

    assert tool_call_chunks[0].tool_calls == [
        {
            "id": "call_2",
            "type": "function",
            "name": "write_file",
            "arguments": {"path": "demo.txt"},
        }
    ]
    assert finish_chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_ollama_llm_stream_client_preserves_cache_usage_fields_when_present():
    client = OllamaLlmStreamClient(
        _FakeOllamaClient(
            [
                {
                    "choices": [{"finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 5,
                        "cached_tokens": 40,
                        "cache_read_tokens": 30,
                        "cache_creation_tokens": 10,
                    },
                }
            ]
        )
    )

    chunks = [
        chunk
        async for chunk in client.stream_chat(
            LlmStreamRequest(model="GPT-5.4", messages=[{"role": "user", "content": "hello"}])
        )
    ]

    assert chunks[-1].usage == {
        "input_tokens": 100,
        "output_tokens": 5,
        "cached_tokens": 40,
        "cache_read_tokens": 30,
        "cache_creation_tokens": 10,
        "provider_code": "ollama",
    }
