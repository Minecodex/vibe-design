from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings
from app.services.llm_runtime import LlmConnectionFailure

from .model_stream import ModelStreamTurn


@dataclass(slots=True)
class TurnResult:
    assistant_text: str
    tool_calls: list[dict[str, Any]]
    finish_reason: str | None
    usage: dict[str, Any] | None
    elapsed_ms: int


class ModelTurnError(Exception):
    def __init__(
        self,
        original: Exception,
        *,
        elapsed_ms: int,
        failure_kind: str | None = None,
        retryable: bool | None = None,
        meaningful_output_seen: bool = False,
    ) -> None:
        super().__init__(str(original))
        self.original = original
        self.elapsed_ms = elapsed_ms
        self.failure_kind = failure_kind
        self.retryable = retryable
        self.meaningful_output_seen = meaningful_output_seen


class TurnRunner:
    """Run one model turn and collapse stream chunks into a stable result."""

    def __init__(self, provider) -> None:
        self.provider = provider

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | None,
        tools: list[dict[str, Any]],
        model: str,
        prompt_cache_key: str | None = None,
        on_chunk: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> TurnResult:
        stream_turn = ModelStreamTurn()
        started = time.monotonic()
        try:
            async with asyncio.timeout(settings.HARNESS_MODEL_TURN_TIMEOUT_SECONDS):
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    system=system,
                    tools=tools,
                    model=model,
                    prompt_cache_key=prompt_cache_key,
                ):
                    observed = stream_turn.observe(chunk)
                    if on_chunk is not None:
                        await on_chunk(
                            {
                                "content": chunk.content,
                                "tool_calls": chunk.tool_calls,
                                "usage": chunk.usage,
                                "finish_reason": chunk.finish_reason,
                                **observed,
                            }
                        )
        except TimeoutError as exc:
            raise ModelTurnError(
                exc,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                failure_kind="read_timeout",
                retryable=True,
                meaningful_output_seen=bool(stream_turn.text or stream_turn.tool_calls or stream_turn.finish_reason),
            ) from exc
        except LlmConnectionFailure as exc:
            raise ModelTurnError(
                exc,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                failure_kind=exc.failure_kind,
                retryable=exc.retryable,
                meaningful_output_seen=exc.meaningful_output_seen or bool(stream_turn.text or stream_turn.tool_calls or stream_turn.finish_reason),
            ) from exc
        except Exception as exc:
            raise ModelTurnError(
                exc,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                meaningful_output_seen=bool(stream_turn.text or stream_turn.tool_calls or stream_turn.finish_reason),
            ) from exc

        return TurnResult(
            assistant_text=stream_turn.text,
            tool_calls=stream_turn.tool_calls,
            finish_reason=stream_turn.finish_reason,
            usage=stream_turn.usage,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


ModelTurnResult = TurnResult
ModelTurnRunner = TurnRunner
