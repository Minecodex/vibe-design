import pytest

from app.services.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_edit_image_posts_reference_urls_as_json(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "edit-1", "data": [{"url": "https://example.test/result.png"}]}

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json=None, headers=None, data=None, files=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["data"] = data
            captured["files"] = files
            return FakeResponse()

    monkeypatch.setattr("app.services.ollama_client.httpx.AsyncClient", FakeAsyncClient)

    result = await OllamaClient("https://ollama.example/v1", "test-key").edit_image(
        model_name="gpt-image-2",
        prompt="make variant",
        image_refs=["https://cdn.example.test/ref.png"],
        size="1024x1024",
        response_format=None,
        quality=None,
    )

    assert captured["url"] == "https://ollama.example/v1/images/edits"
    assert captured["json"] == {
        "model": "gpt-image-2",
        "prompt": "make variant",
        "size": "1024x1024",
        "image_urls": ["https://cdn.example.test/ref.png"],
    }
    assert captured["data"] is None
    assert captured["files"] is None
    assert result["result_values"] == ["https://example.test/result.png"]
