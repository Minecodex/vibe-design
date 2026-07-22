from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.services.ollama_client import OllamaClient

from .openai_compat import prepare_tools_for_model, to_openai_messages
from .types import LlmConnectionFailure, LlmStreamChunk, LlmStreamRequest
from .usage import normalize_llm_usage


class OllamaLlmStreamClient:
    provider_name = "ollama"

    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    async def stream_chat(
        self,
        request: LlmStreamRequest,
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        pending_tool_calls: dict[int, dict[str, Any]] = {}
        stream_started = False
        meaningful_output_seen = False
        last_usage: dict[str, Any] | None = None
        finish_reason_emitted = False
        try:
            async for payload in self.client.stream_chat_completions_events_raw(
                model_name=request.model,
                messages=to_openai_messages(request.messages, request.system),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=prepare_tools_for_model(request.model, request.tools),
                tool_choice=request.tool_choice,
            ):
                stream_started = True
                choices = payload.get("choices", [])
                raw_usage = payload.get("usage", {}) or {}
                usage = normalize_llm_usage(raw_usage)
                if usage:
                    usage = {**usage, "provider_code": self.provider_name}
                if usage:
                    last_usage = usage

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

                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta", {}) or {}
                content = self._extract_content(choice, delta)
                if content:
                    meaningful_output_seen = True
                    yield LlmStreamChunk(content=content)

                for index, tool_delta in enumerate(delta.get("tool_calls", []) or []):
                    if not isinstance(tool_delta, dict):
                        continue
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
                    finish_reason_emitted = True
                    yield LlmStreamChunk(
                        finish_reason="tool_calls" if normalized_finish_reason == "tool_calls" else "stop",
                        usage=usage,
                    )
                elif usage:
                    yield LlmStreamChunk(usage=usage)

            if pending_tool_calls:
                meaningful_output_seen = True
                yield LlmStreamChunk(tool_calls=self._finalize_tool_calls(pending_tool_calls))
            meaningful_output_seen = meaningful_output_seen or last_usage is not None
            if not finish_reason_emitted:
                yield LlmStreamChunk(finish_reason="stop", usage=last_usage)
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
        lowered = raw_message.lower()
        failure_kind = "unknown_stream_failure"
        retryable = False

        if isinstance(exc, httpx.ConnectError):
            failure_kind = "connect_failure"
            retryable = True
        elif isinstance(exc, httpx.ReadTimeout):
            failure_kind = "read_timeout"
            retryable = True
        elif isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError)):
            failure_kind = "midstream_disconnect"
            retryable = True
        elif "status=" in lowered:
            failure_kind = "provider_http_error"

        return LlmConnectionFailure(
            failure_kind=failure_kind,
            retryable=retryable,
            raw_error_type=exc.__class__.__name__,
            raw_message=raw_message,
            provider_name=cls.provider_name,
            model=model,
            stream_started=stream_started,
            meaningful_output_seen=meaningful_output_seen,
        )

    @staticmethod
    def _extract_content(choice: dict[str, Any], delta: dict[str, Any]) -> str:
        candidates = (delta.get("content"), choice.get("message", {}).get("content"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
            if isinstance(candidate, list):
                parts: list[str] = []
                for item in candidate:
                    if isinstance(item, str):
                        parts.append(item)
                        continue
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                        continue
                    if item.get("type") in {"text", "output_text"} and isinstance(item.get("content"), str):
                        parts.append(item["content"])
                if parts:
                    return "".join(parts)
        return ""

    @staticmethod
    def _parse_tool_arguments(arguments_text: str) -> dict[str, Any]:
        if not arguments_text:
            return {}
        try:
            parsed = json.loads(arguments_text)
            return parsed if isinstance(parsed, dict) else {"raw": arguments_text}
        except json.JSONDecodeError:
            return {"raw": arguments_text}

    @classmethod
    def _finalize_tool_calls(cls, pending_tool_calls: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for _, tool_call in sorted(pending_tool_calls.items()):
            arguments = tool_call.get("arguments_text", "")
            tool_calls.append(
                {
                    "id": tool_call.get("id"),
                    "type": "function",
                    "name": tool_call.get("name") or "",
                    "arguments": cls._parse_tool_arguments(arguments),
                }
            )
        return tool_calls
