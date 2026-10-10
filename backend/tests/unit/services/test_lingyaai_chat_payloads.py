import pytest

from app.services.builtin_provider import LingyaAiBuiltinProvider


def test_lingyaai_auth_headers_reject_blank_api_key_before_httpx():
    with pytest.raises(ValueError, match="APIMart API key.*required"):
        provider = LingyaAiBuiltinProvider("   ")
        provider._auth_headers()


def test_lingyaai_chat_payload_omits_temperature_for_marked_models(monkeypatch):
    provider = LingyaAiBuiltinProvider("test-key")

    payload = provider._build_chat_payload(
        model_name="claude-opus-4-7",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        stream=False,
        max_tokens=600,
        tools=[
            {
                "type": "function",
                "function": {"name": "resolve_selection", "parameters": {"type": "object"}},
            }
        ],
    )

    assert "temperature" not in payload
    assert payload["max_tokens"] == 600
    assert payload["tools"][0]["function"]["name"] == "resolve_selection"


def test_lingyaai_chat_payload_keeps_temperature_for_unmarked_models(monkeypatch):
    provider = LingyaAiBuiltinProvider("test-key")

    payload = provider._build_chat_payload(
        model_name="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        stream=False,
        max_tokens=0,
        tools=None,
    )

    assert payload["temperature"] == 0.1
    assert "max_tokens" not in payload


def test_lingyaai_stream_chat_payload_omits_temperature_and_keeps_stream_options():
    provider = LingyaAiBuiltinProvider("test-key")

    payload = provider._build_chat_payload(
        model_name="gemini-3.1-pro-preview-thinking",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        stream=True,
        max_tokens=0,
        tools=None,
    )

    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert "temperature" not in payload
