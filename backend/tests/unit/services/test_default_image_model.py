from app.core.default_models import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_MODEL_LABEL
from app.services.apimart_client import ApimartClient


def test_default_image_model_is_nano_banana2():
    assert DEFAULT_IMAGE_MODEL == "gemini-3.1-flash-image-preview-official"
    assert DEFAULT_IMAGE_MODEL_LABEL == "NanoBanana2"


def test_apimart_client_uses_default_image_model():
    client = ApimartClient("test-key")
    assert client.generate_image.__defaults__[0] == DEFAULT_IMAGE_MODEL
