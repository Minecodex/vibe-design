from __future__ import annotations

from app.core.config import settings


def _clean_key(value: str | None) -> str:
    return str(value or "").strip()


def get_ollama_multimodal_api_key() -> str:
    return _clean_key(settings.OLLAMA_API_KEY) or "ollama"


def get_ollama_image_api_key() -> str:
    return _clean_key(settings.OLLAMA_IMAGE_API_KEY) or get_ollama_multimodal_api_key()
