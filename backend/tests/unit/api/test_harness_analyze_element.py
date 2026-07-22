from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.harness import analyze_element
from app.schemas.harness import AnalyzeElementRequest


@pytest.mark.asyncio
async def test_harness_analyze_element_uses_fixed_mark_model(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMultimodalService:
        def __init__(self, db):
            self.db = db

        async def chat(self, **kwargs):
            captured.update(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "content": '["apple"]',
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "app.services.multimodal_service.MultimodalService",
        FakeMultimodalService,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.media_utils.resolve_url_for_api",
        lambda image_url, prefer="base64": {"type": "url", "url": image_url},
    )

    response = await analyze_element(
        AnalyzeElementRequest(
            image_url="https://example.com/image.png",
            relative_x=0.25,
            relative_y=0.5,
            language="en",
        ),
        db=object(),
        user=SimpleNamespace(id=9),
    )

    assert captured["billing_label"] == "billing.labels.mark_recognition"
    assert captured["provider_code"] == "builtin"
    assert response.labels == ["apple"]
