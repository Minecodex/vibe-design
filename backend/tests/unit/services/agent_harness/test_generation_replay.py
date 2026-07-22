import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.generation import GenerationTask
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.agent_harness.capabilities.tools.analyze_image import AnalyzeImageTool
from app.services.agent_harness.capabilities.tools.generate_image import (
    GenerateImageParams,
    GenerateImageTool,
)
from app.services.agent_harness.capabilities.tools.generate_video import (
    GenerateVideoParams,
    GenerateVideoTool,
)
from app.services.agent_harness.core.context import (
    HarnessContext,
    reset_current_context,
    set_current_context,
)
from app.services.agent_harness.core.utils import generation_store
from app.services.generation_intake_service import GenerationIntakeResult


@pytest_asyncio.fixture(autouse=True)
async def _use_test_generation_db(db_session):
    @asynccontextmanager
    async def _session_factory():
        yield db_session

    app.state.db_session_factory = _session_factory
    yield
    app.state.db_session_factory = AsyncSessionLocal


@pytest.fixture(autouse=True)
def _route_builtin_provider_to_patched_apimart(monkeypatch):
    class DynamicApimartClient:
        def __new__(cls, *args, **kwargs):
            from app.services.apimart_client import ApimartClient

            return ApimartClient(*args, **kwargs)

    monkeypatch.setattr("app.services.builtin_provider.ApimartClient", DynamicApimartClient)


def _capture_enqueued(started: list[str]):
    async def _enqueue_task(*args, **kwargs):
        task_id = kwargs.get("task_id")
        if task_id is None and args:
            task_id = args[0]
        started.append(str(task_id))

    return _enqueue_task


async def _ignore_enqueued(*args, **kwargs):
    return None


def test_generate_image_description_and_schema_are_dynamic_for_selected_model(tmp_path: Path):
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
    )
    token = set_current_context(ctx)
    try:
        tool = GenerateImageTool()
        schema = tool.get_input_schema()
        assert "GPT-Image 2" in tool.description
        assert "1K, 2K, 4K" in tool.description
        assert "4K 不等于 4096x4096 方图" in tool.description
        assert schema["properties"]["resolution"]["enum"] == ["1K", "2K", "4K"]
        assert "21:9" in schema["properties"]["aspect_ratio"]["description"]
        assert "reference_image_urls" in schema["properties"]
        assert "reference_image_url" not in schema["properties"]
        assert "artifact_ref" not in schema["properties"]
        assert "reference_ids" not in schema["properties"]
        assert "tool_reference" not in schema["properties"]
        assert "structured media references" in tool.description
        assert "tool_reference" in tool.description
        assert "artifact_ref" in tool.description
        assert "自动等待" in tool.description
        assert "如果本工具返回 processing" not in tool.description
    finally:
        reset_current_context(token)


def test_generate_video_description_and_schema_are_dynamic_for_selected_model(tmp_path: Path):
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="kling-v3",
        video_provider="builtin",
    )
    token = set_current_context(ctx)
    try:
        tool = GenerateVideoTool()
        schema = tool.get_input_schema()
        schema_text = json.dumps(schema, ensure_ascii=False)
        assert "Kling 3" in tool.description
        assert "720p, 720p_audio, 1080p, 1080p_audio, 4k, 4k_audio" in tool.description
        assert "15s" in tool.description
        assert "output" in schema["properties"]
        assert "input" in schema["properties"]
        assert "model_options" in schema["properties"]
        assert "4k_audio" in schema_text
        assert "first_image_url" in schema_text
        assert "last_image_url" in schema_text
        assert "generate_audio" in schema_text
        assert "multi_shot" in schema_text
        assert "reference_video_urls" not in schema_text
        assert "artifact_ref" not in schema["properties"]
        assert "reference_ids" not in schema["properties"]
        assert "tool_reference" not in schema["properties"]
        assert "structured media references" in tool.description
        assert "tool_reference" in tool.description
        assert "artifact_ref" in tool.description
        assert "自动等待" in tool.description
        assert "如果本工具返回 processing" not in tool.description
    finally:
        reset_current_context(token)


def test_generate_video_schema_exposes_reference_images_for_grok(tmp_path: Path):
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-grok",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="grok-imagine-1.0-video-apimart",
        video_provider="builtin",
    )
    token = set_current_context(ctx)
    try:
        tool = GenerateVideoTool()
        schema = tool.get_input_schema()
        schema_text = json.dumps(schema, ensure_ascii=False)
        assert "Grok-Imagine-video-1.0" in tool.description
        assert "\"references\"" in schema_text
        assert "\"image_urls\"" in schema_text
        assert "\"video_urls\"" not in schema_text
        assert "\"audio_urls\"" not in schema_text
        assert "\"kling\"" not in schema_text
    finally:
        reset_current_context(token)


def test_analyze_image_description_uses_structured_references_without_new_schema_fields():
    tool = AnalyzeImageTool()
    schema = tool.get_input_schema()

    assert "image_url" in schema["properties"]
    assert "reference_ids" not in schema["properties"]
    assert "tool_reference" not in schema["properties"]
    assert "structured media references" in tool.description
    assert "tool_reference" in tool.description


def test_generate_image_keeps_canvas_upload_reference_out_of_base64_params(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "app.core.config.settings.HARNESS_WORKSPACE_ROOT",
        str(tmp_path / "uploads" / "harness"),
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image",
        run_id="run-image",
        workspace_root=tmp_path / "uploads" / "harness",
        runtime_profile="canvas",
        project_id=65,
    )

    from app.services.agent_harness.capabilities.tools.generate_image import (
        _resolve_reference_for_generation_params,
    )

    assert (
        _resolve_reference_for_generation_params("/api/v1/uploads/canvas/65/reference.jpg", ctx)
        == "/api/v1/uploads/canvas/65/reference.jpg"
    )
    assert (
        _resolve_reference_for_generation_params("api/v1/uploads/canvas/65/reference.jpg", ctx)
        == "/api/v1/uploads/canvas/65/reference.jpg"
    )


@pytest.mark.asyncio
async def test_generate_image_submits_task_and_returns_processing_without_polling(monkeypatch, tmp_path: Path, db_session):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    query_calls: list[str] = []
    started: list[str] = []

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_image(self, **_kwargs):
            return {"code": 200, "data": [{"task_id": "remote-image-task"}]}

        async def query_result(self, external_task_id: str):
            query_calls.append(external_task_id)
            return {"code": 200, "data": {"status": "completed"}}

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _capture_enqueued(started),
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gemini-3.1-flash-image-preview-official",
        image_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A woman drinking coffee"),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["status"] == "processing"
    assert result.metadata["result_url"] is None
    assert result.metadata["artifact_ref"].startswith("artifact_ref:")
    assert started == []
    assert query_calls == []
    saved_task = await GenerationTaskRepository(db_session).get_by_id_and_user(
        int(result.metadata["task_id"]),
        ctx.user_id,
    )
    assert saved_task is not None
    assert saved_task.project_id is None
    assert saved_task.workflow_stage == "provider_operation"


@pytest.mark.asyncio
async def test_generate_image_routes_submission_through_generation_intake_service(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []
    appended_events = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=456,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Flux",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    async def direct_generation_should_not_run(*_args, **_kwargs):
        raise AssertionError("generate_image tool must submit through GenerationIntakeService")

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.generation_service.GenerationService.generate_image",
        direct_generation_should_not_run,
    )

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-intake",
        run_id="run-image-intake",
        workspace_root=tmp_path,
        image_model="flux",
        image_provider="builtin",
        runtime_profile="canvas",
        project_id=9,
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_image", tool_call_id="call-image-intake")

    local_reference = ctx.reference_inputs_dir / "source.jpg"
    local_reference.parent.mkdir(parents=True, exist_ok=True)
    local_reference.write_bytes(b"fake-image")

    result = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A quiet editorial product photo",
            reference_image_urls=["references/inputs/source.jpg"],
        ),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["task_id"] == "456"
    assert len(submitted_requests) == 1
    request = submitted_requests[0]
    assert request.client_request_id == "harness:image:conv-image-intake:call-image-intake"
    assert request.image_urls == ["references/inputs/source.jpg"]
    assert request.metadata_params["reference_image_urls"] == ["references/inputs/source.jpg"]
    assert "base64" not in json.dumps(request.image_urls)
    assert request.planned_result_url
    assert request.metadata_params["tool_call_id"] == "call-image-intake"
    assert request.reserve_billing is False
    assert appended_events[0]["event_type"] == "item_started"
    assert appended_events[0]["idempotency_key"] == f"run:run-image-intake:generation:{result.metadata['artifact_ref']}:started"
    assert appended_events[0]["payload"]["item_type"] == "generation_task"
    assert appended_events[0]["payload"]["item_id"] == result.metadata["artifact_ref"]
    assert appended_events[0]["payload"]["payload"]["task_id"] == "456"
    assert appended_events[0]["payload"]["payload"]["artifact_ref"] == result.metadata["artifact_ref"]
    assert appended_events[0]["payload"]["payload"]["canvas_item"]["task_id"] == "456"


@pytest.mark.asyncio
async def test_generate_image_reuses_same_artifact_task_without_ecommerce_confirmation(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []
    appended_events = []

    class FakeGenerationIntakeService:
        _task_by_request_id = {}

        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            if request.client_request_id in self._task_by_request_id:
                return GenerationIntakeResult(
                    task=self._task_by_request_id[request.client_request_id],
                    reused_existing=True,
                    amount_cents=0,
                )
            task = GenerationTask(
                id=901,
                user_id=request.user_id,
                project_id=request.project_id,
                task_type="text2image",
                provider_code=request.provider_code,
                model_name=request.model_name,
                model_label="GPT-Image 2",
                prompt=request.prompt,
                params={
                    "planned_result_url": request.planned_result_url,
                    "artifact_ref": request.metadata_params["artifact_ref"],
                    "canvas_item": {"task_id": "901"},
                },
                status="processing",
                client_request_id=request.client_request_id,
            )
            self._task_by_request_id[request.client_request_id] = task
            return GenerationIntakeResult(
                task=task,
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-generic-image",
        run_id="run-generic-image",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
        runtime_profile="canvas",
        project_id=9,
        skill_id="menswear-ecommerce-hero",
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_image", tool_call_id="call-generic-image")
    local_reference = ctx.reference_inputs_dir / "source.jpg"
    local_reference.parent.mkdir(parents=True, exist_ok=True)
    local_reference.write_bytes(b"fake-image")

    params = GenerateImageParams(
        prompt="生成正面白底商品图。",
        reference_image_urls=["references/inputs/source.jpg"],
    )

    first = await GenerateImageTool().execute(params, ctx)

    second = await GenerateImageTool().execute(params, ctx)

    assert first.is_error is False
    assert second.is_error is False
    assert len(submitted_requests) == 2
    assert submitted_requests[0].client_request_id == "harness:image:conv-generic-image:call-generic-image"
    assert submitted_requests[0].client_request_id == submitted_requests[1].client_request_id
    assert first.metadata["task_id"] == "901"
    assert second.metadata["task_id"] == "901"
    assert submitted_requests[1].metadata_params["tool_call_id"] == "call-generic-image"
    assert second.metadata["tool_call_id"] == "call-generic-image"
    assert len([event for event in appended_events if event["event_type"] == "item_started"]) == 2


@pytest.mark.asyncio
async def test_generate_image_routes_ollama_submission_through_generation_intake_service(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.OLLAMA_API_KEY", "test-ollama-key")
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=789,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Ollama Image (gpt-image-2)",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
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
        conversation_id="conv-image-ollama-intake",
        run_id="run-image-ollama-intake",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="ollama",
        runtime_profile="canvas",
        project_id=9,
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_image", tool_call_id="call-image-ollama-intake")

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A quiet editorial product photo"),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["task_id"] == "789"
    assert len(submitted_requests) == 1
    request = submitted_requests[0]
    assert request.provider_code == "ollama"
    assert request.model_name == "gpt-image-2"
    assert request.client_request_id == "harness:image:conv-image-ollama-intake:call-image-ollama-intake"
    assert request.reserve_billing is False


@pytest.mark.asyncio
async def test_generate_image_forwards_canvas_upload_tool_reference_to_intake(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path / "uploads" / "harness"))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=4,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Seedream 5.0 Lite",
                    prompt=request.prompt,
                    params={
                        "image_urls": request.image_urls,
                        "reference_image_urls": request.metadata_params.get("reference_image_urls"),
                        "reference_diagnostics": request.metadata_params.get("reference_diagnostics"),
                    },
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
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
        conversation_id="1779366716889_544727",
        run_id="run-image-intake",
        workspace_root=tmp_path / "uploads" / "harness",
        image_model="doubao-seedream-5-0-260128",
        image_provider="builtin",
        runtime_profile="canvas",
        project_id=1,
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_image", tool_call_id="functions.generate_image:0")

    reference_url = "/api/v1/uploads/canvas/1/2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"
    reference_file = tmp_path / "uploads" / "canvas" / "1" / "2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"
    reference_file.parent.mkdir(parents=True)
    reference_file.write_bytes(b"fake-image")
    result = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A cute monkey sitting and eating grapes",
            reference_image_urls=[reference_url],
        ),
        ctx,
    )

    assert result.is_error is False
    assert len(submitted_requests) == 1
    request = submitted_requests[0]
    assert request.image_urls == [reference_url]
    assert request.metadata_params["reference_image_urls"] == [reference_url]
    assert request.metadata_params["reference_diagnostics"]["tool_reference_images"]["count"] == 1
    assert request.metadata_params["reference_diagnostics"]["tool_reference_images"]["kinds"] == {"local_upload": 1}
    assert result.metadata["reference_diagnostics"]["tool_reference_images"]["count"] == 1
    assert request.client_request_id == "harness:image:1779366716889_544727:functions.generate_image:0"


@pytest.mark.asyncio
async def test_generate_image_records_warning_when_message_references_are_unused(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=789,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Flux",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.load_recent_messages",
        lambda *_args, **_kwargs: [
            {
                "role": "user",
                "metadata": {
                    "references": [
                        {
                            "id": "canvas:img-1",
                            "kind": "canvas_item",
                            "media_type": "image",
                            "tool_reference": "/api/v1/uploads/canvas/88/source.png",
                        }
                    ]
                },
            }
        ],
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-unused-ref",
        run_id="run-image-unused-ref",
        workspace_root=tmp_path,
        image_model="flux",
        image_provider="builtin",
        runtime_profile="canvas",
        project_id=88,
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A clean product variant"),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.image_urls is None
    assert request.metadata_params["reference_diagnostics"] == {
        "available_reference_count": 1,
        "available_reference_ids": ["canvas:img-1"],
        "used_reference_image_count": 0,
        "tool_reference_images": {
            "count": 0,
            "kinds": {},
            "transports": {},
            "mime_types": [],
            "items": [],
        },
        "warning": "message_has_image_references_but_tool_has_no_image_inputs",
    }


@pytest.mark.asyncio
async def test_generate_image_returns_split_retry_metadata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_image(self, **_kwargs):
            return {"code": 200, "data": [{"task_id": "remote-image-task"}]}

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-retry-metadata",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gemini-3.1-flash-image-preview-official",
        image_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A monkey eating a peach"),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["artifact_ref"].startswith("artifact_ref:")
    assert result.metadata["auto_retry_count"] == 0
    assert result.metadata["auto_retry_max"] == 3
    assert result.metadata["manual_retry_count"] == 0
    assert "retry_count" not in result.metadata
    assert "max_retry" not in result.metadata


@pytest.mark.asyncio
async def test_generate_image_persists_tool_call_id_on_generation_task(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_image(self, **_kwargs):
            return {"code": 200, "data": [{"task_id": "remote-image-task"}]}

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-tool-call",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gemini-3.1-flash-image-preview-official",
        image_provider="builtin",
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_image", tool_call_id="call-generate-image-1")

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A woman drinking coffee"),
        ctx,
    )

    saved_task = await generation_store.read_generation_task(ctx, result.metadata["task_id"])

    assert result.is_error is False
    assert saved_task["task_id"] == result.metadata["task_id"]
    assert saved_task["tool_call_id"] == "call-generate-image-1"


@pytest.mark.asyncio
async def test_generate_image_accepts_supported_gpt_image_2_4k_square_ratio(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    submitted_requests = []
    query_calls: list[str] = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=690,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="GPT Image 2",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(prompt="A woman drinking coffee", resolution="4K", aspect_ratio="1:1"),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["status"] == "processing"
    assert query_calls == []
    request = submitted_requests[0]
    assert request.resolution == "4K"
    assert request.aspect_ratio == "1:1"


@pytest.mark.asyncio
async def test_generate_image_forwards_multiple_reference_images(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_image(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=737,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type="text2image",
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="GPT Image 2",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_image.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-image-multi-ref",
        run_id="run-image",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A cinematic poster",
            reference_image_urls=[
                "https://example.com/ref-1.png",
                "https://example.com/ref-2.png",
            ],
        ),
        ctx,
    )

    assert result.is_error is False
    assert submitted_requests[0].image_urls == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]


@pytest.mark.asyncio
async def test_generate_video_submits_task_and_returns_processing_without_polling(monkeypatch, tmp_path: Path, db_session):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    query_calls: list[str] = []
    started: list[str] = []

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_video(self, **_kwargs):
            return {"code": 200, "data": [{"task_id": "remote-video-task"}]}

        async def query_result(self, external_task_id: str):
            query_calls.append(external_task_id)
            return {"code": 200, "data": {"status": "completed"}}

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _capture_enqueued(started),
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="doubao-seedance-1-5-pro",
        video_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="A woman drinking coffee",
            duration=5,
            output={"resolution": "480p"},
        ),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["status"] == "processing"
    assert result.metadata["result_url"] is None
    assert result.metadata["artifact_ref"].startswith("artifact_ref:")
    assert started == []
    assert query_calls == []
    saved_task = await GenerationTaskRepository(db_session).get_by_id_and_user(
        int(result.metadata["task_id"]),
        ctx.user_id,
    )
    assert saved_task is not None
    assert saved_task.workflow_stage == "provider_operation"


@pytest.mark.asyncio
async def test_generate_video_routes_submission_through_generation_intake_service(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=654,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type=request.task_type,
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Seedance",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    async def direct_generation_should_not_run(*_args, **_kwargs):
        raise AssertionError("generate_video tool must submit through GenerationIntakeService")

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.generation_service.GenerationService.generate_video",
        direct_generation_should_not_run,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-intake",
        run_id="run-video-intake",
        workspace_root=tmp_path,
        video_model="doubao-seedance-1-5-pro",
        video_provider="builtin",
        runtime_profile="canvas",
        project_id=10,
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="generate_video", tool_call_id="call-video-intake")

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="A quiet editorial product film",
            duration=5,
            output={"resolution": "480p"},
        ),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["task_id"] == "654"
    assert len(submitted_requests) == 1
    request = submitted_requests[0]
    assert request.task_type == "text2video"
    assert request.client_request_id == "harness:video:conv-video-intake:call-video-intake"
    assert request.planned_result_url
    assert request.metadata_params["tool_call_id"] == "call-video-intake"
    assert request.reserve_billing is False


@pytest.mark.asyncio
async def test_generate_video_records_unused_message_reference_diagnostics(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=655,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type=request.task_type,
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Seedance",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.load_recent_messages",
        lambda *_args, **_kwargs: [
            {
                "role": "user",
                "metadata": {
                    "references": [
                        {
                            "id": "canvas:img-1",
                            "kind": "canvas_item",
                            "media_type": "image",
                            "tool_reference": "/api/v1/uploads/canvas/88/source.png",
                        }
                    ]
                },
            }
        ],
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-unused-ref",
        run_id="run-video-unused-ref",
        workspace_root=tmp_path,
        video_model="doubao-seedance-1-5-pro",
        video_provider="builtin",
        runtime_profile="canvas",
        project_id=88,
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="Animate this into an editorial product film",
            duration=5,
            output={"resolution": "480p"},
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.image_urls is None
    assert request.first_frame_image is None
    assert request.tail_frame_image is None
    assert request.metadata_params["reference_diagnostics"] == {
        "available_reference_count": 1,
        "available_reference_ids": ["canvas:img-1"],
        "used_reference_image_count": 0,
        "warning": "message_has_image_references_but_tool_has_no_image_inputs",
    }


@pytest.mark.asyncio
async def test_generate_video_forwards_extended_kling_parameters(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=1024,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type=request.task_type,
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Kling",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-extended",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="kling-v3",
        video_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="cinematic shots",
            duration=15,
            output={"generate_audio": True},
            input={
                "mode": "frames",
                "frames": {
                    "first_image_url": "https://example.com/first.png",
                    "last_image_url": "https://example.com/last.png",
                },
            },
            model_options={
                "kling": {"mode": "4k"},
                "kling_v3": {
                    "multi_shot": True,
                    "shot_type": "customize",
                    "multi_prompt": [
                        {"index": 1, "prompt": "Shot one", "duration": 8},
                        {"index": 2, "prompt": "Shot two", "duration": 7},
                    ],
                    "element_list": [
                        {
                            "name": "hero",
                            "description": "main character",
                            "element_input_urls": ["https://example.com/a.png", "https://example.com/b.png"],
                        }
                    ],
                },
            },
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.resolution == "4k_audio"
    assert request.first_frame_image == "https://example.com/first.png"
    assert request.tail_frame_image == "https://example.com/last.png"
    assert request.audio is True
    assert request.multi_shot is True
    assert request.shot_type == "customize"
    assert request.multi_prompt == [
        {"index": 1, "prompt": "Shot one", "duration": 8},
        {"index": 2, "prompt": "Shot two", "duration": 7},
    ]
    assert request.element_list == [
        {
            "name": "hero",
            "description": "main character",
            "element_input_urls": ["https://example.com/a.png", "https://example.com/b.png"],
        },
    ]


@pytest.mark.asyncio
async def test_generate_video_rejects_video_audio_refs_and_forwards_image_refs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=1117,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type=request.task_type,
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Seedance",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-seedance-2",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="doubao-seedance-2.0",
        video_provider="builtin",
    )
    ctx.ensure_dirs()

    unsupported = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="第一人称茶饮广告，人物边走边介绍产品",
            duration=5,
            output={"resolution": "720p", "generate_audio": True},
            input={
                "mode": "references",
                "references": {
                    "image_urls": [
                        "https://example.com/ref-1.png",
                        "https://example.com/ref-2.png",
                    ],
                    "video_urls": ["https://example.com/ref.mp4"],
                    "audio_urls": ["https://example.com/ref.wav"],
                },
            },
            model_options={"seedance_2": {"return_last_frame": True}},
        ),
        ctx,
    )

    assert unsupported.is_error is True

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="第一人称茶饮广告，人物边走边介绍产品",
            duration=5,
            output={"resolution": "720p", "generate_audio": True},
            input={
                "mode": "references",
                "references": {
                    "image_urls": [
                        "https://example.com/ref-1.png",
                        "https://example.com/ref-2.png",
                    ],
                },
            },
            model_options={"seedance_2": {"return_last_frame": True}},
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.image_urls == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]
    assert request.return_last_frame is True
    assert request.audio is True


@pytest.mark.asyncio
async def test_generate_video_forwards_grok_reference_images(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    submitted_requests = []

    class FakeGenerationIntakeService:
        def __init__(self, _db):
            pass

        async def submit_video(self, request):
            submitted_requests.append(request)
            return GenerationIntakeResult(
                task=GenerationTask(
                    id=1175,
                    user_id=request.user_id,
                    project_id=request.project_id,
                    task_type=request.task_type,
                    provider_code=request.provider_code,
                    model_name=request.model_name,
                    model_label="Grok",
                    prompt=request.prompt,
                    params={"planned_result_url": request.planned_result_url},
                    status="processing",
                    client_request_id=request.client_request_id,
                ),
                reused_existing=False,
                amount_cents=0,
            )

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.generate_video.GenerationIntakeService",
        FakeGenerationIntakeService,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-grok-ref",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="grok-imagine-1.0-video-apimart",
        video_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="让这张图自然动起来，保留原始构图",
            duration=10,
            output={"resolution": "720p"},
            input={
                "mode": "references",
                "references": {
                    "image_urls": [
                        "https://example.com/ref-1.png",
                        "https://example.com/ref-2.png",
                    ],
                },
            },
        ),
        ctx,
    )

    assert result.is_error is False
    request = submitted_requests[0]
    assert request.image_urls == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]
    assert request.resolution == "720p"


@pytest.mark.asyncio
async def test_generate_video_returns_split_retry_metadata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_video(self, **_kwargs):
            return {"code": 200, "data": [{"task_id": "remote-video-task"}]}

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        _ignore_enqueued,
    )

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-video-retry-metadata",
        run_id="run-video",
        workspace_root=tmp_path,
        video_model="doubao-seedance-1-5-pro",
        video_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await GenerateVideoTool().execute(
        GenerateVideoParams(
            prompt="A monkey eating a peach",
            duration=5,
            output={"resolution": "480p"},
        ),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["artifact_ref"].startswith("artifact_ref:")
    assert result.metadata["auto_retry_count"] == 0
    assert result.metadata["auto_retry_max"] == 3
    assert result.metadata["manual_retry_count"] == 0
    assert "retry_count" not in result.metadata
    assert "max_retry" not in result.metadata
