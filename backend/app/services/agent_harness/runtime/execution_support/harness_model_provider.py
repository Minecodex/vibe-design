from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from collections.abc import AsyncGenerator
from collections.abc import Callable
from typing import Any

from app.core.default_models import get_default_multimodal_model
from app.core.config import (
    HARNESS_STREAM_CONNECT_TIMEOUT_SECONDS,
    HARNESS_STREAM_MAX_RETRIES_NO_PROGRESS,
    HARNESS_STREAM_MAX_RETRIES_TOOL_ARGS_ONLY,
    HARNESS_STREAM_POOL_TIMEOUT_SECONDS,
    HARNESS_STREAM_WRITE_TIMEOUT_SECONDS,
    settings,
)
from app.services.llm_runtime import (
    LlmConnectionFailure,
    LlmStreamClientFactory,
    LlmStreamChunk,
    LlmStreamRequest,
    LlmTimeoutProfile,
)

COMPACT_SYSTEM_PROMPT = (
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
    "- Do NOT use file, shell, browser, image, or any other tool.\n"
    "- You already have all the context you need in the conversation above.\n"
    "- Tool calls will be rejected and will waste your only turn.\n"
    "- Your response must be plain text: an <analysis> block followed by a <summary> block.\n\n"
    "You are compacting a Home Harness agent conversation for continuation. Preserve the user's intent, "
    "the current task state, file paths, decisions, errors and fixes, tool result references, and the exact "
    "next step needed to continue without drift. Do not include secrets, cookies, authorization headers, "
    "signed URLs, or full large tool outputs."
)

COMPACT_USER_PROMPT = """Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and the assistant's previous actions.
This summary should be thorough in capturing technical details, code patterns, architectural decisions, and current execution state that would be essential for continuing development work without losing context.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and verify that you covered the needed details. In your analysis:

1. Chronologically analyze each section of the conversation.
2. Identify the user's explicit requests and intent changes.
3. Identify the assistant's approach, decisions, tool calls, file edits, and command outputs that matter.
4. Capture specific details such as file paths, function names, important snippets, errors, and fixes.
5. Pay special attention to recent messages and user feedback.
6. Double-check technical accuracy and completeness.

Your <summary> block must include these sections:

1. Primary Request and Intent: Capture all explicit user requests and intent changes.
2. Key Technical Concepts: List important technologies, architecture concepts, and implementation patterns.
3. Files and Code Sections: List files examined, modified, or created, why they matter, and important code details.
4. Errors and Fixes: List errors encountered, test failures, command issues, and how they were handled.
5. Problem Solving: Document solved problems and any ongoing troubleshooting.
6. All User Messages: List the user's non-tool messages that affect the task.
7. Pending Tasks: List explicit pending tasks.
8. Current Work: Describe exactly what was being worked on immediately before compaction.
9. Optional Next Step: State the next step only if it directly follows the latest user request and current work.

Here's an example of how your output should be structured:

<example>
<analysis>
[Your thought process, ensuring all points are covered thoroughly and accurately]
</analysis>

<summary>
1. Primary Request and Intent:
   [Detailed description]

2. Key Technical Concepts:
   - [Concept 1]
   - [Concept 2]

3. Files and Code Sections:
   - [File Name 1]
      - [Summary of why this file is important]
      - [Important Code Snippet]

4. Errors and Fixes:
   - [Error description]:
      - [How you fixed it]

5. Problem Solving:
   [Description]

6. All User Messages:
   - [Detailed non-tool user message]

7. Pending Tasks:
   - [Task 1]

8. Current Work:
   [Precise description of current work]

9. Optional Next Step:
   [Optional next step to take]
</summary>
</example>

There may be additional summarization instructions provided in the included context. If so, follow those instructions while preserving the structure above.

Do not ask follow-up questions. Do not summarize at a high level only. Include enough concrete detail that the next model turn can continue directly.

REMINDER: Do NOT call any tools. Respond with plain text only: an <analysis> block followed by a <summary> block. Tool calls will be rejected and you will fail the task.
"""


class HarnessModelProvider:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        multimodal_provider: str | None = None,
        stream_client=None,
        stream_client_factory: LlmStreamClientFactory | None = None,
    ) -> None:
        if stream_client is not None and stream_client_factory is not None:
            raise ValueError("stream_client and stream_client_factory are mutually exclusive")
        self.api_key = api_key
        self.multimodal_provider = multimodal_provider
        if stream_client_factory is not None:
            self._stream_client_factory = stream_client_factory
        elif stream_client is not None:
            self._stream_client_factory = _FixedStreamClientFactory(stream_client)
        else:
            self._stream_client_factory = LlmStreamClientFactory(
                api_key=api_key,
                multimodal_provider=multimodal_provider,
            )
        self.last_compact_usage: dict[str, Any] | None = None
        self.last_compact_elapsed_ms: int = 0
        self.last_compact_model: str | None = None
        self.last_compact_call_id: str | None = None

    async def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 0,
        prompt_cache_key: str | None = None,
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        selected_model = model or get_default_multimodal_model()
        stream_client = self._stream_client_factory.client_for_model(selected_model)
        request = LlmStreamRequest(
            model=selected_model,
            messages=messages,
            system=system,
            tools=tools or [],
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt_cache_key=prompt_cache_key,
            timeout_profile=LlmTimeoutProfile(
                connect_seconds=HARNESS_STREAM_CONNECT_TIMEOUT_SECONDS,
                read_seconds=settings.HARNESS_STREAM_READ_TIMEOUT_SECONDS,
                write_seconds=HARNESS_STREAM_WRITE_TIMEOUT_SECONDS,
                pool_seconds=HARNESS_STREAM_POOL_TIMEOUT_SECONDS,
            ),
        )

        no_progress_attempt = 0
        tool_args_only_attempt = 0
        while True:
            buffered_tool_argument_chunks: list[StreamChunk] = []
            yielded_any_chunk = False
            saw_meaningful_chunk = False
            stream_terminal = False
            try:
                from app.services.agent_harness.agent_resources.labels import RESOURCE_LLM
                from app.services.agent_harness.agent_resources.scheduler import get_agent_resource_scheduler

                async with get_agent_resource_scheduler().acquire(RESOURCE_LLM, tool_name="chat_stream"):
                    async for chunk in stream_client.stream_chat(request):
                        if self._is_tool_argument_only_chunk(chunk):
                            buffered_tool_argument_chunks.append(chunk)
                            continue

                        if buffered_tool_argument_chunks:
                            for buffered_chunk in buffered_tool_argument_chunks:
                                yield buffered_chunk
                                yielded_any_chunk = True
                            buffered_tool_argument_chunks = []

                        yielded_any_chunk = True
                        if self._is_meaningful_stream_chunk(chunk):
                            saw_meaningful_chunk = True
                        if str(chunk.finish_reason or "").strip():
                            stream_terminal = True
                        yield chunk
                break
            except LlmConnectionFailure as exc:
                progress_state = self._progress_state(
                    yielded_any_chunk=yielded_any_chunk,
                    saw_meaningful_chunk=saw_meaningful_chunk,
                    buffered_tool_argument_chunks=buffered_tool_argument_chunks,
                    stream_terminal=stream_terminal,
                )
                if self._should_retry_failure(
                    exc,
                    progress_state=progress_state,
                    no_progress_attempt=no_progress_attempt,
                    tool_args_only_attempt=tool_args_only_attempt,
                ):
                    if progress_state == "no_progress":
                        no_progress_attempt += 1
                    elif progress_state == "tool_args_only":
                        tool_args_only_attempt += 1
                    attempt_number = no_progress_attempt if progress_state == "no_progress" else tool_args_only_attempt
                    await asyncio.sleep(self._retry_delay_seconds(exc, progress_state=progress_state, attempt=attempt_number))
                    continue
                if buffered_tool_argument_chunks:
                    for buffered_chunk in buffered_tool_argument_chunks:
                        yield buffered_chunk
                exc.meaningful_output_seen = saw_meaningful_chunk
                raise

    def compact(
        self,
        history: list[dict[str, Any]],
        *,
        model: str | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Synchronously run a no-tools handoff compaction turn.

        Context building is still synchronous, while provider calls are async.
        Running the compact request in a short-lived thread keeps the existing
        engine/SSE call shape unchanged and avoids nested event loops.
        """
        timeout = max(float(settings.HARNESS_MODEL_TURN_TIMEOUT_SECONDS), 30.0) + 5.0
        self.last_compact_usage = None
        self.last_compact_elapsed_ms = 0
        self.last_compact_model = model or get_default_multimodal_model()
        self.last_compact_call_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        deadline = started + timeout
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: asyncio.run(self._compact_async(history, model=model)))
        wait_for_completion = True
        try:
            while True:
                if should_abort is not None and should_abort():
                    wait_for_completion = False
                    future.cancel()
                    self.last_compact_elapsed_ms = int((time.monotonic() - started) * 1000)
                    raise asyncio.CancelledError("context compaction cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    wait_for_completion = False
                    future.cancel()
                    self.last_compact_elapsed_ms = int((time.monotonic() - started) * 1000)
                    raise TimeoutError("harness LLM compact timed out")
                poll_timeout = min(0.25, remaining)
                try:
                    result = future.result(timeout=poll_timeout)
                    self.last_compact_elapsed_ms = int((time.monotonic() - started) * 1000)
                    return result
                except FutureTimeoutError:
                    continue
        except Exception:
            self.last_compact_elapsed_ms = int((time.monotonic() - started) * 1000)
            raise
        finally:
            executor.shutdown(wait=wait_for_completion, cancel_futures=not wait_for_completion)

    async def _compact_async(self, history: list[dict[str, Any]], *, model: str | None = None) -> list[dict[str, Any]] | None:
        selected_model = model or get_default_multimodal_model()
        compact_prompt = {
            "role": "user",
            "content": COMPACT_USER_PROMPT,
        }
        text_parts: list[str] = []
        usage: dict[str, Any] | None = None
        async for chunk in self.chat_stream(
            [*history, compact_prompt],
            system=COMPACT_SYSTEM_PROMPT,
            tools=[],
            model=selected_model,
            temperature=0.1,
            max_tokens=8192,
        ):
            if chunk.content:
                text_parts.append(chunk.content)
            if chunk.usage:
                usage = chunk.usage
        self.last_compact_usage = usage
        self.last_compact_model = selected_model
        text = "".join(text_parts).strip()
        return _parse_compact_messages(text)

    @staticmethod
    def _is_tool_argument_only_chunk(chunk: LlmStreamChunk) -> bool:
        return (chunk.diagnostics or {}).get("provider_event_kind") == "tool_call_arguments_delta"

    @staticmethod
    def _is_meaningful_stream_chunk(chunk: LlmStreamChunk) -> bool:
        finish_reason = str(chunk.finish_reason or "").lower()
        return bool(chunk.content or chunk.tool_calls or finish_reason)

    @classmethod
    def _progress_state(
        cls,
        *,
        yielded_any_chunk: bool,
        saw_meaningful_chunk: bool,
        buffered_tool_argument_chunks: list[LlmStreamChunk],
        stream_terminal: bool,
    ) -> str:
        if stream_terminal:
            return "terminal_chunk"
        if saw_meaningful_chunk:
            if buffered_tool_argument_chunks:
                return "stable_tool_call"
            return "partial_text_only"
        if buffered_tool_argument_chunks:
            return "tool_args_only"
        if yielded_any_chunk:
            return "partial_text_only"
        return "no_progress"

    @staticmethod
    def _retry_delay_seconds(exc: LlmConnectionFailure, *, progress_state: str, attempt: int) -> float:
        if progress_state == "tool_args_only":
            delays = (0.5, 1.0, 2.0)
        elif exc.failure_kind == "provider_overload":
            delays = (1.0, 3.0, 6.0)
        else:
            delays = (0.5, 1.0, 2.0)
        return delays[min(max(attempt - 1, 0), len(delays) - 1)]

    @staticmethod
    def _should_retry_failure(
        exc: LlmConnectionFailure,
        *,
        progress_state: str,
        no_progress_attempt: int,
        tool_args_only_attempt: int,
    ) -> bool:
        if not exc.retryable:
            return False
        if progress_state == "no_progress":
            return no_progress_attempt < HARNESS_STREAM_MAX_RETRIES_NO_PROGRESS
        if progress_state == "tool_args_only" and exc.failure_kind == "midstream_disconnect":
            return tool_args_only_attempt < HARNESS_STREAM_MAX_RETRIES_TOOL_ARGS_ONLY
        return False


def create_harness_model_provider(
    *,
    api_key: str | None = None,
    multimodal_provider: str | None = None,
    stream_client_factory: LlmStreamClientFactory | None = None,
) -> HarnessModelProvider:
    return HarnessModelProvider(
        api_key=api_key,
        multimodal_provider=multimodal_provider,
        stream_client_factory=stream_client_factory,
    )


class _FixedStreamClientFactory:
    def __init__(self, stream_client) -> None:
        self._stream_client = stream_client

    def client_for_model(self, _model: str):
        return self._stream_client


def _parse_compact_messages(text: str) -> list[dict[str, Any]] | None:
    if not text:
        return None
    summary_block = _summary_block(text)
    if summary_block:
        return [{"role": "assistant", "content": summary_block, "source_kind": "llm_compaction"}]
    candidate = _json_payload_candidate(text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return [{"role": "assistant", "content": _fallback_handoff_summary(text), "source_kind": "llm_compaction"}]
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        payload = payload["messages"]
    if not isinstance(payload, list):
        return None
    messages: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"assistant", "user", "system"} or not content:
            continue
        messages.append({"role": role, "content": content, "source_kind": "llm_compaction"})
    return messages or None


def _json_payload_candidate(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return text[start : end + 1]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _summary_block(text: str) -> str:
    match = re.search(r"<summary>\s*(.*?)\s*</summary>", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()[:12_000]


def _fallback_handoff_summary(text: str) -> str:
    cleaned = text.strip()
    return cleaned[:12_000]
