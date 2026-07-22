from __future__ import annotations

from app.core.providers import build_provider_registry


def resolve_model_label(
    model_name: str | None,
    *,
    provider_code: str | None = None,
    bucket: str | None = None,
) -> str:
    if not model_name:
        return ""

    registry = build_provider_registry()
    providers_to_check: list[dict] = []
    if provider_code and provider_code in registry:
        providers_to_check.append(registry[provider_code])
    providers_to_check.extend(
        provider
        for code, provider in registry.items()
        if code != provider_code
    )

    bucket_names = [bucket] if bucket else ["text2image", "text2video", "multimodal"]

    for provider in providers_to_check:
        models = provider.get("models", {})
        for bucket_name in bucket_names:
            for model in models.get(bucket_name, []):
                if model.get("model_name") == model_name:
                    return str(model.get("label") or model_name)

    return str(model_name)
