import pytest

from app.services.multimodal_service import MultimodalService


@pytest.mark.asyncio
async def test_chat_stream_exposes_stream_usage_and_final_cost(monkeypatch):
    deducted_amounts: list[int] = []
    refunded_amounts: list[int] = []
    created_logs: list[dict] = []

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 100

        async def deduct_balance(self, user_id, amount):
            deducted_amounts.append(amount)
            return True

        async def refund_balance(self, user_id, amount):
            refunded_amounts.append(amount)

        def calculate_amount(self, model_name, input_tokens=None, output_tokens=None):
            assert model_name == "gemini-3.1-pro-preview"
            assert input_tokens == 123
            assert output_tokens == 45
            return 7

        async def create_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            return None

        async def create_provider_reconcile_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            return None

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.last_stream_usage = {
                "prompt_tokens": 123,
                "completion_tokens": 45,
            }

        async def chat_completions_stream(self, **kwargs):
            yield "A bright "
            yield "red apple"

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.ApimartClient", FakeApimartClient)
    monkeypatch.setattr("app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY", "test-key")

    service = MultimodalService(db=object())

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            user_id=1,
            model_name="gemini-3.1-pro-preview",
            messages=[{"role": "user", "content": "hello"}],
            billing_label="billing.labels.image_analysis",
        )
    ]

    assert chunks == ["A bright ", "red apple"]
    assert deducted_amounts == [1, 6]
    assert refunded_amounts == []
    assert service.last_stream_usage == {
        "prompt_tokens": 123,
        "completion_tokens": 45,
    }
    assert service.last_stream_amount_cents == 7
    assert service.last_stream_elapsed_ms >= 0
    assert created_logs[0]["amount_cents"] == 7
    assert created_logs[0]["params"]["streaming"] is True
    assert created_logs[0]["params"]["input_tokens"] == 123
    assert created_logs[0]["params"]["output_tokens"] == 45


@pytest.mark.asyncio
async def test_chat_stream_lingyaai_uses_bill_lookup_without_pre_deduct(monkeypatch):
    deducted_amounts: list[int] = []
    created_logs: list[dict] = []

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 100

        async def deduct_balance(self, user_id, amount):
            deducted_amounts.append(amount)
            return True

        async def refund_balance(self, user_id, amount):
            raise AssertionError("LingyaAI streaming should not pre-deduct")

        async def create_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            return None

        async def create_provider_reconcile_usage_log(self, **kwargs):
            created_logs.append(kwargs)
            return None

    class FakeLingyaAiProvider:
        code = "lingyaai"
        last_stream_usage = {"prompt_tokens": 11, "completion_tokens": 22}
        last_stream_provider_headers = {
            "x_oneapi_request_id": "oneapi-stream-1",
            "x_request_id": "trace-stream-1",
        }

        async def chat_completions_stream(self, **kwargs):
            yield "hello "
            yield "lingya"

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr("app.services.multimodal_service.get_active_builtin_provider", lambda api_key: FakeLingyaAiProvider())
    monkeypatch.setattr("app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY", "test-key")

    service = MultimodalService(db=object())

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            user_id=1,
            model_name="gemini-3.1-pro-preview",
            messages=[{"role": "user", "content": "hello"}],
            billing_label="billing.labels.image_analysis",
        )
    ]

    assert chunks == ["hello ", "lingya"]
    assert deducted_amounts == []
    assert service.last_stream_amount_cents == 0
    assert service.last_stream_usage["provider_code"] == "lingyaai"
    assert service.last_stream_usage["oneapi_request_id"] == "oneapi-stream-1"
    assert created_logs[0]["provider_code"] == "lingyaai"
    assert created_logs[0]["provider_request_id"] == "oneapi-stream-1"
    assert created_logs[0]["provider_trace_id"] == "trace-stream-1"
    assert created_logs[0]["params"]["streaming"] is True


@pytest.mark.asyncio
async def test_chat_stream_ollama_skips_balance_deduction_and_usage_logs(monkeypatch):
    billing_calls: list[tuple[str, int]] = []

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def deduct_balance(self, user_id, amount):
            billing_calls.append(("deduct", amount))
            return True

        async def refund_balance(self, user_id, amount):
            billing_calls.append(("refund", amount))

        async def create_usage_log(self, **kwargs):
            billing_calls.append(("usage_log", kwargs["amount_cents"]))
            return None

    class FakeOllamaClient:
        def __init__(self, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key
            self.last_stream_usage = {
                "prompt_tokens": 10,
                "completion_tokens": 5,
            }

        async def chat_completions_stream(self, **kwargs):
            yield "hello "
            yield "ollama"

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.OllamaClient", FakeOllamaClient)
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr("app.services.multimodal_service.settings.OLLAMA_API_KEY", "ollama")

    service = MultimodalService(db=object())

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            user_id=1,
            model_name="gemma4:e4b",
            provider_code="ollama",
            messages=[{"role": "user", "content": "hello"}],
            billing_label="billing.labels.image_analysis",
        )
    ]

    assert chunks == ["hello ", "ollama"]
    assert billing_calls == []
    assert service.last_stream_usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    assert service.last_stream_amount_cents == 0


@pytest.mark.asyncio
async def test_chat_stream_defaults_max_tokens_to_model_output_limit(monkeypatch):
    captured = {}

    class FakeBillingService:
        def __init__(self, db):
            self.db = db

        async def get_balance(self, user_id):
            return 100

        async def deduct_balance(self, user_id, amount):
            return True

        async def refund_balance(self, user_id, amount):
            return None

        def calculate_amount(self, model_name, input_tokens=None, output_tokens=None):
            return 0

        async def create_usage_log(self, **kwargs):
            return None

    class FakeApimartClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.last_stream_usage = {}

        async def chat_completions_stream(self, **kwargs):
            captured.update(kwargs)
            yield "hello"

    monkeypatch.setattr("app.services.multimodal_service.BillingService", FakeBillingService)
    monkeypatch.setattr("app.services.multimodal_service.ApimartClient", FakeApimartClient)
    monkeypatch.setattr("app.services.multimodal_service.settings.BUILTIN_PROVIDER_API_KEY", "test-key")

    service = MultimodalService(db=object())

    chunks = [
        chunk
        async for chunk in service.chat_stream(
            user_id=1,
            model_name="kimi-k2.5",
            provider_code="builtin",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=0,
        )
    ]

    assert chunks == ["hello"]
    assert captured["max_tokens"] == 98304
