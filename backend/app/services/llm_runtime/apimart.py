from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.services.apimart_client import ApimartClient, ApimartStreamError

from .openai_compat import prepare_tools_for_model, to_openai_messages
from .types import LlmConnectionFailure, LlmStreamChunk, LlmStreamRequest
from .usage import normalize_llm_usage

_RECOVERABLE_APIMART_STREAM_STATUS_CODES = {429, 500, 502, 503, 504}
_RECOVERABLE_APIMART_STREAM_ERROR_MARKERS = (
    "get_channel_failed",
    "please wait and try again later",
)


class ApimartLlmStreamClient:
    provider_name = "apimart"

    def __init__(self, client: ApimartClient) -> None:
        self.client = client

    async def stream_chat(
        self,
        request: LlmStreamRequest,
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        pending_tool_calls: dict[int, dict[str, Any]] = {}
        stream_started = False
        meaningful_output_seen = False
        try:
            async for payload in self.client.stream_chat_completions_events_raw(
                model_name=request.model,
                messages=to_openai_messages(request.messages, request.system),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=prepare_tools_for_model(request.model, request.tools) or None,
                tool_choice=request.tool_choice,
                timeout_profile=request.timeout_profile,
                prompt_cache_key=request.prompt_cache_key,
            ):
                stream_started = True
                choices = payload.get("choices", [])
                raw_usage = payload.get("usage", {}) or {}
                usage = normalize_llm_usage(raw_usage, metadata=self._provider_request_metadata(payload))
                if not choices:
                    if usage:
                        yield LlmStreamChunk(
                            usage=usage,
                            diagnostics={
                                "provider_event_kind": "usage_only_without_choices",
                                "raw_choices_count": 0,
                                "has_usage": True,
                            },
                        )
                    continue

                choice = choices[0]
                delta = choice.get("delta", {}) or {}
                content = delta.get("content")
                if content:
                    meaningful_output_seen = True
                    yield LlmStreamChunk(content=content)

                for index, tool_delta in enumerate(delta.get("tool_calls", []) or []):
                    slot = int(tool_delta.get("index", index))
                    state = pending_tool_calls.setdefault(
                        slot,
                        {
                            "id": tool_delta.get("id"),
                            "name": "",
                            "arguments_text": "",
                            "argument_chunk_count": 0,
                        },
                    )
                    if tool_delta.get("id"):
                        state["id"] = tool_delta["id"]
                    function_data = tool_delta.get("function", {}) or {}
                    if function_data.get("name"):
                        state["name"] = function_data["name"]
                    if function_data.get("arguments"):
                        argument_delta = function_data["arguments"]
                        state["arguments_text"] += argument_delta
                        state["argument_chunk_count"] += 1
                        yield LlmStreamChunk(
                            diagnostics={
                                "provider_event_kind": "tool_call_arguments_delta",
                                "tool_call_index": slot,
                                "tool_call_id": state.get("id"),
                                "tool_name": state.get("name") or "",
                                "argument_delta_chars": len(argument_delta),
                                "argument_chars": len(state["arguments_text"]),
                                "argument_chunk_count": state["argument_chunk_count"],
                            }
                        )

                finish_reason_raw = choice.get("finish_reason")
                normalized_finish_reason = (
                    "tool_calls" if finish_reason_raw in {"tool_calls", "function_call"} else finish_reason_raw
                )
                if normalized_finish_reason == "tool_calls" and pending_tool_calls:
                    meaningful_output_seen = True
                    yield LlmStreamChunk(tool_calls=self._finalize_tool_calls(pending_tool_calls))
                    pending_tool_calls = {}

                if normalized_finish_reason:
                    meaningful_output_seen = True
                    yield LlmStreamChunk(
                        finish_reason="tool_calls" if normalized_finish_reason == "tool_calls" else "stop",
                        usage=usage,
                    )
                elif usage:
                    yield LlmStreamChunk(usage=usage)
        except Exception as exc:
            raise self._map_failure(
                exc,
                model=request.model,
                stream_started=stream_started,
                meaningful_output_seen=meaningful_output_seen,
            ) from exc

    @classmethod
    def _map_failure(
        cls,
        exc: Exception,
        *,
        model: str,
        stream_started: bool,
        meaningful_output_seen: bool,
    ) -> LlmConnectionFailure:
        raw_message = str(exc).strip() or exc.__class__.__name__
        failure_kind = "unknown_stream_failure"
        retryable = False
        http_status: int | None = None
        lowered = raw_message.lower()

        if isinstance(exc, httpx.ConnectError):
            failure_kind = "connect_failure"
            retryable = True
        elif isinstance(exc, httpx.ReadTimeout):
            failure_kind = "read_timeout"
            retryable = True
        elif isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError)) or (
            "peer closed connection" in lowered or "incomplete chunked read" in lowered
        ):
            failure_kind = "midstream_disconnect"
            retryable = True
        elif isinstance(exc, ApimartStreamError):
            http_status = int(exc.status_code)
            if (
                http_status in _RECOVERABLE_APIMART_STREAM_STATUS_CODES
                or any(marker in lowered for marker in _RECOVERABLE_APIMART_STREAM_ERROR_MARKERS)
            ):
                failure_kind = "provider_overload"
                retryable = True
            else:
                failure_kind = "provider_http_error"
                retryable = False

        return LlmConnectionFailure(
            failure_kind=failure_kind,
            retryable=retryable,
            raw_error_type=exc.__class__.__name__,
            raw_message=raw_message,
            provider_name=cls.provider_name,
            model=model,
            http_status=http_status,
            stream_started=stream_started,
            meaningful_output_seen=meaningful_output_seen,
        )

    def _provider_request_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        provider_code = str(getattr(self.client, "code", "") or "").strip()
        if provider_code:
            metadata["provider_code"] = provider_code

        headers = getattr(self.client, "last_stream_provider_headers", None)
        if isinstance(headers, dict):
            oneapi_request_id = headers.get("x_oneapi_request_id")
            request_id = headers.get("x_request_id")
            if oneapi_request_id:
                metadata["oneapi_request_id"] = oneapi_request_id
            if request_id:
                metadata["request_id"] = request_id

        payload_request_id = payload.get("request_id") or payload.get("id")
        if payload_request_id and not metadata.get("request_id"):
            metadata["request_id"] = str(payload_request_id)
        return metadata

    @staticmethod
    def _parse_tool_arguments(arguments_text: str) -> dict[str, Any]:
        if not arguments_text:
            return {}
        try:
            parsed = json.loads(arguments_text)
            return parsed if isinstance(parsed, dict) else {"raw": arguments_text}
        except (json.JSONDecodeError, TypeError):
            pass

        decoder = json.JSONDecoder()
        idx = 0
        text_len = len(arguments_text)
        last_obj: dict[str, Any] | None = None
        while idx < text_len:
            while idx < text_len and arguments_text[idx].isspace():
                idx += 1
            if idx >= text_len:
                break
            try:
                obj, end = decoder.raw_decode(arguments_text, idx)
            except json.JSONDecodeError:
                break
            if isinstance(obj, dict):
                last_obj = obj
            idx = end

        if last_obj is not None:
            return last_obj
        return {"raw": arguments_text}

    @classmethod
    def _finalize_tool_calls(cls, pending_tool_calls: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for _, tool_call in sorted(pending_tool_calls.items()):
            arguments = tool_call.get("arguments_text", "")
            if isinstance(arguments, str):
                arguments = cls._parse_tool_arguments(arguments)
            normalized.append(
                {
                    "id": tool_call.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                    "name": tool_call.get("name", ""),
                    "arguments": arguments,
                }
            )
        return normalized
