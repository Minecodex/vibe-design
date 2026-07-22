from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.generation import GenerationTask
from app.services.agent_harness.capabilities.tools.generate_image import (
    GenerateImageParams,
    GenerateImageTool,
)
from app.services.agent_harness.capabilities.tools.generate_video import (
    GenerateVideoParams,
    GenerateVideoTool,
)
from app.services.agent_harness.core.context import HarnessContext
from app.services.generation_intake_service import GenerationIntakeResult


@pytest_asyncio.fixture(autouse=True)
async def _use_test_generation_db(db_session):
    @asynccontextmanager
    async def _session_factory():
        yield db_session

    app.state.db_session_factory = _session_factory
    yield
    app.state.db_session_factory = AsyncSessionLocal


async def _ignore_enqueued(*args, **kwargs):
    return None


def _processing_task(request, *, task_id: int, task_type: str) -> GenerationTask:
    return GenerationTask(
        id=task_id,
        user_id=request.user_id,
        project_id=request.project_id,
        task_type=task_type,
        provider_code=request.provider_code,
        model_name=request.model_name,
        model_label=request.model_name,
        prompt=request.prompt,
        params={"planned_result_url": request.planned_result_url},
        status="processing",
        client_request_id=request.client_request_id,
    )


@pytest.mark.asyncio
async def test_generate_image_uses_selected_model_media_preferences(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=_processing_task(request, task_id=3201, task_type="text2image"),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-preferences",
        run_id="run-image-preferences",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
        model_preferences={
            "media_generation_settings": {
                "image": {
                    "builtin:gpt-image-2": {
                        "resolution": "2K",
                        "aspect_ratio": "16:9",
                    }
                }
            }
        },
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A product key visual",
            resolution="4K",
            aspect_ratio="1:1",
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.resolution == "2K"
    assert request.aspect_ratio == "16:9"
    assert result.metadata["resolution"] == "2K"
    assert result.metadata["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_generate_image_keeps_tool_parameters_without_media_preferences(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=_processing_task(request, task_id=3202, task_type="text2image"),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-auto-preferences",
        run_id="run-image-preferences",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
        model_preferences={
            "media_generation_settings": {
                "image": {
                    "builtin:other-model": {
                        "resolution": "2K",
                        "aspect_ratio": "16:9",
                    }
                }
            }
        },
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A square product key visual",
            resolution="4K",
            aspect_ratio="1:1",
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.resolution == "4K"
    assert request.aspect_ratio == "1:1"


@pytest.mark.asyncio
async def test_generate_video_uses_selected_model_media_preferences(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=_processing_task(request, task_id=3301, task_type=request.task_type),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-preferences",
        run_id="run-video-preferences",
        workspace_root=tmp_path,
        video_model="kling-v3",
        video_provider="builtin",
        model_preferences={
            "media_generation_settings": {
                "video": {
                    "builtin:kling-v3": {
                        "resolution": "1080p",
                        "aspect_ratio": "9:16",
                        "duration": 12,
                    }
                }
            }
        },
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="A vertical product film",
            aspect_ratio="16:9",
            duration=5,
            output={"resolution": "720p", "generate_audio": True},
            model_options={"kling": {"mode": "4k"}},
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.resolution == "1080p"
    assert request.quality == "1080p"
    assert request.aspect_ratio == "9:16"
    assert request.duration == 12
    assert request.audio is False
    assert request.metadata_params["output"] == {"resolution": "1080p"}
    assert request.metadata_params["model_options"] is None
    assert result.metadata["resolution"] == "1080p"
    assert result.metadata["aspect_ratio"] == "9:16"
    assert result.metadata["duration"] == 12


@pytest.mark.asyncio
async def test_generate_video_keeps_tool_parameters_without_media_preferences(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=_processing_task(request, task_id=3302, task_type=request.task_type),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-auto-preferences",
        run_id="run-video-preferences",
        workspace_root=tmp_path,
        video_model="kling-v3",
        video_provider="builtin",
        model_preferences={
            "media_generation_settings": {
                "video": {
                    "builtin:other-model": {
                        "resolution": "1080p",
                        "aspect_ratio": "9:16",
                        "duration": 12,
                    }
                }
            }
        },
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="A horizontal product film",
            aspect_ratio="16:9",
            duration=5,
            output={"resolution": "720p", "generate_audio": True},
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.resolution == "720p_audio"
    assert request.quality == "720p_audio"
    assert request.aspect_ratio == "16:9"
    assert request.duration == 5
    assert request.audio is True
