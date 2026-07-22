from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status

from app.core.ollama_credentials import get_ollama_image_api_key
from app.core.media_capabilities import get_model_config
from app.core.ollama_image_config import resolve_ollama_image_size
from app.services.generation_media_resolver import resolve_generation_image_urls_with_diagnostics
from app.services.ollama_client import OllamaClient


def _supports_image_response_format(model_name: str) -> bool:
    normalized = str(model_name or "").strip().lower()
    return not normalized.startswith("gpt-image-")


def _provider_error(data: dict[str, Any]) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "调用 Ollama 图片生成失败")
    if error:
        return str(error)
    return str(data.get("message") or "调用 Ollama 图片生成失败")


def _provider_status_code(data: dict[str, Any]) -> int:
    try:
        status_code = int(data.get("_status_code") or status.HTTP_400_BAD_REQUEST)
    except (TypeError, ValueError):
        return status.HTTP_400_BAD_REQUEST
    if status_code < 400:
        return status.HTTP_400_BAD_REQUEST
    return status_code


def _resolve_reference_image_refs(
    image_urls: list[str],
    local_path_resolver: Callable[[str], str | None],
) -> list[str]:
    resolved: list[str] = []
    for url in image_urls:
        local_path = local_path_resolver(url)
        if local_path:
            resolved.append(local_path)
            continue
        if str(url or "").startswith(("http://", "https://", "data:")):
            resolved.append(url)
            continue
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="参考图路径无法解析",
        )
    return resolved


def _resolve_reference_image_urls_for_payload(
    image_urls: list[str],
    local_path_resolver: Callable[[str], str | None],
) -> tuple[list[str], dict[str, object]]:
    result = resolve_generation_image_urls_with_diagnostics(
        _resolve_reference_image_refs(image_urls, local_path_resolver)
    )
    return result.urls, result.diagnostics


def validate_ollama_image_generation_request(
    *,
    model_name: str,
    image_urls: list[str],
    local_path_resolver: Callable[[str], str | None],
) -> None:
    config = get_model_config("ollama", "text2image", model_name)
    if not image_urls:
        return
    if not config.get("supports_reference_image"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前 Ollama 图片模型未开启参考图能力",
        )
    max_refs = int(config.get("max_reference_images") or 0)
    if max_refs > 0 and len(image_urls) > max_refs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前 Ollama 图片模型最多支持 {max_refs} 张参考图",
        )
    if str(config.get("reference_mode") or "edits") != "edits":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前 Ollama 图片模型参考图模式不受支持",
        )
    _resolve_reference_image_refs(image_urls, local_path_resolver)


async def submit_ollama_image_generation(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    resolution: str,
    aspect_ratio: str,
    image_urls: list[str],
    local_path_resolver: Callable[[str], str | None],
) -> dict[str, Any]:
    config = get_model_config("ollama", "text2image", model_name)
    response_format = str(config.get("response_format") or "").strip() or None
    if not _supports_image_response_format(model_name):
        response_format = None
    quality = str(config.get("quality") or "").strip() or None
    size = resolve_ollama_image_size(resolution, aspect_ratio)

    validate_ollama_image_generation_request(
        model_name=model_name,
        image_urls=image_urls,
        local_path_resolver=local_path_resolver,
    )

    client = OllamaClient(base_url, api_key or get_ollama_image_api_key())
    reference_resolution_diagnostics: dict[str, object] | None = None
    if image_urls:
        image_refs, reference_resolution_diagnostics = _resolve_reference_image_urls_for_payload(
            image_urls,
            local_path_resolver,
        )
        result = await client.edit_image(
            model_name=model_name,
            prompt=prompt,
            image_refs=image_refs,
            size=size,
            response_format=response_format,
            quality=quality,
        )
    else:
        result = await client.generate_image(
            model_name=model_name,
            prompt=prompt,
            size=size,
            response_format=response_format,
            quality=quality,
        )

    if result.get("_status_code"):
        raise HTTPException(
            status_code=_provider_status_code(result),
            detail=_provider_error(result),
        )
    result_values = result.get("result_values") or []
    if not result_values:
        raise RuntimeError("Ollama image generation returned no images")
    result_id = str(result.get("id") or "").strip()
    return {
        "external_task_id": f"ollama-sync:{result_id}" if result_id else None,
        "result_values": result_values,
        "request_diagnostics": {
            "provider": "ollama",
            "operation": "image_submit",
            "model_name": model_name,
            "provider_payload_has_image": bool(image_urls),
            "provider_payload_image_count": len(image_urls or []),
            "reference_resolution": reference_resolution_diagnostics
            or {
                "input_count": 0,
                "output_url_count": 0,
                "remote_input_count": 0,
                "object_storage_upload_count": 0,
                "transport_counts": {"remote_url": 0, "object_storage_url": 0},
            },
        },
    }
