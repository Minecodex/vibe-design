from app.core.config import settings

DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_IMAGE_MODEL_LABEL = "NanoBanana2"
DEFAULT_MULTIMODAL_MODEL = "claude-opus-4-8"
DEFAULT_THINKING_MULTIMODAL_MODEL = "claude-opus-4-6-thinking"
FIXED_MARK_RECOGNITION_MODEL = "gemini-3.1-pro-preview"


def _configured_ollama_model() -> str | None:
    model_name = (settings.OLLAMA_MULTIMODAL_MODEL or "").strip()
    return model_name or None


def is_ollama_multimodal_enabled() -> bool:
    return bool(settings.OLLAMA_MULTIMODAL_ENABLED and _configured_ollama_model())


def is_ollama_image_analysis_enabled() -> bool:
    return bool(settings.OLLAMA_IMAGE_ANALYSIS_ENABLED and is_ollama_multimodal_enabled())


def get_ollama_image_generation_model() -> str | None:
    model_name = (settings.OLLAMA_IMAGE_GENERATION_MODEL or "").strip()
    if model_name:
        return model_name
    return _configured_ollama_model()


def is_ollama_image_generation_enabled() -> bool:
    return bool(settings.OLLAMA_IMAGE_GENERATION_ENABLED and get_ollama_image_generation_model())


def get_default_multimodal_provider() -> str:
    return "ollama" if is_ollama_multimodal_enabled() else "builtin"


def get_default_multimodal_model() -> str:
    return _configured_ollama_model() if is_ollama_multimodal_enabled() else DEFAULT_MULTIMODAL_MODEL


def get_default_thinking_multimodal_model() -> str:
    return _configured_ollama_model() if is_ollama_multimodal_enabled() else DEFAULT_THINKING_MULTIMODAL_MODEL


def get_default_image_analysis_model() -> str:
    return get_default_mark_recognition_model()


def get_default_image_analysis_provider() -> str:
    return get_default_mark_recognition_provider()


def get_default_mark_recognition_model() -> str:
    if is_ollama_image_analysis_enabled():
        return get_default_multimodal_model()
    return FIXED_MARK_RECOGNITION_MODEL


def get_default_mark_recognition_provider() -> str:
    if is_ollama_image_analysis_enabled():
        return get_default_multimodal_provider()
    return "builtin"
