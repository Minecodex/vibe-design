import pytest
from fastapi import HTTPException

from app.services.multimodal_service import MultimodalService, get_multimodal_model_config
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def _per_user_provider_key(monkeypatch):
    monkeypatch.setattr(
        MultimodalService,
        "_resolve_builtin_key",
        AsyncMock(return_value=("test-key", 1)),
    )



def test_create_builtin_client_uses_explicit_user_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY",
        "",
    )

    client = MultimodalService._create_builtin_client("test-user-key")
    assert client._auth_headers()["Authorization"] == "Bearer test-user-key"


@pytest.mark.asyncio
async def test_chat_rejects_unsupported_model_with_readable_message():
    service = MultimodalService(db=object())

    with pytest.raises(HTTPException) as exc_info:
        await service.chat(
            user_id=1,
            model_name="bad-model",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "不支持的多模态模型: bad-model"


@pytest.mark.asyncio
async def test_chat_surfaces_readable_provider_error_message(monkeypatch):
    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 10

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def chat_completions(self, **kwargs):
            return {"error": {"message": "bad request"}}

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.get_active_builtin_provider", lambda api_key: FakeApimartClient(api_key))
    monkeypatch.setattr(
        "app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY",
        "test-key",
    )

    service = MultimodalService(db=object())

    with pytest.raises(HTTPException) as exc_info:
        await service.chat(
            user_id=1,
            model_name="gemini-3.1-pro-preview",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "多模态模型调用失败: bad request"


@pytest.mark.asyncio
async def test_chat_stream_surfaces_readable_provider_error_message(monkeypatch):
    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 100

        async def deduct_balance(self, user_id, amount):
            return True

        async def refund_balance(self, user_id, amount):
            return None

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.last_stream_usage = {}

        async def chat_completions_stream(self, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.ApimartClient", FakeApimartClient)
    monkeypatch.setattr(
        "app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY",
        "test-key",
    )

    service = MultimodalService(db=object())

    with pytest.raises(HTTPException) as exc_info:
        async for _ in service.chat_stream(
            user_id=1,
            model_name="gemini-3.1-pro-preview",
            messages=[{"role": "user", "content": "hello"}],
        ):
            pass

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "多模态模型流式调用失败: boom"


def test_get_multimodal_model_config_reads_builtin_registry_entry():
    config = get_multimodal_model_config("glm-5.1", "builtin")

    assert config is not None
    assert config["max_input_tokens"] == 204800
    assert config["max_output_tokens"] == 128000
    assert config["supports_thinking_mode"] is False


@pytest.mark.asyncio
async def test_chat_defaults_max_tokens_to_model_output_limit(monkeypatch):
    captured = {}

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 10

        def calculate_amount(self, model_name, input_tokens=None, output_tokens=None):
            return 0

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def chat_completions(self, **kwargs):
            captured.update(kwargs)
            return {
                "data": {
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                }
            }

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.get_active_builtin_provider", lambda api_key: FakeApimartClient(api_key))
    monkeypatch.setattr(
        "app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY",
        "test-key",
    )

    service = MultimodalService(db=object())

    await service.chat(
        user_id=1,
        model_name="glm-5.1",
        provider_code="builtin",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=0,
    )

    assert captured["max_tokens"] == 128000


@pytest.mark.asyncio
async def test_chat_ollama_records_zero_cost_usage_log(monkeypatch):
    created_logs: list[dict] = []

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def create_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            return None

    class FakeOllamaClient:
        def __init__(self, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key

        async def chat_completions(self, **kwargs):
            return {
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.OllamaClient", FakeOllamaClient)
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_API_KEY", "ollama")

    service = MultimodalService(db=object())

    result = await service.chat(
        user_id=1,
        model_name="gemma4:e4b",
        provider_code="ollama",
        messages=[{"role": "user", "content": "hello"}],
        task_type="mark_recognition",
        billing_label="billing.labels.mark_recognition",
    )

    assert result["_amount_cents"] == 0
    assert len(created_logs) == 1
    assert created_logs[0]["user_id"] == 1
    assert created_logs[0]["model_name"] == "gemma4:e4b"
    assert created_logs[0]["task_type"] == "mark_recognition"
    assert created_logs[0]["amount_cents"] == 0
    assert created_logs[0]["task_status"] == "success"
    assert created_logs[0]["billing_label"] == "billing.labels.mark_recognition"
    assert created_logs[0]["provider_code"] == "ollama"
    assert created_logs[0]["billing_mode"] == "local_zero_cost"
    assert created_logs[0]["params"]["input_tokens"] == 10
    assert created_logs[0]["params"]["output_tokens"] == 5


@pytest.mark.asyncio
async def test_chat_clamps_max_tokens_to_model_output_limit(monkeypatch):
    captured = {}

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 10

        def calculate_amount(self, model_name, input_tokens=None, output_tokens=None):
            return 0

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def chat_completions(self, **kwargs):
            captured.update(kwargs)
            return {
                "data": {
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                }
            }

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.get_active_builtin_provider", lambda api_key: FakeApimartClient(api_key))
    monkeypatch.setattr(
        "app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY",
        "test-key",
    )

    service = MultimodalService(db=object())

    await service.chat(
        user_id=1,
        model_name="glm-5.1",
        provider_code="builtin",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=200001,
    )

    assert captured["max_tokens"] == 128000
