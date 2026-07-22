import logging
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.billing import UsageLog
from app.models.generation import GenerationTask
from app.models.user import User
from app.schemas.billing import UsageLogListRead
from app.schemas.generation import GenerationTaskRead
from app.services import builtin_credentials as builtin_credentials_module
from app.services import generation_service as generation_service_module
from app.services.apimart_client import ApimartClient
from app.services.billing_service import BillingService
from app.services.builtin_provider import BuiltinQueryResult, BuiltinSubmitResult
from app.services.builtin_provider import get_builtin_provider
from app.services.generation_media_resolver import GenerationMediaResolveError
from app.services.generation_service import GenerationService


def _configure_fake_tos(monkeypatch):
    uploads: list[tuple[str, str, str]] = []

    class FakeTosClient:
        def __init__(self, ak, sk, endpoint, region):
            assert ak == "test-ak"
            assert sk == "test-sk"
            assert endpoint == "tos-cn-guangzhou.volces.com"
            assert region == "cn-guangzhou"

        def put_object_from_file(self, bucket_name, object_key, file_path):
            uploads.append((bucket_name, object_key, file_path))

    monkeypatch.setattr(settings, "TOS_AK", "test-ak")
    monkeypatch.setattr(settings, "TOS_SK", "test-sk")
    monkeypatch.setattr(settings, "TOS_ENDPOINT", "tos-cn-guangzhou.volces.com")
    monkeypatch.setattr(settings, "TOS_REGION", "cn-guangzhou")
    monkeypatch.setattr(settings, "TOS_BUCKET_NAME", "design-public")
    monkeypatch.setattr(settings, "TOS_PUBLIC_BASE_URL", "")
    monkeypatch.setattr(settings, "TOS_OBJECT_PREFIX", "generation-refs/")
    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=FakeTosClient))
    monkeypatch.setattr("app.services.generation_media_resolver._file_content_digest", lambda _path: "fixedobjectkey")
    return uploads


@pytest.mark.asyncio
async def test_download_file_to_local_retries_with_exponential_backoff_before_success(monkeypatch, tmp_path):
    attempts = 0
    sleeps: list[float] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self, _chunk_size):
            yield b"image-bytes"

    class FakeStream:
        async def __aenter__(self):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise httpx.ConnectError("temporary failure")
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, file_url, timeout):
            assert method == "GET"
            return FakeStream()

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    local_url = await GenerationService._download_file_to_local("https://example.com/image.png", "png")

    assert attempts == 3
    assert sleeps == [1, 2]
    assert local_url.startswith("/api/v1/uploads/generated/")
    saved_file = tmp_path / local_url.removeprefix("/api/v1/")
    assert saved_file.read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_download_file_to_local_raises_after_three_attempts(monkeypatch, tmp_path):
    attempts = 0
    sleeps: list[float] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, file_url, timeout):
            assert method == "GET"

            class FakeStream:
                async def __aenter__(self):
                    nonlocal attempts
                    attempts += 1
                    raise httpx.ReadTimeout("still failing")

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            return FakeStream()

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(httpx.ReadTimeout):
        await GenerationService._download_file_to_local("https://example.com/image.png", "png")

    assert attempts == 3
    assert sleeps == [1, 2]


@pytest.mark.asyncio
async def test_retry_image_submission_retries_three_times_with_exponential_backoff(monkeypatch):
    service = GenerationService(db=None)
    attempts = 0
    sleeps: list[float] = []

    async def flaky_submit():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary provider outage")
        return {"task_id": "task-123"}

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    result = await service._retry_image_submission(
        flaky_submit,
        provider_code="builtin",
        model_name="gemini-3.1-flash-image-preview-official",
    )

    assert result == {"task_id": "task-123"}
    assert attempts == 3
    assert sleeps == [1, 2]


@pytest.mark.asyncio
async def test_retry_image_submission_does_not_retry_non_retryable_http_exception(monkeypatch):
    service = GenerationService(db=None)
    attempts = 0
    sleeps: list[float] = []

    async def invalid_submit():
        nonlocal attempts
        attempts += 1
        raise HTTPException(status_code=400, detail="bad request")

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(HTTPException) as exc_info:
        await service._retry_image_submission(
            invalid_submit,
            provider_code="builtin",
            model_name="gemini-3.1-flash-image-preview-official",
        )

    assert exc_info.value.status_code == 400
    assert attempts == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_retry_image_submission_does_not_retry_generation_media_resolve_error(monkeypatch):
    service = GenerationService(db=None)
    attempts = 0
    sleeps: list[float] = []

    async def invalid_submit():
        nonlocal attempts
        attempts += 1
        raise GenerationMediaResolveError("generation_object_storage_not_configured")

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(GenerationMediaResolveError) as exc_info:
        await service._retry_image_submission(
            invalid_submit,
            provider_code="builtin",
            model_name="gemini-3.1-flash-image-preview-official",
        )

    assert exc_info.value.code == "generation_object_storage_not_configured"
    assert attempts == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_builtin_credentials_refreshes_license_runtime_when_worker_memory_key_is_missing(monkeypatch):
    calls = []
    service = GenerationService(db=object())
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_API_KEY", "")

    class FakeLicenseRuntime:
        async def force_refresh(self, db):
            calls.append(db)
            settings.BUILTIN_PROVIDER_API_KEY = "sk-refreshed"

    monkeypatch.setattr(builtin_credentials_module, "license_runtime_state", FakeLicenseRuntime())

    credentials = await service._get_credentials(user_id=1, provider_code="builtin")

    assert credentials.access_key == "sk-refreshed"
    assert calls == [service.db]


def test_download_failure_error_does_not_include_provider_signed_url():
    signed_url = "https://provider.example/generated.png?X-Amz-Signature=secret-token"

    message = GenerationService._build_download_failure_error(
        signed_url,
        RuntimeError("download failed"),
    )

    assert "result_url_download_failed" in message
    assert "provider.example" not in message
    assert "secret-token" not in message
    assert signed_url not in message


@pytest.mark.asyncio
async def test_apimart_query_interface_error_keeps_task_processing(monkeypatch):
    async def fake_query_result(self, external_task_id):
        return {
            "error": {"message": "connect failed"},
            "_status_code": 502,
        }

    monkeypatch.setattr(ApimartClient, "query_result", fake_query_result)
    provider = get_builtin_provider("apimart", "test-key")

    result = await provider.query_generation("task-1", task_type="text2image", model_name="gpt-image-2")

    assert result.status == "processing"
    assert result.error_message is None


@pytest.mark.asyncio
async def test_apimart_query_remote_failed_status_marks_task_failed(monkeypatch):
    async def fake_query_result(self, external_task_id):
        return {
            "code": 200,
            "data": {
                "status": "failed",
                "error": {"message": "provider generation failed"},
            },
        }

    monkeypatch.setattr(ApimartClient, "query_result", fake_query_result)
    provider = get_builtin_provider("apimart", "test-key")

    result = await provider.query_generation("task-1", task_type="text2video", model_name="kling-v3")

    assert result.status == "failed"
    assert result.error_message == "provider generation failed"


@pytest.mark.asyncio
async def test_query_builtin_uses_first_url_when_provider_returns_comma_joined_result_urls(monkeypatch):
    service = GenerationService(db=None)

    async def fake_query_result(self, external_task_id):
        return {
            "code": 200,
            "data": {
                "status": "completed",
                "result": {
                    "result_urls": [
                        "https://upload.apimart.ai/f/image/9998224076794054-9b85c95e-1e72-4eb8-abc1-6b46265ade51-1775923205945359808_9.png,https://upload.apimart.ai/f/image/9998224076792463-ac69e226-0596-4b19-8901-eae3c089e1d5-1775923207505892359_12.png"
                    ]
                },
            },
        }

    downloaded_urls: list[str] = []

    async def fake_download(url, ext):
        downloaded_urls.append(url)
        return "/api/v1/uploads/generated/first.png"

    monkeypatch.setattr(ApimartClient, "query_result", fake_query_result)
    monkeypatch.setattr(service, "_download_file_to_local", fake_download)

    task = SimpleNamespace(
        external_task_id="task-joined-urls",
        task_type="text2image",
        params={},
    )
    cred = SimpleNamespace(access_key="test-key")

    result = await service._query_builtin(task, cred)

    assert downloaded_urls == [
        "https://upload.apimart.ai/f/image/9998224076794054-9b85c95e-1e72-4eb8-abc1-6b46265ade51-1775923205945359808_9.png"
    ]
    assert result["result_url"] == "/api/v1/uploads/generated/first.png"
    assert result["result_urls"] == ["/api/v1/uploads/generated/first.png"]


@pytest.mark.asyncio
async def test_query_builtin_marks_task_failed_when_download_retries_are_exhausted(monkeypatch):
    service = GenerationService(db=None)

    async def fake_query_result(self, external_task_id):
        return {
            "code": 200,
            "data": {
                "status": "completed",
                "result": {
                    "result_urls": ["https://example.com/provider-result.png"]
                },
            },
        }

    async def fake_download(url, ext):
        raise httpx.ReadTimeout("download timed out")

    monkeypatch.setattr(ApimartClient, "query_result", fake_query_result)
    monkeypatch.setattr(service, "_download_file_to_local", fake_download)

    task = SimpleNamespace(
        external_task_id="task-download-failed",
        task_type="text2image",
        params={},
    )
    cred = SimpleNamespace(access_key="test-key")

    result = await service._query_builtin(task, cred)

    assert result["status"] == "failed"
    assert result.get("result_url") is None
    assert "result_url_download_failed" in result["error_message"]
    assert "ReadTimeout" in result["error_message"]
    assert "https://example.com/provider-result.png" not in result["error_message"]
    assert "download timed out" not in result["error_message"]


@pytest.mark.asyncio
async def test_generate_image_for_builtin_returns_processing_and_enqueues_provider_operation(monkeypatch):
    service = GenerationService(db=None)

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            raise AssertionError("LingyaAI image submission should run in the background")

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 303
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    enqueued: list[dict[str, object]] = []

    class FakeProviderOperationService:
        def __init__(self, db):
            assert db is None

        async def enqueue_generation_submit(self, task, *, task_kind, provider_code, priority):
            enqueued.append(
                {
                    "task_id": task.id,
                    "task_kind": task_kind,
                    "provider_code": provider_code,
                    "priority": priority,
                }
            )
            return SimpleNamespace(id=1)

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(generation_service_module, "get_active_builtin_provider", lambda api_key: FakeBuiltinProvider())
    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="Gemini-3.1-flash-image-preview",
        provider_code="builtin",
    )

    assert task.status == "processing"
    assert task.external_task_id is None
    assert getattr(task, "result_url", None) is None
    assert getattr(task, "result_urls", None) is None
    assert task.builtin_provider_code == "lingyaai"
    assert task.workflow_stage == "provider_operation"
    assert task.scheduler_next_run_at is None
    assert getattr(task, "provider_request_id", None) is None
    assert getattr(task, "provider_trace_id", None) is None
    assert task.params["provider_submit"]["provider_code"] == "lingyaai"
    assert "raw" not in task.params["provider_submit"]
    assert enqueued == [
        {
            "task_id": 303,
            "task_kind": "image",
            "provider_code": "lingyaai",
            "priority": "foreground",
        }
    ]


@pytest.mark.asyncio
async def test_builtin_submit_operation_stores_external_id_and_enqueues_query(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=401,
        user_id=9,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="seedream-5.0-lite",
        prompt="blue banana",
        status="processing",
        external_task_id=None,
        params={"resolution": "1K", "aspect_ratio": "1:1", "provider_submit": {}},
    )
    operation = SimpleNamespace(id=11, payload={})
    repo_events: list[tuple[str, dict]] = []
    enqueued_queries: list[tuple[int, str]] = []

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            assert kwargs["prompt"] == "blue banana"
            return BuiltinSubmitResult(
                status="processing",
                external_task_id="upstream-1",
                oneapi_request_id="req-1",
                request_id="trace-1",
                raw={"id": "upstream-1"},
            )

    class FakeProviderOperationRepository:
        def __init__(self, db):
            assert db is None

        async def mark_succeeded(self, op, *, result_payload=None):
            assert op is operation
            repo_events.append(("succeeded", result_payload or {}))
            return op

        async def mark_failed(self, *_args, **_kwargs):
            raise AssertionError("processing submit must not fail operation")

    class FakeProviderOperationService:
        def __init__(self, db):
            assert db is None

        async def enqueue_generation_query(self, queued_task, *, provider_code):
            enqueued_queries.append((queued_task.id, provider_code))
            return SimpleNamespace(id=12)

        async def enqueue_result_download(self, *_args, **_kwargs):
            raise AssertionError("processing submit must enqueue query, not download")

    async def fake_get_credentials(user_id, provider_code):
        assert (user_id, provider_code) == (9, "builtin")
        return SimpleNamespace(access_key="test-key")

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())
    monkeypatch.setattr(generation_service_module, "ProviderOperationRepository", FakeProviderOperationRepository)
    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)

    result = await service.complete_builtin_image_submit_operation(task, operation)

    assert result is task
    assert task.status == "processing"
    assert task.external_task_id == "upstream-1"
    assert task.workflow_stage == "provider_operation"
    assert task.provider_request_id == "req-1"
    assert task.provider_trace_id == "trace-1"
    assert task.params["provider_submit"]["raw"] == {"id": "upstream-1"}
    assert repo_events == [("succeeded", {"external_task_id": "upstream-1", "status": "processing"})]
    assert enqueued_queries == [(401, "lingyaai")]


@pytest.mark.asyncio
async def test_completed_builtin_submit_operation_enqueues_result_download_without_fake_external_id(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=402,
        user_id=9,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="seedream-5.0-lite",
        prompt="blue banana",
        status="processing",
        external_task_id=None,
        params={"resolution": "1K", "aspect_ratio": "1:1", "provider_submit": {}},
    )
    operation = SimpleNamespace(id=21, payload={})
    repo_events: list[tuple[str, dict]] = []
    enqueued_downloads: list[tuple[int, str, list[str]]] = []

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **_kwargs):
            return BuiltinSubmitResult(
                status="completed",
                result_urls=["https://example.test/result.png"],
                oneapi_request_id="req-2",
                request_id="trace-2",
                raw={"id": "sync-image"},
            )

    class FakeProviderOperationRepository:
        def __init__(self, db):
            pass

        async def mark_succeeded(self, op, *, result_payload=None):
            assert op is operation
            repo_events.append(("succeeded", result_payload or {}))
            return op

        async def mark_failed(self, *_args, **_kwargs):
            raise AssertionError("completed submit must not fail operation")

    class FakeProviderOperationService:
        def __init__(self, db):
            pass

        async def enqueue_generation_query(self, *_args, **_kwargs):
            raise AssertionError("completed submit should skip query")

        async def enqueue_result_download(self, queued_task, *, provider_code, result_urls):
            enqueued_downloads.append((queued_task.id, provider_code, list(result_urls)))
            return SimpleNamespace(id=22)

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key")

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())
    monkeypatch.setattr(generation_service_module, "ProviderOperationRepository", FakeProviderOperationRepository)
    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)

    await service.complete_builtin_image_submit_operation(task, operation)

    assert task.status == "processing"
    assert task.external_task_id is None
    assert task.workflow_stage == "provider_operation"
    assert repo_events == [("succeeded", {"external_task_id": None, "status": "completed"})]
    assert enqueued_downloads == [(402, "lingyaai", ["https://example.test/result.png"])]


@pytest.mark.asyncio
async def test_query_builtin_task_for_operation_enqueues_download_without_completing_task(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=403,
        user_id=9,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="seedream-5.0-lite",
        status="processing",
        external_task_id="upstream-3",
        params={"provider_submit": {"provider_code": "lingyaai"}},
    )
    enqueued_downloads: list[tuple[int, str, list[str]]] = []

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def query_generation(self, external_task_id, *, task_type, model_name):
            assert external_task_id == "upstream-3"
            return BuiltinQueryResult(
                status="completed",
                result_urls=["https://example.test/query-result.png"],
            )

    class FakeProviderOperationService:
        def __init__(self, db):
            pass

        async def enqueue_result_download(self, queued_task, *, provider_code, result_urls):
            enqueued_downloads.append((queued_task.id, provider_code, list(result_urls)))
            return SimpleNamespace(id=31)

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key")

    async def update_should_not_run(*_args, **_kwargs):
        raise AssertionError("completed query should not terminalize before result download")

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "update", update_should_not_run)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())
    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)

    result = await service.query_builtin_task_for_operation(task)

    assert result == {
        "status": "completed",
        "pending_result_download": True,
        "result_urls": ["https://example.test/query-result.png"],
    }
    assert task.status == "processing"
    assert enqueued_downloads == [(403, "lingyaai", ["https://example.test/query-result.png"])]


@pytest.mark.asyncio
async def test_result_download_operation_success_terminalizes_task(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=404,
        user_id=9,
        status="processing",
        result_urls=None,
        terminal_side_effects_finalized_at=None,
    )
    operation = SimpleNamespace(id=41, payload={"result_urls": ["https://example.test/final.png"]})
    repo_events: list[tuple[str, dict]] = []
    finalized: list[int] = []

    class FakeProviderOperationRepository:
        def __init__(self, db):
            pass

        async def mark_succeeded(self, op, *, result_payload=None):
            assert op is operation
            repo_events.append(("succeeded", result_payload or {}))
            return op

        async def mark_failed(self, *_args, **_kwargs):
            raise AssertionError("successful download must not fail operation")

    async def fake_store_urls(existing_task, urls):
        assert urls == ["https://example.test/final.png"]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/final.png",
            "result_urls": ["/api/v1/uploads/generated/final.png"],
        }

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    async def fake_finalize(existing_task):
        finalized.append(existing_task.id)

    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_finalize_terminal_side_effects", fake_finalize)
    monkeypatch.setattr(generation_service_module, "ProviderOperationRepository", FakeProviderOperationRepository)

    await service.complete_result_download_operation(task, operation)

    assert task.status == "completed"
    assert task.workflow_stage == "terminal_completed"
    assert task.last_error_type is None
    assert task.result_urls == ["/api/v1/uploads/generated/final.png"]
    assert repo_events == [("succeeded", {"result_urls": ["/api/v1/uploads/generated/final.png"]})]
    assert finalized == [404]


@pytest.mark.asyncio
async def test_result_download_operation_failure_terminalizes_task(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(id=405, user_id=9, status="processing", terminal_side_effects_finalized_at=None)
    operation = SimpleNamespace(id=51, payload={"result_urls": ["https://example.test/final.png"]})
    repo_events: list[tuple[str, str | None]] = []
    finalized: list[int] = []

    class FakeProviderOperationRepository:
        def __init__(self, db):
            pass

        async def mark_succeeded(self, *_args, **_kwargs):
            raise AssertionError("failed download must not succeed operation")

        async def mark_failed(self, op, *, error_type, error_message=None):
            assert op is operation
            repo_events.append((error_type, error_message))
            return op

    async def fake_store_urls(existing_task, urls):
        return {
            "status": "failed",
            "error_message": "result_url_download_failed: ReadTimeout",
        }

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    async def fake_finalize(existing_task):
        finalized.append(existing_task.id)

    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_finalize_terminal_side_effects", fake_finalize)
    monkeypatch.setattr(generation_service_module, "ProviderOperationRepository", FakeProviderOperationRepository)

    await service.complete_result_download_operation(task, operation)

    assert task.status == "failed"
    assert task.workflow_stage == "terminal_failed"
    assert task.last_error_type == "result_download_failed"
    assert repo_events == [("result_download_failed", "result_url_download_failed: ReadTimeout")]
    assert finalized == [405]


@pytest.mark.asyncio
async def test_generate_image_normalizes_apimart_model_name_for_lingyaai(monkeypatch):
    service = GenerationService(db=None)

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            raise AssertionError("LingyaAI image submission should run in the background")

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 304
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    class FakeProviderOperationService:
        def __init__(self, db):
            pass

        async def enqueue_generation_submit(self, task, *, task_kind, provider_code, priority):
            return SimpleNamespace(id=1)

    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_CODE", "lingyaai", raising=False)
    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(generation_service_module, "get_active_builtin_provider", lambda api_key: FakeBuiltinProvider())
    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="gemini-3.1-flash-image-preview-official",
        provider_code="builtin",
    )

    assert task.model_name == "nano-banana-2"
    assert task.model_label == "NanoBanana2"


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_stores_result_and_request_ids(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=303,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="Gemini-3.1-flash-image-preview",
        model_label="LingyaAI Image",
        prompt="blue banana",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        params={
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "image_urls": None,
            "mask_url": None,
            "image_count": 1,
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            assert kwargs["prompt"] == "blue banana"
            return BuiltinSubmitResult(
                status="completed",
                external_task_id="lingyaai-sync:req-1",
                result_urls=["data:image/png;base64,aW1hZ2U="],
                progress=100,
                oneapi_request_id="req-1",
                request_id="trace-1",
                raw={"id": "image-response-1"},
            )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 303
        assert user_id == 9
        return task

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    async def fake_store_urls(existing_task, urls):
        assert urls == ["data:image/png;base64,aW1hZ2U="]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/lingyaai-result.png",
            "result_urls": ["/api/v1/uploads/generated/lingyaai-result.png"],
            "progress": 100,
        }

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())

    await service.complete_lingyaai_image_task(task_id=303, user_id=9)

    assert task.status == "completed"
    assert task.external_task_id == "lingyaai-sync:req-1"
    assert task.result_url == "/api/v1/uploads/generated/lingyaai-result.png"
    assert task.result_urls == ["/api/v1/uploads/generated/lingyaai-result.png"]
    assert task.provider_request_id == "req-1"
    assert task.provider_trace_id == "trace-1"
    assert task.params["provider_submit"]["provider_code"] == "lingyaai"
    assert task.params["provider_submit"]["raw"] == {"id": "image-response-1"}


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_resolves_reference_without_persisting_base64(monkeypatch, tmp_path):
    service = GenerationService(db=None)
    conversation_dir = tmp_path / "users" / "9" / "conversations" / "conv-ref"
    reference_path = conversation_dir / "references" / "inputs" / "source.jpg"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"fake-image")

    task = SimpleNamespace(
        id=305,
        user_id=9,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="nano-banana-2",
        model_label="LingyaAI Image",
        prompt="blue banana",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}305",
        params={
            "aspect_ratio": "1:1",
            "resolution": "2K",
            "image_urls": ["references/inputs/source.jpg"],
            "agent_conversation_id": "conv-ref",
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            assert kwargs["image_urls"] == [str(reference_path.resolve())]
            return BuiltinSubmitResult(
                status="completed",
                external_task_id="lingyaai-sync:req-2",
                result_urls=["data:image/png;base64,aW1hZ2U="],
                oneapi_request_id="req-2",
                request_id="trace-2",
                raw={"data": [{"b64_json": "aW1hZ2U="}]},
            )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_get_by_id_and_user(task_id, user_id):
        return task

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    async def fake_store_urls(existing_task, urls):
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/lingyaai-result.png",
            "result_urls": ["/api/v1/uploads/generated/lingyaai-result.png"],
            "progress": 100,
        }

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation_dir",
        lambda user_id, conversation_id, **_kwargs: conversation_dir,
    )
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())

    await service.complete_lingyaai_image_task(task_id=305, user_id=9)

    assert task.status == "completed"
    assert task.params["image_urls"] == ["references/inputs/source.jpg"]
    assert task.params["provider_submit"]["raw"] == {"data": [{"b64_json": "[omitted-base64:chars=8]"}]}
    assert "data:image" not in str(task.params)
    assert "aW1hZ2U=" not in str(task.params)


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_forwards_canvas_reference_urls_to_provider(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=4,
        user_id=1,
        project_id=1,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="doubao-seedream-5-0-260128",
        model_label="Seedream 5.0 Lite",
        prompt="A cute monkey sitting and eating grapes",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}4",
        params={
            "aspect_ratio": "1:1",
            "resolution": "2K",
            "image_urls": ["/api/v1/uploads/canvas/1/2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"],
            "mask_url": None,
            "image_count": 1,
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )
    captured: dict[str, object] = {}

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            captured.update(kwargs)
            return BuiltinSubmitResult(
                status="completed",
                external_task_id="lingyaai-sync:req-3",
                result_urls=["data:image/png;base64,aW1hZ2U="],
                oneapi_request_id="req-3",
                request_id="trace-3",
                raw={"data": [{"b64_json": "aW1hZ2U="}]},
                request_diagnostics={
                    "provider": "lingyaai",
                    "operation": "image_submit",
                    "provider_payload_has_image": True,
                    "provider_payload_image_count": 1,
                    "provider_payload_images": {
                        "count": 1,
                        "kinds": {"remote_url": 1},
                        "transports": {"url": 1},
                        "mime_types": ["image/png"],
                        "items": [],
                    },
                },
            )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 4
        assert user_id == 1
        return task

    async def fake_update(existing_task, payload):
        for key, value in payload.items():
            setattr(existing_task, key, value)
        return existing_task

    async def fake_store_urls(existing_task, urls):
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/lingyaai-result.png",
            "result_urls": ["/api/v1/uploads/generated/lingyaai-result.png"],
            "progress": 100,
        }

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())

    await service.complete_lingyaai_image_task(task_id=4, user_id=1)

    assert captured["model_name"] == "doubao-seedream-5-0-260128"
    assert captured["image_urls"] == ["/api/v1/uploads/canvas/1/2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"]
    assert task.status == "completed"
    assert task.params["provider_submit"]["request_diagnostics"]["provider_payload_has_image"] is True
    assert task.params["reference_diagnostics"]["provider_request"]["provider_payload_image_count"] == 1


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_does_not_materialize_when_scheduler_claim_is_lost(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=303,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="Gemini-3.1-flash-image-preview",
        model_label="LingyaAI Image",
        prompt="blue banana",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        scheduler_claim_token="current-owner",
        params={
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "image_urls": None,
            "mask_url": None,
            "image_count": 1,
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )
    materialized: list[list[str]] = []

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 303
        assert user_id == 9
        return task

    async def fail_get_credentials(user_id, provider_code):
        raise AssertionError("lost scheduler claim must not call the provider")

    async def fake_store_urls(existing_task, urls):
        materialized.append(list(urls))
        return {"status": "completed", "result_url": "/generated.png"}

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service, "_get_credentials", fail_get_credentials)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)

    await service.complete_lingyaai_image_task(
        task_id=303,
        user_id=9,
        scheduler_claim_token="lost-owner",
    )

    assert materialized == []
    assert task.status == "processing"


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_materializes_success_once(monkeypatch):
    service = GenerationService(db=object())
    task = SimpleNamespace(
        id=303,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="Gemini-3.1-flash-image-preview",
        model_label="LingyaAI Image",
        prompt="blue banana",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        scheduler_claim_token="claim-1",
        params={
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "image_urls": None,
            "mask_url": None,
            "image_count": 1,
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )
    materialized: list[list[str]] = []
    finalized: list[int] = []

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            return BuiltinSubmitResult(
                status="completed",
                external_task_id="lingyaai-sync:req-1",
                result_urls=["data:image/png;base64,aW1hZ2U="],
                progress=100,
                oneapi_request_id="req-1",
                request_id="trace-1",
                raw={"id": "image-response-1"},
            )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_get_by_id_and_user(task_id, user_id):
        return task

    async def fake_update_for_scheduler_claim(*, task_id, user_id, claim_token, data):
        assert claim_token == "claim-1"
        for key, value in data.items():
            setattr(task, key, value)
        return task

    async def fake_store_urls(existing_task, urls):
        materialized.append(list(urls))
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/lingyaai-result.png",
            "result_urls": ["/api/v1/uploads/generated/lingyaai-result.png"],
            "progress": 100,
        }

    async def fake_finalize(updated_task):
        finalized.append(updated_task.id)

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update_for_scheduler_claim", fake_update_for_scheduler_claim, raising=False)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store_urls)
    monkeypatch.setattr(service, "_finalize_terminal_side_effects", fake_finalize)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())

    await service.complete_lingyaai_image_task(task_id=303, user_id=9, scheduler_claim_token="claim-1")
    await service.complete_lingyaai_image_task(task_id=303, user_id=9, scheduler_claim_token="claim-1")

    assert materialized == [["data:image/png;base64,aW1hZ2U="]]
    assert finalized == [303]
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_complete_lingyaai_image_task_records_provider_failure_without_materialization(monkeypatch):
    service = GenerationService(db=object())
    task = SimpleNamespace(
        id=303,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        model_name="Gemini-3.1-flash-image-preview",
        model_label="LingyaAI Image",
        prompt="blue banana",
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        scheduler_claim_token="claim-1",
        params={
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "image_urls": None,
            "mask_url": None,
            "image_count": 1,
            "provider_submit": {"provider_code": "lingyaai"},
        },
    )
    updates: list[dict] = []
    finalized: list[int] = []

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def submit_image(self, **kwargs):
            return BuiltinSubmitResult(
                status="failed",
                external_task_id="lingyaai-sync:req-1",
                error_message="provider rejected request",
                oneapi_request_id="req-1",
                request_id="trace-1",
                raw={"id": "image-response-1"},
            )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_get_by_id_and_user(task_id, user_id):
        return task

    async def fake_update_for_scheduler_claim(*, task_id, user_id, claim_token, data):
        assert claim_token == "claim-1"
        updates.append(dict(data))
        for key, value in data.items():
            setattr(task, key, value)
        return task

    async def fail_store_urls(existing_task, urls):
        raise AssertionError("failed LingyaAI tasks must not materialize result URLs")

    async def fake_finalize(updated_task):
        finalized.append(updated_task.id)

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update_for_scheduler_claim", fake_update_for_scheduler_claim, raising=False)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fail_store_urls)
    monkeypatch.setattr(service, "_finalize_terminal_side_effects", fake_finalize)
    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())

    await service.complete_lingyaai_image_task(task_id=303, user_id=9, scheduler_claim_token="claim-1")

    assert len(updates) == 1
    assert finalized == [303]
    assert task.status == "failed"
    assert task.error_message == "provider rejected request"
    assert task.workflow_stage == "terminal_failed"
    assert task.last_error_type == "provider_failed"
    assert task.terminalized_at is not None
    assert task.scheduler_claim_token is None


@pytest.mark.asyncio
async def test_query_task_status_keeps_processing_for_internal_lingyaai_image_task(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=303,
        user_id=9,
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        provider_code="builtin",
        task_type="text2image",
        builtin_provider_code="lingyaai",
        params={"provider_submit": {"provider_code": "lingyaai"}},
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 303
        assert user_id == 9
        return task

    async def fail_get_credentials(user_id, provider_code):
        raise AssertionError("internal LingyaAI image tasks should not query provider while processing")

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service, "_get_credentials", fail_get_credentials)

    result = await service.query_task_status(303, 9)

    assert result is task
    assert result.status == "processing"


@pytest.mark.asyncio
async def test_query_task_status_keeps_internal_lingyaai_image_task_read_only_for_scheduler_claim(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=303,
        user_id=9,
        status="processing",
        external_task_id=f"{generation_service_module.LINGYAAI_IMAGE_PENDING_TASK_PREFIX}303",
        provider_code="builtin",
        task_type="text2image",
        builtin_provider_code="lingyaai",
        params={"provider_submit": {"provider_code": "lingyaai"}},
    )
    calls: list[tuple[int, int, str | None]] = []

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 303
        assert user_id == 9
        return task

    async def fake_complete_lingyaai_image_task(*, task_id, user_id, scheduler_claim_token=None):
        calls.append((task_id, user_id, scheduler_claim_token))

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service, "complete_lingyaai_image_task", fake_complete_lingyaai_image_task)

    result = await service.query_task_status(303, 9, scheduler_claim_token="claim-1")

    assert calls == []
    assert result is task
    assert result.status == "processing"


@pytest.mark.asyncio
async def test_query_builtin_uses_active_provider_adapter_and_keeps_submit_request_ids(monkeypatch):
    service = GenerationService(db=None)

    class FakeBuiltinProvider:
        code = "lingyaai"

        async def query_generation(self, external_task_id, *, task_type, model_name):
            assert external_task_id == "video-1"
            assert task_type == "text2video"
            assert model_name == "kling-v3-video-generation"
            return BuiltinQueryResult(
                status="completed",
                result_urls=["https://example.com/result.mp4"],
                progress=100,
                oneapi_request_id="req-video-1",
                request_id="trace-video-1",
                raw={"id": "video-1", "status": "completed"},
            )

    async def fake_download(url, ext, target_url=None):
        assert url == "https://example.com/result.mp4"
        assert ext == "mp4"
        return "/api/v1/uploads/generated/result.mp4"

    monkeypatch.setattr(generation_service_module, "get_builtin_provider", lambda provider_code, api_key=None: FakeBuiltinProvider())
    monkeypatch.setattr(service, "_download_file_to_local", fake_download)

    task = SimpleNamespace(
        external_task_id="video-1",
        task_type="text2video",
        model_name="kling-v3-video-generation",
        params={
            "provider_submit": {
                "provider_code": "lingyaai",
                "raw": {"id": "video-1", "status": "pending"},
            }
        },
    )
    cred = SimpleNamespace(access_key="test-key")

    result = await service._query_builtin(task, cred)

    assert result["status"] == "completed"
    assert result["result_url"] == "/api/v1/uploads/generated/result.mp4"
    assert result["params"]["provider_submit"]["provider_code"] == "lingyaai"
    assert result["params"]["provider_submit"]["raw"] == {"id": "video-1", "status": "pending"}


@pytest.mark.asyncio
async def test_generate_image_for_builtin_clamps_requested_image_count_to_one(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 1001
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
        image_count=2,
    )

    assert task.params["image_count"] == 1
    assert task.external_task_id is None
    assert task.status == "processing"
    assert enqueued[0]["task_kind"] == "image"
    assert enqueued[0]["task"].params["image_count"] == 1


@pytest.mark.asyncio
async def test_generate_image_allows_null_project_id_for_home_scope(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 304
        assert task.project_id is None
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=None,
        prompt="blue banana",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
    )

    assert task.id == 304
    assert task.project_id is None
    assert task.external_task_id is None
    assert task.status == "processing"
    assert enqueued[0]["task"].project_id is None


def _enable_ollama_image_generation(monkeypatch, *, config: str | None = None):
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_GENERATION_ENABLED", True)
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_GENERATION_MODEL", "gpt-image-2")
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_BASE_URL", "http://ollama.test/v1")
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_API_KEY", "test-ollama-key")
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_API_KEY", "")
    monkeypatch.setattr(
        generation_service_module.settings,
        "OLLAMA_IMAGE_GENERATION_CONFIG",
        config
        or "sizes=1K|2K|4K;ratios=1:1|16:9|9:16|2:1|1:2|4:3|3:4|3:2|2:3|5:4|4:5|21:9|9:21|3:1|1:3;reference=true;max_refs=16;response_format=url;reference_mode=edits",
    )


@pytest.mark.asyncio
async def test_ollama_generation_credentials_prefer_image_key_then_ollama_api_key(monkeypatch):
    service = GenerationService(db=None)
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_API_KEY", "legacy-key")
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_API_KEY", "image-key")

    credentials = await service._get_credentials(user_id=9, provider_code="ollama")

    assert credentials.access_key == "image-key"

    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_API_KEY", "")

    credentials = await service._get_credentials(user_id=9, provider_code="ollama")

    assert credentials.access_key == "legacy-key"


async def _attach_memory_task_repo(service: GenerationService):
    async def fake_create(task):
        task.id = 900
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    service.task_repo.create = fake_create
    service.task_repo.update = fake_update


def _capture_provider_operation_enqueues(monkeypatch):
    enqueued: list[dict[str, object]] = []

    class FakeProviderOperationService:
        def __init__(self, db):
            pass

        async def enqueue_generation_submit(self, task, *, task_kind, provider_code, priority):
            enqueued.append(
                {
                    "task": task,
                    "task_kind": task_kind,
                    "provider_code": provider_code,
                    "priority": priority,
                }
            )
            return SimpleNamespace(id=len(enqueued))

    monkeypatch.setattr(generation_service_module, "ProviderOperationService", FakeProviderOperationService)
    return enqueued


@pytest.mark.asyncio
async def test_generate_image_for_ollama_returns_processing_and_enqueues_durable_completion(monkeypatch):
    service = GenerationService(db=None)
    await _attach_memory_task_repo(service)
    _enable_ollama_image_generation(monkeypatch)
    scheduled: list[tuple[int, int]] = []

    def fake_schedule_completion(*, task_id, user_id):
        scheduled.append((task_id, user_id))

    monkeypatch.setattr(service, "_schedule_ollama_image_completion", fake_schedule_completion)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="gpt-image-2",
        provider_code="ollama",
        aspect_ratio="16:9",
        resolution="2K",
    )

    assert task.status == "processing"
    assert task.external_task_id == f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}900"
    assert task.workflow_stage == "ollama_image_submit"
    assert task.scheduler_next_run_at is not None
    assert task.params["provider_submit"]["provider_code"] == "ollama"
    assert scheduled == [(900, 9)]


@pytest.mark.asyncio
async def test_complete_ollama_image_task_uses_generations_without_references(monkeypatch):
    service = GenerationService(db=None)
    _enable_ollama_image_generation(monkeypatch)
    calls: list[dict] = []

    async def fake_generate_image(self, **kwargs):
        calls.append(kwargs)
        return {"id": "img-1", "result_values": ["https://example.test/result.png"]}

    async def fake_edit_image(self, **kwargs):
        raise AssertionError("edit_image should not be called without references")

    async def fake_store(task, urls):
        assert urls == ["https://example.test/result.png"]
        return {"status": "completed", "result_url": "/api/v1/uploads/generated/result.png", "result_urls": ["/api/v1/uploads/generated/result.png"], "progress": 100}

    task = GenerationTask(
        id=902,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="blue banana",
        params={
            "resolution": "2K",
            "aspect_ratio": "16:9",
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}902",
        workflow_stage="ollama_image_submit",
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 902
        assert user_id == 9
        return task

    async def fake_update(task_obj, payload):
        for key, value in payload.items():
            setattr(task_obj, key, value)
        return task_obj

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.edit_image", fake_edit_image)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store)

    await service.complete_ollama_image_task(task_id=902, user_id=9)

    assert calls == [
        {
            "model_name": "gpt-image-2",
            "prompt": "blue banana",
            "size": "2048x1152",
            "response_format": None,
            "quality": None,
        }
    ]
    assert task.status == "completed"
    assert task.external_task_id == "ollama-sync:img-1"


@pytest.mark.asyncio
async def test_complete_ollama_image_task_retries_retryable_ollama_failures(monkeypatch):
    service = GenerationService(db=None)
    _enable_ollama_image_generation(monkeypatch)
    attempts = 0
    sleeps: list[float] = []

    async def fake_generate_image(self, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return {"_status_code": 502, "error": {"message": "temporary Ollama outage"}}
        return {"id": "img-retry", "result_values": ["https://example.test/result.png"]}

    async def fake_store(task, urls):
        assert urls == ["https://example.test/result.png"]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/result.png",
            "result_urls": ["/api/v1/uploads/generated/result.png"],
            "progress": 100,
        }

    async def fake_sleep(delay):
        sleeps.append(delay)

    task = GenerationTask(
        id=903,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="blue banana",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}903",
        workflow_stage="ollama_image_submit",
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 903
        assert user_id == 9
        return task

    async def fake_update(task_obj, payload):
        for key, value in payload.items():
            setattr(task_obj, key, value)
        return task_obj

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store)
    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    await service.complete_ollama_image_task(task_id=903, user_id=9)

    assert attempts == 3
    assert sleeps == [1, 2]
    assert task.status == "completed"
    assert task.external_task_id == "ollama-sync:img-retry"


@pytest.mark.asyncio
async def test_complete_ollama_image_task_does_not_retry_non_retryable_ollama_failure(monkeypatch):
    service = GenerationService(db=None)
    _enable_ollama_image_generation(monkeypatch)
    attempts = 0
    sleeps: list[float] = []

    async def fake_generate_image(self, **kwargs):
        nonlocal attempts
        attempts += 1
        return {"_status_code": 400, "error": {"message": "bad Ollama request"}}

    async def fake_sleep(delay):
        sleeps.append(delay)

    task = GenerationTask(
        id=904,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="blue banana",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}904",
        workflow_stage="ollama_image_submit",
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 904
        assert user_id == 9
        return task

    async def fake_update(task_obj, payload):
        for key, value in payload.items():
            setattr(task_obj, key, value)
        return task_obj

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr(generation_service_module.asyncio, "sleep", fake_sleep)

    await service.complete_ollama_image_task(task_id=904, user_id=9)

    assert attempts == 1
    assert sleeps == []
    assert task.status == "failed"
    assert task.error_message == "bad Ollama request"


@pytest.mark.asyncio
async def test_complete_ollama_image_task_records_zero_cost_usage_log(db_session, monkeypatch):
    _enable_ollama_image_generation(monkeypatch)
    user = User(
        email="ollama-image-billing@example.test",
        username="ollama-image-billing",
        hashed_password="hashed",
        balance_cents=0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    billing_svc = BillingService(db_session)
    parent_log = await billing_svc.create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="agent_harness",
        task_type="agent",
        amount_cents=0,
        params={
            "engine": "agent_harness",
            "conversation_id": "conv-ollama-image-billing",
            "agent_run_id": "run-ollama-image-billing",
            "billing_summary": {},
        },
        task_status="pending",
        billing_label="billing.labels.agent_canvas",
    )
    task = GenerationTask(
        user_id=user.id,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="blue banana",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "parent_usage_log_id": parent_log.id,
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}0",
        workflow_stage="ollama_image_submit",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    task.external_task_id = f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}{task.id}"
    await db_session.commit()
    await db_session.refresh(task)

    async def fake_generate_image(self, **kwargs):
        return {"id": "img-billing", "result_values": ["https://example.test/result.png"]}

    async def fake_store(task_obj, urls):
        assert urls == ["https://example.test/result.png"]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/result.png",
            "result_urls": ["/api/v1/uploads/generated/result.png"],
            "progress": 100,
        }

    service = GenerationService(db_session)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store)

    await service.complete_ollama_image_task(task_id=task.id, user_id=user.id)

    usage_log = (
        await db_session.execute(select(UsageLog).where(UsageLog.task_id == task.id))
    ).scalar_one()
    assert usage_log.parent_id == parent_log.id
    assert usage_log.provider_code == "ollama"
    assert usage_log.model_name == "gpt-image-2"
    assert usage_log.model_label == "Ollama Image (gpt-image-2)"
    assert usage_log.task_type == "text2image"
    assert usage_log.amount_cents == 0
    assert usage_log.status == "success"
    assert usage_log.billing_label == "billing.labels.image_generate"
    assert UsageLogListRead.model_validate(usage_log).model_label == "Ollama Image (gpt-image-2)"

    refreshed_parent = await db_session.get(UsageLog, parent_log.id)
    summary = refreshed_parent.params["billing_summary"]
    assert summary["image_generation_calls"] == 1
    assert summary["image_models"] == ["gpt-image-2"]
    assert summary["image_model_stats"] == [
        {
            "model_name": "gpt-image-2",
            "model_label": "Ollama Image (gpt-image-2)",
            "calls": 1,
            "success_calls": 1,
            "failed_calls": 0,
        }
    ]


@pytest.mark.asyncio
async def test_complete_ollama_image_task_does_not_record_unknown_request_id(db_session, monkeypatch):
    _enable_ollama_image_generation(monkeypatch)
    user = User(
        email="ollama-image-no-request-id@example.test",
        username="ollama-image-no-request-id",
        hashed_password="hashed",
        balance_cents=0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="blue banana",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}0",
        workflow_stage="ollama_image_submit",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    task.external_task_id = f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}{task.id}"
    await db_session.commit()
    await db_session.refresh(task)

    async def fake_generate_image(self, **kwargs):
        return {"result_values": ["https://example.test/result.png"]}

    async def fake_store(task_obj, urls):
        assert urls == ["https://example.test/result.png"]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/result.png",
            "result_urls": ["/api/v1/uploads/generated/result.png"],
            "progress": 100,
        }

    service = GenerationService(db_session)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store)

    await service.complete_ollama_image_task(task_id=task.id, user_id=user.id)

    usage_log = (
        await db_session.execute(select(UsageLog).where(UsageLog.task_id == task.id))
    ).scalar_one()
    assert task.external_task_id is None
    assert usage_log.params["request_id"] is None
    assert usage_log.params["external_task_id"] is None
    assert usage_log.params["generation_task"]["request_id"] is None
    assert usage_log.params["generation_task"]["external_task_id"] is None


@pytest.mark.asyncio
async def test_complete_ollama_image_task_uses_edits_with_references(monkeypatch, tmp_path):
    service = GenerationService(db=None)
    _enable_ollama_image_generation(monkeypatch)
    monkeypatch.chdir(tmp_path)
    ref_path = tmp_path / "uploads" / "canvas" / "5" / "ref.png"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_bytes(b"ref")
    uploads = _configure_fake_tos(monkeypatch)
    calls: list[dict] = []

    async def fake_edit_image(self, **kwargs):
        calls.append(kwargs)
        return {"id": "edit-1", "result_values": ["data:image/png;base64,aW1hZ2U="]}

    task = GenerationTask(
        id=901,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="gpt-image-2",
        prompt="make variant",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "image_urls": ["/api/v1/uploads/canvas/5/ref.png"],
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}901",
        workflow_stage="ollama_image_submit",
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 901
        assert user_id == 9
        return task

    async def fake_update(task_obj, payload):
        for key, value in payload.items():
            setattr(task_obj, key, value)
        return task_obj

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.edit_image", fake_edit_image)

    await service.complete_ollama_image_task(
        task_id=901,
        user_id=9,
    )

    assert calls[0]["image_refs"] == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.png"
    ]
    assert uploads == [
        ("design-public", "generation-refs/fixedobjectkey.png", str(ref_path.resolve()))
    ]
    assert calls[0]["size"] == "1024x1024"
    assert calls[0]["response_format"] is None
    assert task.status == "completed"
    assert task.result_url.startswith("/api/v1/uploads/generated/")
    assert task.external_task_id == "ollama-sync:edit-1"
    assert task.params["provider_submit"]["request_diagnostics"]["reference_resolution"] == {
        "input_count": 1,
        "output_url_count": 1,
        "remote_input_count": 0,
        "object_storage_upload_count": 1,
        "transport_counts": {"remote_url": 0, "object_storage_url": 1},
    }


@pytest.mark.asyncio
async def test_complete_ollama_image_task_preserves_response_format_for_non_gpt_image_models(monkeypatch):
    service = GenerationService(db=None)
    _enable_ollama_image_generation(monkeypatch, config="sizes=1K;ratios=1:1;response_format=url")
    monkeypatch.setattr(generation_service_module.settings, "OLLAMA_IMAGE_GENERATION_MODEL", "legacy-image-model")
    calls: list[dict] = []

    async def fake_generate_image(self, **kwargs):
        calls.append(kwargs)
        return {"id": "img-legacy", "result_values": ["https://example.test/result.png"]}

    async def fake_store(task, urls):
        assert urls == ["https://example.test/result.png"]
        return {
            "status": "completed",
            "result_url": "/api/v1/uploads/generated/result.png",
            "result_urls": ["/api/v1/uploads/generated/result.png"],
            "progress": 100,
        }

    task = GenerationTask(
        id=905,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="ollama",
        model_name="legacy-image-model",
        prompt="blue banana",
        params={
            "resolution": "1K",
            "aspect_ratio": "1:1",
            "provider_submit": {"provider_code": "ollama"},
        },
        status="processing",
        external_task_id=f"{generation_service_module.OLLAMA_IMAGE_PENDING_TASK_PREFIX}905",
        workflow_stage="ollama_image_submit",
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 905
        assert user_id == 9
        return task

    async def fake_update(task_obj, payload):
        for key, value in payload.items():
            setattr(task_obj, key, value)
        return task_obj

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr("app.services.ollama_image_generation.OllamaClient.generate_image", fake_generate_image)
    monkeypatch.setattr(service, "_store_builtin_result_urls", fake_store)

    await service.complete_ollama_image_task(task_id=905, user_id=9)

    assert calls[0]["response_format"] == "url"
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_generate_image_for_ollama_rejects_references_when_disabled(monkeypatch):
    service = GenerationService(db=None)
    await _attach_memory_task_repo(service)
    _enable_ollama_image_generation(
        monkeypatch,
        config="sizes=1K;ratios=1:1;reference=false;max_refs=0;response_format=url;reference_mode=edits",
    )

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="make variant",
        model_name="gpt-image-2",
        provider_code="ollama",
        image_urls=["/api/v1/uploads/canvas/5/ref.png"],
    )

    assert task.status == "failed"
    assert task.error_message == "当前 Ollama 图片模型未开启参考图能力"


@pytest.mark.asyncio
async def test_generate_image_for_ollama_rejects_too_many_references(monkeypatch):
    service = GenerationService(db=None)
    await _attach_memory_task_repo(service)
    _enable_ollama_image_generation(
        monkeypatch,
        config="sizes=1K;ratios=1:1;reference=true;max_refs=1;response_format=url;reference_mode=edits",
    )

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="make variant",
        model_name="gpt-image-2",
        provider_code="ollama",
        image_urls=["/api/v1/uploads/canvas/5/a.png", "/api/v1/uploads/canvas/5/b.png"],
    )

    assert task.status == "failed"
    assert task.error_message == "当前 Ollama 图片模型最多支持 1 张参考图"


@pytest.mark.asyncio
async def test_generate_image_for_ollama_rejects_unresolved_local_reference_path(monkeypatch):
    service = GenerationService(db=None)
    await _attach_memory_task_repo(service)
    _enable_ollama_image_generation(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="make variant",
        model_name="gpt-image-2",
        provider_code="ollama",
        image_urls=["../../private.png"],
    )

    assert task.status == "failed"
    assert task.error_message == "参考图路径无法解析"


@pytest.mark.asyncio
async def test_generate_image_for_builtin_retries_submission_before_succeeding(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 1351
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
    )

    assert task.external_task_id is None
    assert task.status == "processing"
    assert enqueued[0]["task_kind"] == "image"


@pytest.mark.asyncio
async def test_generate_image_for_builtin_returns_failed_task_when_provider_submit_fails(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 101
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
    )

    assert task.id == 101
    assert task.status == "processing"
    assert task.external_task_id is None
    assert task.error_message is None
    assert enqueued[0]["task_kind"] == "image"


@pytest.mark.asyncio
async def test_generate_image_for_builtin_uses_provider_request_policy_before_submit(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 102
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
    )

    assert task.id == 102
    assert task.status == "processing"
    assert task.error_message is None
    assert enqueued[0]["provider_code"] == "apimart"


@pytest.mark.asyncio
async def test_generate_image_can_resubmit_existing_task_id(monkeypatch):
    service = GenerationService(db=None)
    existing_task = SimpleNamespace(
        id=42,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream-5.0-lite",
        model_label="Seedream-5.0-Lite",
        prompt="old prompt",
        params={},
        status="failed",
        external_task_id="old-external",
        result_url=None,
        result_urls=None,
        error_message="provider failed",
        progress=0,
        scheduler_claim_token="stale-token",
        scheduler_claimed_at=datetime.now(UTC),
        scheduler_lease_expires_at=datetime.now(UTC),
    )

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        raise AssertionError("retry should not create a new generation task")

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="new prompt",
        model_name="seedream-5.0-lite",
        provider_code="builtin",
        existing_task=existing_task,
    )

    assert task.id == 42
    assert task.prompt == "new prompt"
    assert task.external_task_id is None
    assert task.status == "processing"
    assert task.scheduler_claim_token is None
    assert task.scheduler_claimed_at is None
    assert task.scheduler_lease_expires_at is None
    assert enqueued[0]["task"].id == 42


@pytest.mark.asyncio
async def test_generate_video_resubmit_clears_stale_scheduler_claim(monkeypatch):
    service = GenerationService(db=None)
    existing_task = SimpleNamespace(
        id=43,
        user_id=9,
        project_id=5,
        task_type="text2video",
        provider_code="builtin",
        model_name="kling-v3",
        model_label="Kling",
        prompt="old video prompt",
        params={},
        status="failed",
        external_task_id="old-video-external",
        result_url=None,
        result_urls=None,
        error_message="provider failed",
        progress=0,
        scheduler_claim_token="stale-token",
        scheduler_claimed_at=datetime.now(UTC),
        scheduler_lease_expires_at=datetime.now(UTC),
    )

    class FakeBuiltinProvider:
        code = "apimart"

    async def fake_get_credentials(user_id, provider_code):
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        raise AssertionError("retry should not create a new generation task")

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(generation_service_module, "get_active_builtin_provider", lambda api_key: FakeBuiltinProvider())
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_video(
        user_id=9,
        project_id=5,
        prompt="new video prompt",
        model_name="kling-v3",
        provider_code="builtin",
        existing_task=existing_task,
    )

    assert task.id == 43
    assert task.prompt == "new video prompt"
    assert task.external_task_id is None
    assert task.status == "processing"
    assert task.scheduler_claim_token is None
    assert task.scheduler_claimed_at is None
    assert task.scheduler_lease_expires_at is None
    assert enqueued[0]["task_kind"] == "video"


@pytest.mark.asyncio
async def test_generate_image_reuses_existing_client_request_id_without_resubmitting(monkeypatch):
    service = GenerationService(db=None)
    existing_task = SimpleNamespace(
        id=84,
        user_id=9,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        model_name="gemini-3.1-flash-image-preview-official",
        model_label="NanoBanana2",
        prompt="keep this one running",
        params={"aspect_ratio": "1:1", "resolution": "1K"},
        status="processing",
        external_task_id="existing-provider-task",
        result_url=None,
        result_urls=None,
        error_message=None,
        progress=0,
        client_request_id="canvas-request-1",
    )

    async def fake_lookup(*, user_id, project_id, task_type, client_request_id):
        assert user_id == 9
        assert project_id == 5
        assert task_type == "text2image"
        assert client_request_id == "canvas-request-1"
        return existing_task

    async def fake_create(task):
        raise AssertionError("idempotent generation should not create a second task")

    async def fake_get_credentials(user_id, provider_code):
        raise AssertionError("idempotent generation should not submit the provider request again")

    monkeypatch.setattr(service.task_repo, "get_by_client_request_id", fake_lookup, raising=False)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="new prompt that should be ignored for the in-flight task",
        model_name="gemini-3.1-flash-image-preview-official",
        provider_code="builtin",
        client_request_id="canvas-request-1",
    )

    assert task is existing_task
    assert task.id == 84
    assert task.client_request_id == "canvas-request-1"


@pytest.mark.asyncio
async def test_generate_video_for_builtin_returns_failed_task_when_provider_submit_fails(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 202
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_video(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="kling-v3",
        provider_code="builtin",
    )

    assert task.id == 202
    assert task.status == "processing"
    assert task.external_task_id is None
    assert task.error_message is None
    assert enqueued[0]["task_kind"] == "video"


@pytest.mark.asyncio
async def test_generate_image_clamps_resolution_to_highest_supported_size_for_model(monkeypatch):
    service = GenerationService(db=None)

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key", secret_key="", auth_type="api_key")

    async def fake_create(task):
        task.id = 1724
        return task

    async def fake_update(task, payload):
        for key, value in payload.items():
            setattr(task, key, value)
        return task

    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service.task_repo, "create", fake_create)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    enqueued = _capture_provider_operation_enqueues(monkeypatch)

    task = await service.generate_image(
        user_id=9,
        project_id=5,
        prompt="blue banana",
        model_name="doubao-seedream-5-0-lite",
        provider_code="builtin",
        resolution="4K",
    )

    assert task.params["resolution"] == "3K"
    assert task.external_task_id is None
    assert task.status == "processing"
    assert enqueued[0]["task"].params["resolution"] == "3K"


def test_generation_task_read_exposes_task_params():
    payload = GenerationTaskRead.model_validate(
        SimpleNamespace(
            id=7,
            project_id=3,
            task_type="text2image",
            provider_code="builtin",
            model_name="seedream-5.0-lite",
            model_label="Seedream-5.0-Lite",
            prompt="blue banana",
            status="failed",
            progress=0,
            external_task_id="ext-7",
            result_url=None,
            result_urls=None,
            error_message="provider rejected prompt",
            params={"resolution": "2K", "aspect_ratio": "1:1"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    assert payload.model_label == "Seedream-5.0-Lite"
    assert payload.params == {"resolution": "2K", "aspect_ratio": "1:1"}


@pytest.mark.asyncio
async def test_query_task_status_logs_failed_task_details(monkeypatch, caplog):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=42,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream-5.0-lite",
        model_label="Seedream-5.0-Lite",
        prompt="blue banana",
        status="processing",
        progress=20,
        external_task_id="ext-42",
        result_url=None,
        result_urls=None,
        error_message=None,
        params={"resolution": "2K", "aspect_ratio": "1:1"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 42
        assert user_id == 9
        return task

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key")

    async def fake_query_builtin(current_task, cred):
        assert current_task is task
        assert cred.access_key == "test-key"
        return {"status": "failed", "error_message": "provider rejected prompt"}

    async def fake_update(current_task, payload):
        return SimpleNamespace(**{**current_task.__dict__, **payload})

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update", fake_update)
    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service, "_query_builtin", fake_query_builtin)

    caplog.set_level(logging.ERROR)

    updated = await service.query_task_status(42, 9)

    assert updated.status == "failed"
    assert updated.error_message == "provider rejected prompt"
    assert "Generation task failed" in caplog.text
    assert "task_id=42" in caplog.text
    assert "provider=builtin" in caplog.text
    assert "model=seedream-5.0-lite" in caplog.text


@pytest.mark.asyncio
async def test_query_task_status_does_not_terminalize_when_scheduler_claim_is_lost(monkeypatch):
    service = GenerationService(db=None)
    task = SimpleNamespace(
        id=42,
        project_id=5,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream-5.0-lite",
        model_label="Seedream-5.0-Lite",
        prompt="blue banana",
        status="processing",
        progress=20,
        external_task_id="ext-42",
        result_url=None,
        result_urls=None,
        error_message=None,
        params={"resolution": "2K", "aspect_ratio": "1:1"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    updates: list[dict] = []

    async def fake_get_by_id_and_user(task_id, user_id):
        assert task_id == 42
        assert user_id == 9
        return task

    async def fake_get_credentials(user_id, provider_code):
        assert user_id == 9
        assert provider_code == "builtin"
        return SimpleNamespace(access_key="test-key")

    async def fake_query_builtin(current_task, cred):
        assert current_task is task
        assert cred.access_key == "test-key"
        return {"status": "completed", "result_url": "https://cdn.example/image.png"}

    async def fake_update_if_claimed(*, task_id, user_id, claim_token, data):
        assert task_id == 42
        assert user_id == 9
        assert claim_token == "lost-token"
        updates.append(data)
        return None

    async def fake_blind_update(_current_task, _payload):
        raise AssertionError("scheduler-owned status queries must not blind-update generation tasks")

    monkeypatch.setattr(service.task_repo, "get_by_id_and_user", fake_get_by_id_and_user)
    monkeypatch.setattr(service.task_repo, "update_for_scheduler_claim", fake_update_if_claimed, raising=False)
    monkeypatch.setattr(service.task_repo, "update", fake_blind_update)
    monkeypatch.setattr(service, "_get_credentials", fake_get_credentials)
    monkeypatch.setattr(service, "_query_builtin", fake_query_builtin)

    updated = await service.query_task_status(42, 9, scheduler_claim_token="lost-token")

    assert len(updates) == 1
    assert updates[0]["status"] == "completed"
    assert updates[0]["result_url"] == "https://cdn.example/image.png"
    assert updates[0]["workflow_stage"] == "terminal_completed"
    assert updates[0]["terminalized_at"] is not None
    assert updates[0]["scheduler_claim_token"] is None
    assert updated.status == "processing"
