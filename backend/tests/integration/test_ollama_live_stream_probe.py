from __future__ import annotations

import os

import pytest

from app.services.llm_runtime.ollama import OllamaLlmStreamClient
from app.services.llm_runtime.types import LlmStreamRequest
from app.services.ollama_client import OllamaClient


def _live_ollama_enabled() -> bool:
    return os.getenv("RUN_OLLAMA_LIVE_STREAM_TEST") == "1"


@pytest.mark.skipif(not _live_ollama_enabled(), reason="set RUN_OLLAMA_LIVE_STREAM_TEST=1 to call live Ollama-compatible API")
@pytest.mark.asyncio
async def test_live_ollama_stream_keeps_content_before_ask_user_tool_call():
    base_url = os.environ["OLLAMA_BASE_URL"]
    api_key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_IMAGE_API_KEY") or "ollama"
    model = os.environ.get("OLLAMA_MULTIMODAL_MODEL") or "gpt-5.5"
    tool_choice_format = os.environ.get("OLLAMA_TOOL_CHOICE_FORMAT") or "openai"

    tool_schema = {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Render a decision card only after the assistant has already written "
                "the complete standalone summary the user needs to judge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "submit_label": {"type": "string"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "header": {"type": "string"},
                                "question": {"type": "string"},
                                "type": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "value": {"type": "string"},
                                        },
                                        "required": ["label", "value"],
                                    },
                                },
                            },
                            "required": ["id", "header", "question", "type", "options"],
                        },
                    },
                },
                "required": ["title", "submit_label", "questions"],
            },
        },
    }

    request = LlmStreamRequest(
        model=model,
        system=(
            "你必须先输出一段完整的《测试锁定卡》正文，至少包含 1、2、3 三条具体内容。"
            "正文完成之后，才调用 ask_user。不要只写引导语。"
        ),
        messages=[{"role": "user", "content": "请给出测试锁定卡，然后询问我是否确认。"}],
        tools=[tool_schema],
        temperature=0.2,
        max_tokens=2048,
    )
    stream_client = OllamaLlmStreamClient(
        OllamaClient(base_url, api_key=api_key, tool_choice_format=tool_choice_format)
    )

    chunks = [chunk async for chunk in stream_client.stream_chat(request)]
    text = "".join(chunk.content or "" for chunk in chunks)
    tool_calls = [tool_call for chunk in chunks for tool_call in (chunk.tool_calls or [])]

    assert text.strip(), "live provider returned a tool call without any prior streamed content"
    assert "测试锁定卡" in text
    assert tool_calls, "live provider did not call ask_user"
