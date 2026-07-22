"""APIMart API client — communicates with api.apimart.ai.

Supports:
- text2image / image2image (async submit)
- text2video / image2video (async submit)
- query status

Auth: API Key passed as Bearer Token in headers.
Base URL: https://api.apimart.ai
"""

import asyncio
import json as json_module
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx

from app.core.config import (
    APIMART_CONNECT_TIMEOUT_SECONDS,
    APIMART_POOL_TIMEOUT_SECONDS,
    APIMART_WRITE_TIMEOUT_SECONDS,
    settings,
)
from app.core.default_models import DEFAULT_IMAGE_MODEL
from app.core.providers import get_builtin_multimodal_model_entry
from app.services.generation_media_resolver import resolve_generation_image_urls_with_diagnostics

logger = logging.getLogger(__name__)


class ApimartStreamError(Exception):
    def __init__(self, *, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ApimartClient:
    BASE_URL = "https://api.apimart.ai"

    def __init__(self, api_key: str):
        self.api_key = str(api_key or "").strip()
        self.last_stream_usage: dict[str, Any] | None = None

    def _auth_headers(self, *, anthropic_version: bool = False) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("APIMart API key is required for requests")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if anthropic_version:
            headers["anthropic-version"] = "2025-10-01"
        return headers

    @staticmethod
    def _apply_positive_limit(payload: dict[str, Any], key: str, value: int | None) -> None:
        """Only include token limits when explicitly set to a positive value."""
        if value is not None and value > 0:
            payload[key] = value

    @staticmethod
    def _resolve_multimodal_max_tokens(model_name: str, max_tokens: int) -> int:
        if max_tokens > 0:
            return max_tokens
        entry = get_builtin_multimodal_model_entry(model_name)
        if not entry:
            return max_tokens
        config = entry.get("config") or {}
        configured_limit = int(config.get("max_output_tokens") or 0)
        return configured_limit if configured_limit > 0 else max_tokens

    @staticmethod
    def _uses_video_size_field(model_name: str) -> bool:
        normalized = model_name.lower()
        return (
            normalized.startswith("doubao-seedance-2.0")
            or normalized == "grok-imagine-1.0-video-apimart"
        )

    @staticmethod
    def _uses_video_quality_field(model_name: str) -> bool:
        return model_name.lower() == "grok-imagine-1.0-video-apimart"

    @staticmethod
    def _uses_video_generate_audio_flag(model_name: str) -> bool:
        return model_name.lower().startswith("doubao-seedance-2.0")

    @staticmethod
    def _uses_video_image_with_roles(model_name: str) -> bool:
        return model_name.lower().startswith("doubao-seedance-")

    @staticmethod
    def _uses_image_resolution_field(model_name: str) -> bool:
        return model_name.lower() != "imagen-4.0-apimart"

    @staticmethod
    def _normalize_image_resolution(model_name: str, resolution: str) -> str:
        if model_name.lower() == "gpt-image-2":
            return resolution.lower()
        return resolution

    @staticmethod
    def _extract_sse_data_payload(line: str) -> str | None:
        stripped = (line or "").strip()
        if not stripped.startswith("data:"):
            return None
        return stripped[5:].lstrip()

    @staticmethod
    def _build_stream_timeout(timeout_profile: Any | None = None) -> float | httpx.Timeout:
        if timeout_profile is None:
            return 500
        connect_seconds = float(getattr(timeout_profile, "connect_seconds", APIMART_CONNECT_TIMEOUT_SECONDS))
        read_seconds = float(getattr(timeout_profile, "read_seconds", settings.APIMART_TIMEOUT_SECONDS))
        write_seconds = float(
            getattr(
                timeout_profile,
                "write_seconds",
                APIMART_WRITE_TIMEOUT_SECONDS,
            )
        )
        pool_seconds = float(getattr(timeout_profile, "pool_seconds", APIMART_POOL_TIMEOUT_SECONDS))
        return httpx.Timeout(
            read_seconds,
            connect=connect_seconds,
            read=read_seconds,
            write=write_seconds,
            pool=pool_seconds,
        )

    async def _request(
        self, method: str, path: str, params: dict | None = None,
        json_data: dict | None = None, timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        headers = self._auth_headers(anthropic_version=True)
        request_timeout = httpx.Timeout(
            timeout if timeout is not None else settings.APIMART_TIMEOUT_SECONDS,
            connect=APIMART_CONNECT_TIMEOUT_SECONDS,
            read=timeout if timeout is not None else settings.APIMART_TIMEOUT_SECONDS,
            write=APIMART_WRITE_TIMEOUT_SECONDS,
            pool=APIMART_POOL_TIMEOUT_SECONDS,
        )

        async with httpx.AsyncClient(timeout=request_timeout) as client:
            if method == "GET":
                resp = await client.get(url, params=params, headers=headers)
            else:
                logger.debug(f"Apimart POST {path}, JSON payload keys: {json_data.keys() if json_data else None}")
                resp = await client.post(url, json=json_data, headers=headers)

            body_text = resp.text
            if resp.status_code != 200:
                logger.error("Apimart API error: status=%s, path=%s", resp.status_code, path)
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        data["_status_code"] = resp.status_code
                    return data
                except Exception:
                    return {"code": resp.status_code, "msg": body_text, "_status_code": resp.status_code}
            if not body_text.strip():
                logger.error(f"Apimart API returned empty body: status={resp.status_code}, path={path}")
                return {"error": {"message": "API returned empty response"}, "_status_code": 502}
            try:
                return resp.json()
            except Exception:
                logger.error("Apimart API returned non-JSON body: path=%s", path)
                return {"error": {"message": f"API returned non-JSON response: {body_text[:200]}"}, "_status_code": 502}

    async def get_balance(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/balance", timeout=30)

    @staticmethod
    def _is_within_path(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def _allowed_local_upload_file(path: Path) -> str | None:
        uploads_root = (Path(os.getcwd()) / "uploads").resolve()
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if not ApimartClient._is_within_path(resolved, uploads_root):
            return None
        return str(resolved) if resolved.exists() and resolved.is_file() else None

    @staticmethod
    def _local_url_to_file_path(url: str) -> str | None:
        if not url or url.startswith("http") or url.startswith("data:"):
            return None
        normalized = url.replace("\\", "/")
        if "/uploads/" not in normalized and not normalized.startswith("uploads/"):
            return None
        if normalized.startswith(("/api/v1/uploads/", "api/v1/uploads/", "/uploads/", "uploads/")):
            relative_path = normalized.split("/v1/")[-1] if "/v1/" in normalized else normalized.lstrip("/")
            return ApimartClient._allowed_local_upload_file(Path(os.getcwd()) / relative_path)

        raw_path = Path(normalized)
        if raw_path.is_absolute():
            return ApimartClient._allowed_local_upload_file(raw_path)

        return None

    @staticmethod
    def _file_mime_type(file_path: str) -> str:
        ext = file_path.split(".")[-1].lower()
        if ext in ["jpg", "jpeg"]:
            return "image/jpeg"
        if ext == "png":
            return "image/png"
        if ext == "webp":
            return "image/webp"
        return f"image/{ext}"

    def _upload_local_url_to_public_url(self, url: str) -> str | None:
        """Upload a local upload URL to TOS and return a public URL when configured."""
        file_path = self._local_url_to_file_path(url)
        if not file_path:
            return None

        ak = settings.TOS_AK
        sk = settings.TOS_SK
        endpoint = settings.TOS_ENDPOINT
        region = settings.TOS_REGION
        bucket_name = settings.TOS_BUCKET_NAME

        if not (ak and sk and endpoint and bucket_name):
            return None

        try:
            import hashlib

            import tos

            client = tos.TosClientV2(ak, sk, endpoint, region)
            ext = os.path.splitext(file_path)[1]
            # Key by content digest (not a random UUID) so repeated generations / retries of
            # the same reference map to one stable object instead of accumulating unbounded
            # duplicates in the bucket (mirrors the generation media resolver).
            digest = hashlib.sha256()
            with open(file_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            object_key = f"{digest.hexdigest()}{ext}"
            client.put_object_from_file(bucket_name, object_key, file_path)
            public_url = f"https://{bucket_name}.{endpoint}/{object_key}"
            logger.info(f"Successfully uploaded {file_path} to TOS: {public_url}")
            return public_url
        except Exception as e:
            logger.error(f"Failed to upload {file_path} to TOS: {e}")
            return None

    def _local_url_to_absolute(self, url: str) -> str:
        """Convert a local URI to absolute path if needed, though for video image_urls it's better if it's external.
        Assuming the frontend passes valid accessible URLs or base64.
        For now we just pass it as is for video if it's a URL."""
        if not url or url.startswith("http") or url.startswith("data:"):
            return url

        # intercept local upload formats like /api/v1/uploads/canvas/2/8e8937b2-d372-43c5.jpg or /uploads/
        if "/uploads/" in url:
            public_url = self._upload_local_url_to_public_url(url)
            if public_url:
                return public_url
            # The reference is a local path the remote provider cannot fetch. Object
            # storage is unconfigured or the upload failed; surface it instead of silently
            # forwarding an inaccessible path that would fail opaquely downstream.
            logger.warning(
                "Local reference could not be published to object storage; provider may be "
                "unable to fetch it: file=%s",
                url.rsplit("/", 1)[-1],
            )

        return url

    async def _resolve_local_reference_urls_off_loop(
        self, urls: "list[str | None]"
    ) -> dict[str, str]:
        """Resolve reference URLs to provider-accessible URLs without blocking the loop.

        ``_local_url_to_absolute`` uploads local ``/uploads/`` references to object storage
        (blocking network I/O). Running it inline would stall the worker's shared event loop
        and every concurrent agent run / SSE stream on it, so the whole unique batch is
        offloaded to a worker thread (mirrors the generate_image reference fix).
        """
        unique = list(dict.fromkeys(url for url in urls if url))
        if not unique:
            return {}
        return await asyncio.to_thread(self._resolve_local_reference_urls, unique)

    def _resolve_local_reference_urls(self, urls: list[str]) -> dict[str, str]:
        return {url: self._local_url_to_absolute(url) for url in urls}

    # ===================== Image Generation =====================

    async def generate_image(
        self,
        prompt: str,
        model_name: str = DEFAULT_IMAGE_MODEL,
        resolution: str = "1K",
        aspect_ratio: str = "1:1",
        urls: list[str] | None = None,
        mask_url: str | None = None,
        image_count: int = 1,
    ) -> dict:
        """Submit an async image generation task.
        In APIMart, aspect_ratio is mapped to `size` and output resolution to `resolution`.
        """
        path = "/v1/images/generations"

        json_data: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": aspect_ratio,
            "n": image_count,
        }
        if self._uses_image_resolution_field(model_name):
            json_data["resolution"] = self._normalize_image_resolution(model_name, resolution)

        # APIMart image generation accepts remote references through image_urls.
        # Local references are uploaded to object storage by the generation resolver.
        reference_resolution_diagnostics: dict[str, object] | None = None
        if urls:
            # Resolving local references uploads them to object storage (blocking network
            # I/O); offload to a worker thread so the worker's event loop is not stalled
            # while other agent runs / SSE streams share it.
            resolution_result = await asyncio.to_thread(
                resolve_generation_image_urls_with_diagnostics, urls
            )
            processed_urls = resolution_result.urls
            reference_resolution_diagnostics = resolution_result.diagnostics
            if processed_urls:
                json_data["image_urls"] = processed_urls

        result = await self._request("POST", path, json_data=json_data)
        if reference_resolution_diagnostics is not None and isinstance(result, dict):
            result["_request_diagnostics"] = {
                "reference_resolution": reference_resolution_diagnostics,
                "provider_payload_has_image": bool(json_data.get("image_urls")),
                "provider_payload_image_count": len(json_data.get("image_urls") or []),
            }
        return result

    # ===================== Video Generation =====================

    async def generate_video(
        self,
        prompt: str | None,
        model_name: str = "kling-v3",
        aspect_ratio: str = "16:9",
        duration: int | None = 5,
        quality: str | None = None,
        resolution: str | None = None,
        audio: bool = False,
        urls: list[str] | None = None,
        reference_image_urls: list[str] | None = None,
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        first_frame_url: str | None = None,
        tail_frame_url: str | None = None,
        return_last_frame: bool | None = None,
        negative_prompt: str | None = None,
        watermark: bool | None = None,
        multi_shot: bool | None = None,
        shot_type: str | None = None,
        multi_prompt: list[dict[str, Any]] | None = None,
        element_list: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Submit an async video generation task."""
        path = "/v1/videos/generations"
        normalized_model_name = model_name.lower()
        normalized_resolution = (resolution or "720p").lower()
        is_kling_model = "kling" in normalized_model_name

        json_data: dict[str, Any] = {
            "model": model_name,
        }
        if prompt:
            json_data["prompt"] = prompt
        resolved_quality = quality or resolution

        if is_kling_model:
            if normalized_resolution.startswith("4k"):
                json_data["mode"] = "4k"
            else:
                json_data["mode"] = "pro" if normalized_resolution.startswith("1080") else "std"
            json_data["aspect_ratio"] = aspect_ratio
            if audio or normalized_resolution.endswith("_audio"):
                json_data["audio"] = True
        elif self._uses_video_size_field(model_name):
            json_data["size"] = aspect_ratio
        else:
            json_data["aspect_ratio"] = aspect_ratio
        if duration is not None:
            json_data["duration"] = duration
        if self._uses_video_quality_field(model_name):
            if resolved_quality is not None:
                json_data["quality"] = resolved_quality
        elif resolution is not None and not is_kling_model:
            json_data["resolution"] = resolution
        if audio and self._uses_video_generate_audio_flag(model_name):
            json_data["generate_audio"] = True
        elif audio and is_kling_model:
            json_data["audio"] = True

        if negative_prompt:
            json_data["negative_prompt"] = negative_prompt
        if watermark is not None:
            json_data["watermark"] = watermark
        if return_last_frame is not None:
            json_data["return_last_frame"] = return_last_frame
        if multi_shot is not None:
            json_data["multi_shot"] = multi_shot
        if shot_type:
            json_data["shot_type"] = shot_type
        if multi_prompt:
            json_data["multi_prompt"] = multi_prompt
        if element_list:
            json_data["element_list"] = element_list

        # Resolve every local reference once on a worker thread (object-storage uploads are
        # blocking I/O), then substitute positionally so the provider payload keeps the
        # original ordering and duplicates. Resolving inline would stall the shared loop.
        reference_url_map = await self._resolve_local_reference_urls_off_loop(
            [
                *(reference_image_urls or urls or []),
                *(reference_video_urls or []),
                *(reference_audio_urls or []),
                first_frame_url,
                tail_frame_url,
            ]
        )

        def _resolve_ref(url: str) -> str:
            return reference_url_map.get(url, url)

        processed_reference_images = [
            _resolve_ref(url)
            for url in (reference_image_urls or urls or [])
            if url
        ]
        processed_reference_videos = [
            _resolve_ref(url)
            for url in (reference_video_urls or [])
            if url
        ]
        processed_reference_audios = [
            _resolve_ref(url)
            for url in (reference_audio_urls or [])
            if url
        ]

        if first_frame_url or tail_frame_url:
            if self._uses_video_image_with_roles(model_name) and tail_frame_url:
                image_with_roles: list[dict[str, str]] = []
                if first_frame_url:
                    image_with_roles.append({
                        "url": _resolve_ref(first_frame_url),
                        "role": "first_frame",
                    })
                if tail_frame_url:
                    image_with_roles.append({
                        "url": _resolve_ref(tail_frame_url),
                        "role": "last_frame",
                    })
                if image_with_roles:
                    json_data["image_with_roles"] = image_with_roles
            else:
                processed_frame_urls = [
                    _resolve_ref(url)
                    for url in (first_frame_url, tail_frame_url)
                    if url
                ]
                if processed_frame_urls:
                    json_data["image_urls"] = processed_frame_urls
        elif processed_reference_images:
            json_data["image_urls"] = processed_reference_images

        if processed_reference_videos:
            json_data["video_urls"] = processed_reference_videos
        if processed_reference_audios:
            json_data["audio_urls"] = processed_reference_audios

        return await self._request("POST", path, json_data=json_data)

    # ===================== Claude-compatible Messages API =====================

    async def messages(
        self,
        model: str,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 0,
        stream: bool = False,
    ) -> dict:
        """Call the Claude-compatible Messages API (v1/messages)."""
        path = "/v1/messages"
        json_data: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        effective_max_tokens = self._resolve_multimodal_max_tokens(model, max_tokens)
        self._apply_positive_limit(json_data, "max_tokens", effective_max_tokens)
        if system:
            json_data["system"] = system
        if tools:
            # Map parameters -> input_schema if needed (standardize on input_schema)
            processed_tools = []
            for t in tools:
                processed_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t.get("input_schema", t.get("parameters", {}))
                })
            json_data["tools"] = processed_tools
        if tool_choice:
            json_data["tool_choice"] = tool_choice

        return await self._request("POST", path, json_data=json_data)

    # ===================== Chat Completions (Multimodal) =====================

    async def chat_completions(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
    ) -> dict:
        """Call the unified chat completions API (/v1/chat/completions).

        Args:
        model_name: Model ID, e.g. "gemini-3.1-pro-preview", "claude-opus-4-8"
            messages: OpenAI-format messages list, e.g.
                [{"role": "user", "content": [{"type": "text", "text": "..."}]}]
            temperature: Generation temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            tools: OpenAI-format tool declarations, e.g.
                [{"type": "function", "function": {"name": ..., "parameters": ...}}]

        Returns:
            Raw API response dict with ``data.choices`` and ``data.usage``.
        """
        path = "/v1/chat/completions"
        json_data: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        effective_max_tokens = self._resolve_multimodal_max_tokens(model_name, max_tokens)
        self._apply_positive_limit(json_data, "max_tokens", effective_max_tokens)
        if tools:
            json_data["tools"] = tools
        return await self._request("POST", path, json_data=json_data, timeout=500)

    async def chat_completions_stream(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completions via SSE, yielding text chunks."""
        async for chunk in self.chat_completions_stream_events(
            model_name=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        ):
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                yield text

    async def chat_completions_stream_events(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for chunk in self.stream_chat_completions_events_raw(
            model_name=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            timeout_profile=None,
        ):
            yield chunk

    async def stream_chat_completions_events_raw(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
        timeout_profile: Any | None = None,
        prompt_cache_key: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream raw chat completion SSE events."""
        url = f"{self.BASE_URL}/v1/chat/completions"
        json_data: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        effective_max_tokens = self._resolve_multimodal_max_tokens(model_name, max_tokens)
        self._apply_positive_limit(json_data, "max_tokens", effective_max_tokens)
        if tools:
            json_data["tools"] = tools
        if tool_choice:
            json_data["tool_choice"] = tool_choice
        if prompt_cache_key:
            json_data["prompt_cache_key"] = prompt_cache_key
        headers = self._auth_headers()
        self.last_stream_usage = None

        async with httpx.AsyncClient(timeout=self._build_stream_timeout(timeout_profile)) as client:
            async with client.stream("POST", url, json=json_data, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise ApimartStreamError(
                        status_code=resp.status_code,
                        message=(
                            f"Chat completions stream error (status={resp.status_code}): "
                            f"{body.decode()}"
                        ),
                    )

                async for line in resp.aiter_lines():
                    raw = self._extract_sse_data_payload(line)
                    if raw is None:
                        continue
                    if raw == "[DONE]":
                        break
                    try:
                        data = json_module.loads(raw)
                    except (json_module.JSONDecodeError, TypeError):
                        continue
                    # Handle wrapped response: {"code": 200, "data": {...}}
                    chunk = data.get("data", data)
                    usage = chunk.get("usage", {})
                    if isinstance(usage, dict) and usage:
                        self.last_stream_usage = usage
                    if isinstance(chunk, dict):
                        yield chunk

    # ===================== Query Task Result =====================

    async def query_result(self, task_id: str) -> dict:
        """Query the status of an async generation task."""
        path = f"/v1/tasks/{task_id}"
        return await self._request("GET", path, params={"language": "zh"})
