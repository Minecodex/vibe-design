from __future__ import annotations

import asyncio
import base64
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from app.core.config import settings
from app.core.providers import (
    LINGYAAI_BUILTIN_MODELS,
    build_provider_registry,
    get_active_builtin_provider_code,
)
from app.services.apimart_client import ApimartClient
from app.services.generation_media_resolver import resolve_generation_image_urls_with_diagnostics
from app.services.generation_reference_diagnostics import summarize_reference_values


def calculate_lingyaai_amount_cents(*, quota: int, billing_unit_per_yuan: int) -> int:
    if billing_unit_per_yuan <= 0:
        raise ValueError("billing_unit_per_yuan must be positive")
    quota = max(int(quota or 0), 0)
    return max(1, math.ceil((quota / billing_unit_per_yuan) * 100))


@dataclass(slots=True)
class LingyaAiBillLookupResult:
    oneapi_request_id: str
    request_id: str | None
    quota: int
    prompt_tokens: int
    completion_tokens: int
    billing_unit_per_yuan: int
    amount_cents: int
    raw: dict[str, Any]

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any],
        *,
        billing_unit_per_yuan: int,
        oneapi_request_id: str,
        request_id: str | None = None,
    ) -> "LingyaAiBillLookupResult":
        quota = int(row.get("quota") or 0)
        return cls(
            oneapi_request_id=oneapi_request_id,
            request_id=request_id,
            quota=quota,
            prompt_tokens=int(row.get("prompt_tokens") or 0),
            completion_tokens=int(row.get("completion_tokens") or 0),
            billing_unit_per_yuan=billing_unit_per_yuan,
            amount_cents=calculate_lingyaai_amount_cents(
                quota=quota,
                billing_unit_per_yuan=billing_unit_per_yuan,
            ),
            raw=row,
        )

    @classmethod
    def from_rows(
        cls,
        *,
        primary_row: dict[str, Any] | None,
        task_rows: list[dict[str, Any]] | None = None,
        billing_unit_per_yuan: int,
        oneapi_request_id: str,
        request_id: str | None = None,
    ) -> "LingyaAiBillLookupResult":
        rows: list[dict[str, Any]] = []
        if primary_row:
            rows.append(primary_row)
        for row in task_rows or []:
            if row not in rows:
                rows.append(row)
        quota = sum(int(row.get("quota") or 0) for row in rows)
        prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in rows)
        completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in rows)
        raw: dict[str, Any]
        if primary_row and len(rows) == 1:
            raw = primary_row
        else:
            raw = {
                "primary": primary_row,
                "task_rows": task_rows or [],
                "rows": rows,
            }
        return cls(
            oneapi_request_id=oneapi_request_id,
            request_id=request_id,
            quota=quota,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            billing_unit_per_yuan=billing_unit_per_yuan,
            amount_cents=calculate_lingyaai_amount_cents(
                quota=quota,
                billing_unit_per_yuan=billing_unit_per_yuan,
            ),
            raw=raw,
        )


@dataclass(slots=True)
class BuiltinSubmitResult:
    status: str
    external_task_id: str | None = None
    result_urls: list[str] | None = None
    progress: int = 0
    error_message: str | None = None
    oneapi_request_id: str | None = None
    request_id: str | None = None
    raw: dict[str, Any] | None = None
    request_diagnostics: dict[str, Any] | None = None


@dataclass(slots=True)
class BuiltinQueryResult:
    status: str
    result_urls: list[str] | None = None
    progress: int | None = None
    error_message: str | None = None
    oneapi_request_id: str | None = None
    request_id: str | None = None
    raw: dict[str, Any] | None = None


class BuiltinProviderBase:
    code: str

    async def submit_image(self, **kwargs: Any) -> BuiltinSubmitResult:
        raise NotImplementedError

    async def submit_video(self, **kwargs: Any) -> BuiltinSubmitResult:
        raise NotImplementedError

    async def query_generation(self, external_task_id: str, *, task_type: str, model_name: str) -> BuiltinQueryResult:
        raise NotImplementedError

    async def chat_completions(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def chat_completions_stream(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        raise NotImplementedError
        yield {}

    async def lookup_bill(
        self,
        oneapi_request_id: str,
        request_id: str | None = None,
        task_id: str | None = None,
    ) -> LingyaAiBillLookupResult | None:
        return None

    async def fetch_recent_bill_rows(self) -> list[dict[str, Any]]:
        return []

    async def fetch_provider_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    def match_bill_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        provider_request_id: str,
        provider_trace_id: str | None = None,
        provider_task_id: str | None = None,
    ) -> LingyaAiBillLookupResult | None:
        return None


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bill_row_task_id(row: dict[str, Any]) -> str | None:
    other = _parse_json_object(row.get("other"))
    task_id = other.get("task_id")
    if task_id is None:
        return None
    text = str(task_id).strip()
    return text or None


def match_lingyaai_bill_rows(
    rows: list[dict[str, Any]],
    *,
    provider_request_id: str,
    provider_trace_id: str | None = None,
    provider_task_id: str | None = None,
    billing_unit_per_yuan: int,
) -> LingyaAiBillLookupResult | None:
    primary_row: dict[str, Any] | None = None
    task_rows: list[dict[str, Any]] = []
    trace_request_id = str(provider_trace_id or "").strip()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("request_id") == provider_request_id and primary_row is None:
            primary_row = row
        elif trace_request_id and row.get("request_id") == trace_request_id and primary_row is None:
            primary_row = row
        if provider_task_id and _bill_row_task_id(row) == provider_task_id:
            task_rows.append(row)
    if not primary_row:
        return None
    return LingyaAiBillLookupResult.from_rows(
        primary_row=primary_row,
        task_rows=task_rows,
        billing_unit_per_yuan=billing_unit_per_yuan,
        oneapi_request_id=provider_request_id,
        request_id=provider_trace_id,
    )


def _extract_task_id(result: dict[str, Any]) -> str | None:
    data = result.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("task_id") or first.get("id")
    if isinstance(data, dict):
        return data.get("task_id") or data.get("id")
    return result.get("task_id") or result.get("id")


def _extract_urls_from_openai_images(data: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            urls.append(str(item["url"]))
        elif item.get("b64_json"):
            urls.append(f"data:image/png;base64,{item['b64_json']}")
    return urls


def _extract_apimart_result_urls(data: dict[str, Any]) -> list[str]:
    from app.services.provider_result_urls import extract_task_result_urls

    urls = extract_task_result_urls(data)
    if urls:
        return urls
    result = data.get("result", data)
    raw_urls = result.get("result_urls", []) if isinstance(result, dict) else []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    if isinstance(raw_urls, list):
        return [url for url in raw_urls if isinstance(url, str) and url]
    return []


def _model_config(bucket: str, model_name: str) -> dict[str, Any]:
    for entry in build_provider_registry()["builtin"]["models"].get(bucket, []):
        if entry.get("model_name") == model_name:
            return dict(entry.get("config") or {})
    return {}


def _lingyaai_model_config(bucket: str, model_name: str) -> dict[str, Any]:
    for entry in LINGYAAI_BUILTIN_MODELS.get(bucket, []):
        if entry.get("model_name") == model_name:
            return dict(entry.get("config") or {})
    return {}


class ApimartBuiltinProvider(BuiltinProviderBase):
    code = "apimart"

    def __init__(self, api_key: str):
        self.client = ApimartClient(api_key)

    async def submit_image(self, **kwargs: Any) -> BuiltinSubmitResult:
        result = await self.client.generate_image(
            prompt=kwargs["prompt"],
            model_name=kwargs["model_name"],
            resolution=kwargs.get("resolution") or "1K",
            aspect_ratio=kwargs.get("aspect_ratio") or "1:1",
            urls=kwargs.get("image_urls"),
            image_count=kwargs.get("image_count") or 1,
        )
        request_diagnostics = result.pop("_request_diagnostics", None) if isinstance(result, dict) else None
        if result.get("code") != 200:
            error = result.get("error") if isinstance(result.get("error"), dict) else {}
            return BuiltinSubmitResult(
                status="failed",
                error_message=error.get("message") or result.get("msg") or "Unknown error",
                raw=result,
                request_diagnostics=request_diagnostics,
            )
        return BuiltinSubmitResult(
            status="processing",
            external_task_id=_extract_task_id(result),
            raw=result,
            request_diagnostics=request_diagnostics,
        )

    async def submit_video(self, **kwargs: Any) -> BuiltinSubmitResult:
        result = await self.client.generate_video(
            prompt=kwargs.get("prompt"),
            model_name=kwargs["model_name"],
            aspect_ratio=kwargs.get("aspect_ratio") or "16:9",
            duration=kwargs.get("duration") or 5,
            quality=kwargs.get("quality"),
            resolution=kwargs.get("resolution"),
            audio=bool(kwargs.get("audio")),
            urls=kwargs.get("image_urls"),
            reference_image_urls=kwargs.get("reference_image_urls"),
            first_frame_url=kwargs.get("first_frame_image"),
            tail_frame_url=kwargs.get("tail_frame_image"),
            return_last_frame=kwargs.get("return_last_frame"),
            negative_prompt=kwargs.get("negative_prompt"),
            watermark=kwargs.get("watermark"),
            multi_shot=kwargs.get("multi_shot"),
            shot_type=kwargs.get("shot_type"),
            multi_prompt=kwargs.get("multi_prompt"),
            element_list=kwargs.get("element_list"),
        )
        if result.get("code") != 200:
            error = result.get("error") if isinstance(result.get("error"), dict) else {}
            return BuiltinSubmitResult(
                status="failed",
                error_message=error.get("message") or result.get("msg") or "Unknown error",
                raw=result,
            )
        return BuiltinSubmitResult(
            status="processing",
            external_task_id=_extract_task_id(result),
            raw=result,
        )

    async def query_generation(self, external_task_id: str, *, task_type: str, model_name: str) -> BuiltinQueryResult:
        result = await self.client.query_result(external_task_id)
        if "error" in result:
            return BuiltinQueryResult(status="processing", raw=result)
        if result.get("code") != 200:
            return BuiltinQueryResult(status="processing", raw=result)

        data = result.get("data", {})
        if isinstance(data, list):
            data = data[0] if data else {}
        status_value = str((data or {}).get("status") or "").lower()
        if status_value == "completed":
            return BuiltinQueryResult(
                status="completed",
                result_urls=_extract_apimart_result_urls(data),
                progress=100,
                raw=result,
            )
        if status_value == "failed":
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            return BuiltinQueryResult(
                status="failed",
                error_message=error.get("message") or data.get("error_message") or "生成失败",
                raw=result,
            )
        return BuiltinQueryResult(status="processing", progress=_parse_progress(data.get("progress")), raw=result)

    async def chat_completions(self, **kwargs: Any) -> dict[str, Any]:
        return await self.client.chat_completions(**kwargs)

    async def chat_completions_stream(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self.client.stream_chat_completions_events_raw(**kwargs):
            yield event

    async def stream_chat_completions_events_raw(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self.client.stream_chat_completions_events_raw(**kwargs):
            yield event

    async def fetch_provider_balance(self) -> dict[str, Any]:
        return await self.client.get_balance()


def _parse_progress(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().rstrip("%")
    try:
        return max(0, min(100, int(float(text))))
    except ValueError:
        return None


class LingyaAiBuiltinProvider(BuiltinProviderBase):
    code = "lingyaai"
    DEFAULT_BASE_URL = "https://lyapi.com"

    def __init__(self, api_key: str, *, billing_unit_per_yuan: int | None = None):
        self.api_key = str(api_key or "").strip()
        self.billing_unit_per_yuan = billing_unit_per_yuan or settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN
        self.last_stream_usage: dict[str, Any] | None = None
        self.last_stream_provider_headers: dict[str, str | None] = {}

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("APIMart API key is required for provider requests")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def base_url(self) -> str:
        return str(settings.LINGYAAI_BASE_URL or self.DEFAULT_BASE_URL).rstrip("/")

    @staticmethod
    def _should_omit_temperature(model_name: str) -> bool:
        profile = _lingyaai_model_config("multimodal", model_name)
        return bool(profile.get("request_profile") == "lingyaai_chat" and profile.get("omit_temperature"))

    def _build_chat_payload(
        self,
        *,
        model_name: str,
        messages: list[dict[str, Any]],
        temperature: float,
        stream: bool,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
        }
        if not self._should_omit_temperature(model_name):
            payload["temperature"] = temperature
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        return payload

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=timeout or settings.APIMART_TIMEOUT_SECONDS) as client:
            if method == "GET":
                response = await client.get(f"{self.base_url}{path}", headers=headers)
            else:
                response = await client.post(f"{self.base_url}{path}", headers=headers, json=json_data)
        if response.status_code >= 400:
            try:
                data = response.json()
            except Exception:
                data = {"error": {"message": response.text}}
            data["_status_code"] = response.status_code
            return data, response.headers
        return response.json(), response.headers

    async def submit_image(self, **kwargs: Any) -> BuiltinSubmitResult:
        profile = (
            _lingyaai_model_config("text2image", kwargs["model_name"]).get("request_profile")
            or _model_config("text2image", kwargs["model_name"]).get("request_profile")
        )
        payload: dict[str, Any] = {
            "model": kwargs["model_name"],
            "prompt": kwargs["prompt"],
            "response_format": "url",
        }
        aspect_ratio = kwargs.get("aspect_ratio") or "1:1"
        resolution = kwargs.get("resolution") or "1K"
        original_image_urls = [url for url in (kwargs.get("image_urls") or []) if url]
        # Resolving local references uploads them to object storage (blocking network I/O);
        # offload to a worker thread so the shared event loop is not stalled.
        resolution_result = await asyncio.to_thread(
            resolve_generation_image_urls_with_diagnostics, original_image_urls
        )
        image_urls = resolution_result.urls
        if profile in {"lingyaai_nano_banana_image", "lingyaai_gpt_image"}:
            payload["aspect_ratio"] = aspect_ratio
            if image_urls:
                payload["image"] = image_urls
            if profile == "lingyaai_nano_banana_image":
                payload["image_size"] = resolution
            else:
                payload["resolution"] = resolution
        elif profile == "lingyaai_seedream_image":
            payload["size"] = resolution
            if image_urls:
                payload["image"] = image_urls
        else:
            payload["aspect_ratio"] = aspect_ratio
            if image_urls:
                payload["image"] = image_urls

        request_diagnostics = {
            "provider": "lingyaai",
            "operation": "image_submit",
            "model_name": kwargs["model_name"],
            "request_profile": profile or None,
            "reference_inputs": summarize_reference_values(original_image_urls),
            "provider_payload_has_image": bool(payload.get("image")),
            "provider_payload_image_count": len(payload.get("image") or []),
            "provider_payload_images": summarize_reference_values(payload.get("image") or []),
            "reference_resolution": resolution_result.diagnostics,
        }
        data, headers = await self._request("POST", "/v1/images/generations", json_data=payload, timeout=500)
        oneapi_request_id = headers.get("X-Oneapi-Request-Id")
        request_id = headers.get("X-Request-Id") or data.get("id")
        if data.get("_status_code"):
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            return BuiltinSubmitResult(
                status="failed",
                external_task_id=None,
                error_message=error.get("message") or data.get("message") or "调用 LingyaAI 图片生成失败",
                oneapi_request_id=oneapi_request_id,
                request_id=request_id,
                raw=data,
                request_diagnostics=request_diagnostics,
            )
        return BuiltinSubmitResult(
            status="completed",
            external_task_id=None,
            result_urls=_extract_urls_from_openai_images(data),
            progress=100,
            oneapi_request_id=oneapi_request_id,
            request_id=request_id,
            raw=data,
            request_diagnostics=request_diagnostics,
        )

    async def submit_video(self, **kwargs: Any) -> BuiltinSubmitResult:
        payload = self._build_video_payload(**kwargs)
        request_diagnostics = self._video_request_diagnostics(kwargs, payload)
        data, headers = await self._request("POST", "/v1/videos", json_data=payload, timeout=500)
        oneapi_request_id = headers.get("X-Oneapi-Request-Id")
        request_id = headers.get("X-Request-Id")
        external_id = data.get("id")
        status = "processing" if external_id else "failed"
        return BuiltinSubmitResult(
            status=status,
            external_task_id=external_id,
            oneapi_request_id=oneapi_request_id,
            request_id=request_id,
            raw=data,
            request_diagnostics=request_diagnostics,
        )

    @staticmethod
    def _video_request_diagnostics(kwargs: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        model_name = str(kwargs.get("model_name") or "")
        profile = (
            _lingyaai_model_config("text2video", model_name).get("request_profile")
            or _model_config("text2video", model_name).get("request_profile")
        )
        input_images = [
            value
            for value in [
                kwargs.get("first_frame_image"),
                kwargs.get("tail_frame_image"),
                *(kwargs.get("image_urls") or kwargs.get("reference_image_urls") or []),
            ]
            if value
        ]
        payload_images: list[str] = []
        for item in payload.get("content") or []:
            if isinstance(item, dict):
                image_url = item.get("image_url")
                if isinstance(image_url, dict) and image_url.get("url"):
                    payload_images.append(str(image_url["url"]))
        for item in payload.get("images") or []:
            if item:
                payload_images.append(str(item))
        for item in payload.get("media") or []:
            if isinstance(item, dict) and item.get("url"):
                payload_images.append(str(item["url"]))
        input_payload = payload.get("input")
        if isinstance(input_payload, dict):
            for item in input_payload.get("images") or []:
                if item:
                    payload_images.append(str(item))
        return {
            "provider": "lingyaai",
            "operation": "video_submit",
            "model_name": model_name,
            "request_profile": profile or None,
            "reference_inputs": summarize_reference_values(input_images),
            "provider_payload_has_image": bool(payload_images),
            "provider_payload_image_count": len(payload_images),
            "provider_payload_images": summarize_reference_values(payload_images),
        }

    def _build_video_payload(self, **kwargs: Any) -> dict[str, Any]:
        model_name = kwargs["model_name"]
        profile = (
            _lingyaai_model_config("text2video", model_name).get("request_profile")
            or _model_config("text2video", model_name).get("request_profile")
        )
        prompt = kwargs.get("prompt") or ""
        resolution = kwargs.get("resolution") or kwargs.get("quality") or "720p"
        duration = kwargs.get("duration") or 5
        aspect_ratio = kwargs.get("aspect_ratio") or "16:9"
        first_frame = _video_ref_to_public_url(kwargs.get("first_frame_image"))
        tail_frame = _video_ref_to_public_url(kwargs.get("tail_frame_image"))
        reference_images = [_video_ref_to_public_url(url) for url in (kwargs.get("image_urls") or kwargs.get("reference_image_urls") or []) if url]
        reference_images = [url for url in reference_images if url]

        if profile == "lingyaai_seedance2_video":
            content: list[dict[str, Any]] = []
            if prompt:
                content.append({"type": "text", "text": prompt})
            image_entries: list[tuple[str, str]] = []
            if first_frame:
                image_entries.append((first_frame, "first_frame"))
            if tail_frame:
                image_entries.append((tail_frame, "last_frame"))
            if not image_entries:
                image_entries.extend((url, "reference_image") for url in reference_images)
            for url, role in image_entries:
                content.append({"type": "image_url", "image_url": {"url": url}, "role": role})
            return {
                "model": model_name,
                "content": content,
                "resolution": resolution,
                "ratio": aspect_ratio,
                "duration": duration,
                "generate_audio": bool(kwargs.get("audio")),
                "watermark": bool(kwargs.get("watermark", False)),
                "return_last_frame": bool(kwargs.get("return_last_frame", False)),
            }

        if profile == "lingyaai_seedance15_video":
            images = [url for url in [first_frame, tail_frame] if url] or reference_images[:2]
            payload: dict[str, Any] = {
                "model": model_name,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "duration": duration,
                "watermark": bool(kwargs.get("watermark", False)),
            }
            if images:
                payload["images"] = images
            return payload

        media = []
        if first_frame:
            media.append({"type": "first_frame", "url": first_frame})
        if tail_frame:
            media.append({"type": "last_frame", "url": tail_frame})
        if not media:
            media.extend({"type": "first_frame", "url": url} for url in reference_images[:1])
        return {
            "model": model_name,
            "input": {
                "prompt": prompt,
                "media": media,
                "multi_shot": bool(kwargs.get("multi_shot", False)),
                "shot_type": kwargs.get("shot_type"),
                "multi_prompt": kwargs.get("multi_prompt") or [],
            },
            "parameters": {
                "mode": "pro" if str(resolution).lower().startswith("1080") else "std",
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "audio": bool(kwargs.get("audio")),
                "watermark": bool(kwargs.get("watermark", False)),
            },
        }

    async def query_generation(self, external_task_id: str, *, task_type: str, model_name: str) -> BuiltinQueryResult:
        data, headers = await self._request("GET", f"/v1/videos/{external_task_id}", timeout=60)
        status_value = str(data.get("status") or "").lower()
        oneapi_request_id = headers.get("X-Oneapi-Request-Id")
        request_id = headers.get("X-Request-Id")
        if status_value == "completed":
            urls = [url for url in [data.get("video_url"), data.get("watermark_video_url")] if isinstance(url, str) and url]
            return BuiltinQueryResult(
                status="completed",
                result_urls=urls,
                progress=100,
                oneapi_request_id=oneapi_request_id,
                request_id=request_id,
                raw=data,
            )
        if status_value == "failed":
            return BuiltinQueryResult(
                status="failed",
                error_message=data.get("message") or data.get("code") or "生成失败",
                oneapi_request_id=oneapi_request_id,
                request_id=request_id,
                raw=data,
            )
        return BuiltinQueryResult(
            status="processing",
            progress=_parse_progress(data.get("progress")),
            oneapi_request_id=oneapi_request_id,
            request_id=request_id,
            raw=data,
        )

    async def chat_completions(self, **kwargs: Any) -> dict[str, Any]:
        payload = self._build_chat_payload(
            model_name=kwargs["model_name"],
            messages=kwargs["messages"],
            temperature=float(kwargs.get("temperature", 1.0)),
            stream=False,
            max_tokens=int(kwargs.get("max_tokens") or 0),
            tools=kwargs.get("tools"),
        )
        data, headers = await self._request("POST", "/v1/chat/completions", json_data=payload, timeout=500)
        data["_provider_headers"] = {
            "x_oneapi_request_id": headers.get("X-Oneapi-Request-Id"),
            "x_request_id": headers.get("X-Request-Id"),
        }
        return data

    async def chat_completions_stream(self, **kwargs: Any) -> AsyncGenerator[str, None]:
        async for event in self.stream_chat_completions_events_raw(**kwargs):
            choices = event.get("choices", []) if isinstance(event, dict) else []
            if not choices:
                continue
            delta = choices[0].get("delta", {}) or {}
            text = delta.get("content", "")
            if text:
                yield text

    async def stream_chat_completions_events_raw(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        payload = self._build_chat_payload(
            model_name=kwargs["model_name"],
            messages=kwargs["messages"],
            temperature=float(kwargs.get("temperature", 1.0)),
            stream=True,
            max_tokens=int(kwargs.get("max_tokens") or 0),
            tools=kwargs.get("tools"),
        )
        headers = self._auth_headers()
        self.last_stream_usage = None
        self.last_stream_provider_headers = {}
        async with httpx.AsyncClient(timeout=ApimartClient._build_stream_timeout(None)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                self.last_stream_provider_headers = {
                    "x_oneapi_request_id": resp.headers.get("X-Oneapi-Request-Id"),
                    "x_request_id": resp.headers.get("X-Request-Id"),
                }
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(body.decode(errors="replace"))
                async for line in resp.aiter_lines():
                    raw = ApimartClient._extract_sse_data_payload(line)
                    if raw is None or raw == "[DONE]":
                        continue
                    try:
                        event = httpx.Response(200, content=raw).json()
                    except Exception:
                        continue
                    usage = event.get("usage") if isinstance(event, dict) else None
                    if isinstance(usage, dict) and usage:
                        self.last_stream_usage = usage
                    yield event

    async def lookup_bill(
        self,
        oneapi_request_id: str,
        request_id: str | None = None,
        task_id: str | None = None,
    ) -> LingyaAiBillLookupResult | None:
        for attempt in range(3):
            bill = self.match_bill_from_rows(
                await self.fetch_recent_bill_rows(),
                provider_request_id=oneapi_request_id,
                provider_trace_id=request_id,
                provider_task_id=task_id,
            )
            if bill is not None:
                return bill
            if attempt < 2:
                await asyncio.sleep(1)
        return None

    async def fetch_recent_bill_rows(self) -> list[dict[str, Any]]:
        data, _headers = await self._request("GET", "/api/log/token", timeout=30)
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    async def fetch_provider_balance(self) -> dict[str, Any]:
        data, _headers = await self._request("GET", "/api/usage/token/", timeout=30)
        return data

    def match_bill_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        provider_request_id: str,
        provider_trace_id: str | None = None,
        provider_task_id: str | None = None,
    ) -> LingyaAiBillLookupResult | None:
        return match_lingyaai_bill_rows(
            rows,
            provider_request_id=provider_request_id,
            provider_trace_id=provider_trace_id,
            provider_task_id=provider_task_id,
            billing_unit_per_yuan=self.billing_unit_per_yuan,
        )


def _video_ref_to_public_url(url: str | None) -> str | None:
    if not url:
        return None
    return ApimartClient("")._local_url_to_absolute(url)


def _local_url_to_file_path(url: str) -> str | None:
    if not url or url.startswith(("http://", "https://", "data:")):
        return None

    normalized = url.replace("\\", "/")
    if normalized.startswith(("/api/v1/uploads/", "api/v1/uploads/", "/uploads/", "uploads/")):
        relative_path = normalized.split("/v1/")[-1] if "/v1/" in normalized else normalized.lstrip("/")
        file_path = Path(os.getcwd()) / relative_path
        return str(file_path) if file_path.exists() and file_path.is_file() else None

    candidate = Path(url)
    if candidate.is_absolute():
        return _safe_existing_upload_file(candidate)

    if "/uploads/" not in normalized:
        return None

    relative_path = normalized.split("/v1/")[-1] if "/v1/" in normalized else normalized.lstrip("/")
    file_path = Path(os.getcwd()) / relative_path
    return str(file_path) if file_path.exists() and file_path.is_file() else None


def _safe_existing_upload_file(path: Path) -> str | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None

    harness_root = Path(getattr(settings, "HARNESS_WORKSPACE_ROOT", "workspace")).resolve()
    allowed_roots = [
        Path("uploads").resolve(),
        harness_root,
    ]
    if harness_root.name == "harness" and harness_root.parent.name == "uploads":
        allowed_roots.append(harness_root.parent.resolve())

    if (
        resolved.exists()
        and resolved.is_file()
        and any(_is_within_path(resolved, root) for root in allowed_roots)
    ):
        return str(resolved)
    return None


def _is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def get_builtin_provider(provider_code: str, api_key: str | None = None) -> BuiltinProviderBase:
    resolved_api_key = str(api_key or "").strip()
    if provider_code == "lingyaai":
        return LingyaAiBuiltinProvider(
            resolved_api_key,
            billing_unit_per_yuan=settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN,
        )
    return ApimartBuiltinProvider(resolved_api_key)


def get_active_builtin_provider(api_key: str | None = None) -> BuiltinProviderBase:
    return get_builtin_provider(get_active_builtin_provider_code(), api_key)
