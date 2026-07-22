from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import settings


async def _authenticate(client, db_session):
    from app.core.security import create_access_token, get_password_hash
    from app.models.user import User

    suffix = uuid4().hex[:8]
    user = User(
        email=f"prompt-extractor-{suffix}@example.com",
        username=f"promptextractor-{suffix}",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return user


@pytest.mark.asyncio
async def test_prompt_extractor_requires_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    response = await client.post("/api/v1/extension/prompt-extractor/analyze")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_prompt_extractor_rejects_invalid_locale(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    await _authenticate(client, db_session)

    response = await client.post(
        "/api/v1/extension/prompt-extractor/analyze",
        data={"locale": "ja-JP"},
        files={"image": ("demo.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported locale"


@pytest.mark.asyncio
async def test_prompt_extractor_returns_prompt_and_cost(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    await _authenticate(client, db_session)

    async def fake_analyze(self, *, user_id, locale, image):
        assert user_id > 0
        assert locale == "zh-CN"
        assert image.filename == "demo.png"
        return SimpleNamespace(
            prompt="一只坐在窗边的白猫，电影感光影，柔和晨光，浅景深",
            prompts={
                "zh-CN": "一只坐在窗边的白猫，电影感光影，柔和晨光，浅景深",
                "en-US": "a white cat by a window, cinematic light, soft morning glow, shallow depth of field",
            },
            language="zh-CN",
            model="gemini-3.1-pro-preview",
            amount_cents=3,
        )

    monkeypatch.setattr(
        "app.services.prompt_extractor.PromptExtractorService.analyze",
        fake_analyze,
    )

    response = await client.post(
        "/api/v1/extension/prompt-extractor/analyze",
        data={"locale": "zh-CN"},
        files={"image": ("demo.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "prompt": "一只坐在窗边的白猫，电影感光影，柔和晨光，浅景深",
        "prompts": {
            "zh-CN": "一只坐在窗边的白猫，电影感光影，柔和晨光，浅景深",
            "en-US": "a white cat by a window, cinematic light, soft morning glow, shallow depth of field",
        },
        "language": "zh-CN",
        "model": "gemini-3.1-pro-preview",
        "amount_cents": 3,
    }
