from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.agent_harness.core.utils import media_download
from app.services.generated_uploads import build_generated_upload


class _FakeResponse:
    content = b"fake-media"

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, timeout: float):
        return _FakeResponse()


class _EmptyFakeResponse:
    content = b""

    def raise_for_status(self) -> None:
        return None


class _EmptyFakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, timeout: float):
        return _EmptyFakeResponse()


@pytest.mark.asyncio
async def test_downloaded_tool_media_is_registered_as_reference_asset(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(media_download.httpx, "AsyncClient", _FakeAsyncClient)

    conversation_dir = tmp_path / "users" / "7" / "conversations" / "conv-1"
    conversation_dir.mkdir(parents=True)
    ctx = SimpleNamespace(
        user_id=7,
        conversation_id="conv-1",
        conversation_dir=conversation_dir,
        run_id="run-1",
        subagent_run_id=None,
    )

    image_path = await media_download.download_media_to_workspace(
        ctx,
        "https://example.com/image.png",
        ext_hint="png",
        media_kind="image",
    )
    video_path = await media_download.download_media_to_workspace(
        ctx,
        "https://example.com/video.mp4",
        ext_hint="mp4",
        media_kind="video",
    )
    web_image_path = await media_download.download_media_to_workspace(
        ctx,
        "https://example.com/search.jpg",
        ext_hint="jpg",
        media_kind="web_search_image",
    )

    assert image_path.startswith("references/generated/generated_image_001/")
    assert video_path.startswith("references/generated/generated_video_001/")
    assert web_image_path.startswith("references/sources/web_image_001/")
    assert not (conversation_dir / "assets").exists()
    assert not (conversation_dir / ".work" / "downloads").exists()

    manifest = json.loads((conversation_dir / ".meta" / "assets_manifest.json").read_text(encoding="utf-8"))
    assert [asset["kind"] for asset in manifest["assets"]] == ["reference", "reference", "reference"]
    assert [asset["source"] for asset in manifest["assets"]] == ["image", "video", "web_search_image"]


@pytest.mark.asyncio
async def test_empty_downloaded_media_is_not_registered(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(media_download.httpx, "AsyncClient", _EmptyFakeAsyncClient)

    conversation_dir = tmp_path / "users" / "7" / "conversations" / "conv-empty"
    conversation_dir.mkdir(parents=True)
    ctx = SimpleNamespace(
        user_id=7,
        conversation_id="conv-empty",
        conversation_dir=conversation_dir,
        run_id="run-1",
        subagent_run_id=None,
    )

    with pytest.raises(ValueError, match="empty"):
        await media_download.download_media_to_workspace(
            ctx,
            "https://example.com/empty.jpg",
            ext_hint="jpg",
            media_kind="web_search_image",
        )

    assert not (conversation_dir / ".meta" / "assets_manifest.json").exists()


@pytest.mark.asyncio
async def test_download_media_to_workspace_copies_generated_upload_without_http(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path / "workspace"))

    generated = build_generated_upload("source.png")
    generated.path.write_bytes(b"generated-image")

    class FailingAsyncClient:
        async def __aenter__(self):
            raise AssertionError("local generated uploads must not use HTTP")

    monkeypatch.setattr(media_download.httpx, "AsyncClient", FailingAsyncClient)

    conversation_dir = tmp_path / "workspace" / "users" / "7" / "conversations" / "conv-generated"
    conversation_dir.mkdir(parents=True)
    ctx = SimpleNamespace(
        user_id=7,
        conversation_id="conv-generated",
        conversation_dir=conversation_dir,
        run_id="run-1",
        subagent_run_id=None,
    )

    asset_path = await media_download.download_media_to_workspace(
        ctx,
        generated.url,
        ext_hint="png",
        media_kind="image",
        asset_id="generated_image_custom",
    )

    assert asset_path == "references/generated/generated_image_custom/original.png"
    assert (conversation_dir / asset_path).read_bytes() == b"generated-image"
