from app.core.providers import PROVIDER_REGISTRY
from app.services.multimodal_service import MULTIMODAL_MODELS


def test_multimodal_service_models_match_builtin_provider_registry():
    builtin_models = {
        entry["model_name"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert MULTIMODAL_MODELS == builtin_models
