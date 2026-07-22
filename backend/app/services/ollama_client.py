"""Ollama OpenAI-compatible client for local multimodal chat calls."""

import json as json_module
from collections.abc import AsyncGenerator
from typing import Any

import httpx


class OllamaClient:
    def __init__(self, base_url: str, api_key: str = "ollama", *, tool_choice_format: str = "openai"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "ollama"
        self.tool_choice_format = (tool_choice_format or "openai").strip().lower()
        self.last_stream_usage: dict[str, Any] | None = None

    @staticmethod
    def _extract_sse_data_payload(line: str) -> str | None:
        stripped = (line or "").strip()
        if not stripped.startswith("data:"):
            return None
        return stripped[5:].lstrip()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _error_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception:
            data = {"error": {"message": response.text}}
        if isinstance(data, dict):
            data["_status_code"] = response.status_code
            return data
        return {"error": {"message": str(data)}, "_status_code": response.status_code}

    @staticmethod
    def _image_data_to_result_values(data: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if url:
                values.append(url)
                continue
            b64_json = str(item.get("b64_json") or "").strip()
            if b64_json:
                values.append(f"data:image/png;base64,{b64_json}")
        return values

    async def generate_image(
        self,
        *,
        model_name: str,
        prompt: str,
        size: str,
        response_format: str | None = None,
        quality: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/images/generations"
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
        }
        if response_format:
            payload["response_format"] = response_format
        if quality:
            payload["quality"] = quality

        async with httpx.AsyncClient(timeout=500) as client:
            response = await client.post(url, json=payload, headers=self._headers)

        if response.status_code >= 400:
            return self._error_payload(response)
        data = response.json()
        if isinstance(data, dict):
            data["result_values"] = self._image_data_to_result_values(data)
            return data
        return {"error": {"message": "Invalid Ollama image generation response"}, "_status_code": 502}

    async def edit_image(
        self,
        *,
        model_name: str,
        prompt: str,
        image_refs: list[str],
        size: str,
        response_format: str | None = None,
        quality: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/images/edits"
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "image_urls": image_refs,
        }
        if response_format:
            payload["response_format"] = response_format
        if quality:
            payload["quality"] = quality

        async with httpx.AsyncClient(timeout=500) as client:
            response = await client.post(url, json=payload, headers=self._headers)

        if response.status_code >= 400:
            return self._error_payload(response)
        payload = response.json()
        if isinstance(payload, dict):
            payload["result_values"] = self._image_data_to_result_values(payload)
            return payload
        return {"error": {"message": "Invalid Ollama image edit response"}, "_status_code": 502}

    async def chat_completions(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
    ) -> dict:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=500) as client:
            response = await client.post(url, json=payload, headers=self._headers)

        if response.status_code != 200:
            return self._error_payload(response)
        return response.json()

    async def chat_completions_stream(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.stream_chat_completions_events_raw(
            model_name=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        ):
            choices = chunk.get("choices", []) if isinstance(chunk, dict) else []
            if not choices:
                continue
            choice = choices[0] if isinstance(choices[0], dict) else {}
            delta = choice.get("delta", {}) or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield content
                continue
            message = choice.get("message", {}) or {}
            content = message.get("content")
            if isinstance(content, str) and content:
                yield content

    @staticmethod
    def _flatten_tool_choice(tool_choice: dict | str) -> dict | str:
        """Convert OpenAI nested function choices to the flat Responses shape."""
        if not isinstance(tool_choice, dict):
            return tool_choice
        if tool_choice.get("type") != "function" or "name" in tool_choice:
            return tool_choice
        function = tool_choice.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            return {"type": "function", "name": function["name"]}
        return tool_choice

    def _prepare_tool_choice(self, tool_choice: dict | str) -> dict | str:
        if self.tool_choice_format == "flat":
            return self._flatten_tool_choice(tool_choice)
        return tool_choice

    async def stream_chat_completions_events_raw(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 0,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            # OpenAI-compatible streaming endpoints only emit the terminal usage
            # chunk when include_usage is requested. Without it the stream carries
            # no token counts, so every usage-based charge for Ollama-routed models
            # is silently skipped (has_billable_usage -> False). Mirror the builtin
            # provider, which already sets this.
            "stream_options": {"include_usage": True},
        }
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = self._prepare_tool_choice(tool_choice)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.last_stream_usage = None

        async with httpx.AsyncClient(timeout=500) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"Ollama stream error (status={response.status_code}): {body.decode()}"
                    )

                async for line in response.aiter_lines():
                    raw = self._extract_sse_data_payload(line)
                    if raw is None:
                        continue
                    if raw == "[DONE]":
                        break

                    try:
                        chunk = json_module.loads(raw)
                    except (json_module.JSONDecodeError, TypeError):
                        continue

                    usage = chunk.get("usage", {})
                    if isinstance(usage, dict) and usage:
                        self.last_stream_usage = usage
                    if isinstance(chunk, dict):
                        yield chunk
