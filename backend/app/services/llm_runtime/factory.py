from __future__ import annotations

from collections.abc import Callable

from app.core.config import settings
from app.core.ollama_credentials import get_ollama_multimodal_api_key
from app.services.builtin_provider import get_active_builtin_provider
from app.services.multimodal_service import resolve_multimodal_provider
from app.services.ollama_client import OllamaClient

from .apimart import ApimartLlmStreamClient
from .ollama import OllamaLlmStreamClient
from .types import LlmStreamClient


class LlmStreamClientFactory:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        multimodal_provider: str | None = None,
        registry: dict[str, Callable[[], LlmStreamClient]] | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.multimodal_provider = multimodal_provider
        self._registry = registry or self._default_registry()
        self._client_cache: dict[str, LlmStreamClient] = {}

    def client_for_model(self, model: str) -> LlmStreamClient:
        provider_code = resolve_multimodal_provider(model, self.multimodal_provider)
        builder = self._registry.get(provider_code)
        if builder is None:
            builder = self._registry.get("builtin")
            provider_code = "builtin"
        if builder is None:
            raise ValueError(f"No llm stream client registered for provider {provider_code}")
        client = self._client_cache.get(provider_code)
        if client is None:
            client = builder()
            self._client_cache[provider_code] = client
        return client

    def _default_registry(self) -> dict[str, Callable[[], LlmStreamClient]]:
        return {
            "builtin": lambda: ApimartLlmStreamClient(get_active_builtin_provider(self.api_key)),
            "ollama": lambda: OllamaLlmStreamClient(
                OllamaClient(
                    base_url=settings.OLLAMA_BASE_URL,
                    api_key=get_ollama_multimodal_api_key(),
                    tool_choice_format=settings.OLLAMA_TOOL_CHOICE_FORMAT,
                )
            ),
        }
