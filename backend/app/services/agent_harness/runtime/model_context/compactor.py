from __future__ import annotations

import asyncio
import inspect
import re
from copy import deepcopy
from collections.abc import Callable
from typing import Any

from app.core.config import settings
from app.services.agent_harness.core.utils.token_counter import estimate_messages_tokens
from app.services.agent_harness.runtime.model_context.boundary_store import append_boundary_v2
from app.services.agent_harness.runtime.model_context.budget_policy import (
    build_model_context_budget,
    calculate_token_state,
)
from app.services.agent_harness.runtime.model_context.models import (
    CompactResult,
    ModelContextLimitExceeded,
    ModelContextBundle,
)
from app.services.agent_harness.runtime.model_context.restore_planner import build_restore_plan
from app.services.agent_harness.workspace.session_v2.db_store import (
    compare_and_swap_runtime_state_payload,
    read_runtime_state_payload,
)


MODEL_CONTEXT_STATE_KEY = "model_context"
MAX_CONSECUTIVE_COMPACT_FAILURES = 3
MAX_COMPACT_PROMPT_TOO_LONG_RETRIES = 3
COMPACT_PROMPT_TOO_LONG_RETRY_MARKER = "[earlier conversation truncated for compaction retry]"
def compact_if_needed(
    user_id: int,
    conversation_id: str,
    bundle: ModelContextBundle,
    *,
    max_tokens: int,
    llm_compact_adapter: Any | None = None,
    model: str | None = None,
    run_id: str | None = None,
    runtime_contract: dict[str, Any] | None = None,
    workspace_runtime_session: dict[str, Any] | None = None,
    compact_abort_check: Callable[[], bool] | None = None,
) -> CompactResult | None:
    budget = build_model_context_budget(max_tokens=max_tokens)
    token_usage = estimate_messages_tokens(bundle.messages)
    token_state = calculate_token_state(token_usage, budget)
    _persist_token_state(user_id, conversation_id, token_state=token_state, budget=budget)
    if not budget.auto_compact_enabled:
        if token_state.is_at_blocking_limit:
            _raise_context_limit(token_state=token_state, budget=budget)
        return None
    if _compact_breaker_open(user_id, conversation_id):
        if token_state.is_at_blocking_limit:
            _raise_context_limit(token_state=token_state, budget=budget)
        return None
    if not (token_state.is_above_auto_compact_threshold or token_state.is_above_predictive_threshold):
        return None
    try:
        result = _run_llm_full_compact(
            user_id,
            conversation_id,
            bundle,
            budget=budget,
            adapter=llm_compact_adapter,
            model=model,
            run_id=run_id,
            runtime_contract=runtime_contract,
            workspace_runtime_session=workspace_runtime_session,
            compact_abort_check=compact_abort_check,
        )
    except Exception as exc:
        _record_compact_failure(user_id, conversation_id)
        if token_state.is_at_blocking_limit:
            _raise_context_limit(token_state=token_state, budget=budget, cause=exc)
        return None
    if result is None:
        _record_compact_failure(user_id, conversation_id)
        if token_state.is_at_blocking_limit:
            _raise_context_limit(token_state=token_state, budget=budget)
        return None
    _reset_compact_failures(user_id, conversation_id)
    return result


def _run_llm_full_compact(
    user_id: int,
    conversation_id: str,
    bundle: ModelContextBundle,
    *,
    budget,
    adapter: Any | None,
    model: str | None,
    run_id: str | None,
    runtime_contract: dict[str, Any] | None,
    workspace_runtime_session: dict[str, Any] | None,
    compact_abort_check: Callable[[], bool] | None,
) -> CompactResult | None:
    _raise_if_compact_aborted(compact_abort_check)
    if adapter is None:
        return None
    source_messages = [message for message in bundle.compact_messages if isinstance(message, dict)]
    if not source_messages:
        return None
    compacted = _compact_with_prompt_too_long_retries(
        adapter,
        source_messages,
        model=model,
        compact_abort_check=compact_abort_check,
    )
    _raise_if_compact_aborted(compact_abort_check)
    summary_text = _summary_text_from_compacted(compacted)
    if not summary_text or _looks_like_compact_api_error(summary_text):
        return None
    restore_plan = build_restore_plan(
        runtime_contract=runtime_contract,
        workspace_runtime_session=workspace_runtime_session,
    )
    summary_message = {"role": "user", "content": _compact_summary_content(summary_text)}
    restore_messages = restore_plan.messages
    token_counts = _token_counts(
        source_messages,
        [summary_message, *restore_messages],
        budget=budget,
    )
    method = {
        "source": "llm_full_compact",
        "model": model,
        "levels_applied": ["full_summary"],
    }
    _raise_if_compact_aborted(compact_abort_check)
    boundary = append_boundary_v2(
        user_id,
        conversation_id,
        run_id=run_id,
        compact_type="auto_full",
        covered=_covered_payload(bundle),
        summary_message=summary_message,
        restore_messages=restore_messages,
        token_counts=token_counts,
        method=method,
    )
    return CompactResult(
        boundary=boundary,
        compact_type="auto_full",
        summary_message=summary_message,
        restore_messages=restore_messages,
        token_counts=token_counts,
        method=method,
    )


def _compact_with_prompt_too_long_retries(
    adapter: Any,
    messages: list[dict[str, Any]],
    *,
    model: str | None,
    compact_abort_check: Callable[[], bool] | None,
) -> list[dict[str, Any]] | None:
    attempt_messages = list(messages)
    for attempt in range(MAX_COMPACT_PROMPT_TOO_LONG_RETRIES + 1):
        _raise_if_compact_aborted(compact_abort_check)
        try:
            result = _call_compact_adapter(
                adapter,
                attempt_messages,
                model=model,
                compact_abort_check=compact_abort_check,
            )
        except BaseException as exc:
            next_messages = _messages_for_prompt_too_long_retry(attempt_messages)
            if (
                _is_compact_abort(exc)
                or not _is_prompt_too_long_error(exc)
                or attempt >= MAX_COMPACT_PROMPT_TOO_LONG_RETRIES
                or next_messages is None
            ):
                raise
            attempt_messages = next_messages
            continue
        if result is not None:
            summary_text = _summary_text_from_compacted(result)
            if _is_prompt_too_long_summary_text(summary_text):
                next_messages = _messages_for_prompt_too_long_retry(attempt_messages)
                if attempt >= MAX_COMPACT_PROMPT_TOO_LONG_RETRIES or next_messages is None:
                    return result
                attempt_messages = next_messages
                continue
            return result
        next_messages = _messages_for_prompt_too_long_retry(attempt_messages)
        if attempt >= MAX_COMPACT_PROMPT_TOO_LONG_RETRIES or next_messages is None:
            return None
        attempt_messages = next_messages
    return None


def _call_compact_adapter(
    adapter: Any,
    messages: list[dict[str, Any]],
    *,
    model: str | None,
    compact_abort_check: Callable[[], bool] | None,
) -> list[dict[str, Any]] | None:
    compact = adapter.compact
    if compact_abort_check is not None and _accepts_should_abort(compact):
        return compact(messages, model=model, should_abort=compact_abort_check)
    return compact(messages, model=model)


def _accepts_should_abort(compact) -> bool:
    try:
        signature = inspect.signature(compact)
    except (TypeError, ValueError):
        return False
    if "should_abort" in signature.parameters:
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def _raise_if_compact_aborted(compact_abort_check: Callable[[], bool] | None) -> None:
    if compact_abort_check is not None and compact_abort_check():
        raise asyncio.CancelledError("context compaction cancelled")


def _is_compact_abort(exc: BaseException) -> bool:
    return isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit))


def _is_prompt_too_long_error(exc: BaseException) -> bool:
    failure_kind = str(getattr(exc, "failure_kind", "") or "").lower()
    raw_type = str(getattr(exc, "raw_error_type", "") or "").lower()
    raw_message = str(getattr(exc, "raw_message", "") or "")
    message = f"{failure_kind} {raw_type} {raw_message} {exc}".lower()
    markers = (
        "prompt too long",
        "context length",
        "context window",
        "maximum context",
        "max context",
        "token limit",
        "too many tokens",
        "input tokens",
        "request too large",
        "reduce the length",
    )
    return any(marker in message for marker in markers)


def _is_prompt_too_long_summary_text(summary_text: str) -> bool:
    text = str(summary_text or "").strip().lower()
    return text.startswith("prompt is too long") or text.startswith("prompt too long")


def _summary_text_from_compacted(compacted: list[dict[str, Any]] | None) -> str:
    if not isinstance(compacted, list):
        return ""
    for message in compacted:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
    return ""


def _looks_like_compact_api_error(summary_text: str) -> bool:
    text = str(summary_text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    prefix = lowered[:500].lstrip()
    error_prefixes = (
        "api error",
        "provider error",
        "request failed",
        "invalid_request",
        "invalid request",
        "bad request",
        "http 400",
        "400 bad request",
        "error code:",
    )
    if prefix.startswith(error_prefixes):
        return True
    compact_failure_markers = (
        "the model has reached its context window limit",
        "prompt too long",
        "maximum context length",
        "context length exceeded",
        "context window limit",
        "request too large",
        "too many input tokens",
        "reduce the length of the messages",
    )
    return any(marker in prefix for marker in compact_failure_markers)


def _compact_summary_content(summary_text: str, *, recent_messages_preserved: bool = False) -> str:
    summary = _format_compact_summary(summary_text)
    lines = [
        "This session is being continued from a previous conversation that ran out of context. "
        "The summary below covers the earlier portion of the conversation.",
        "",
        summary,
    ]
    if recent_messages_preserved:
        lines.extend(["", "Recent messages are preserved verbatim."])
    lines.extend(
        [
            "",
            "Continue the conversation from where it left off without asking the user any further questions. "
            "Resume directly; do not acknowledge the summary, do not recap what was happening, and do not preface "
            "the response with \"I'll continue\" or similar. Pick up the last task as if the break never happened.",
        ]
    )
    return "\n".join(lines).strip()


def _format_compact_summary(summary_text: str) -> str:
    text = str(summary_text or "").strip()
    text = _strip_analysis_block(text)
    summary_block = _extract_summary_block(text)
    if summary_block:
        return "Summary:\n" + summary_block
    if text.lower().startswith("summary:"):
        return text
    return "Summary:\n" + text


def _strip_analysis_block(text: str) -> str:
    return re.sub(r"<analysis>[\s\S]*?</analysis>", "", text, flags=re.IGNORECASE).strip()


def _extract_summary_block(text: str) -> str:
    match = re.search(r"<summary>\s*([\s\S]*?)\s*</summary>", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _covered_payload(bundle: ModelContextBundle) -> dict[str, Any]:
    return {
        "message_row_id_end": int(bundle.message_row_id_end or 0),
        "event_sequence_end": int(bundle.event_sequence_end or 0),
        "message_count": len(bundle.persisted_messages),
    }


def _token_counts(before: list[dict[str, Any]], after: list[dict[str, Any]], *, budget) -> dict[str, Any]:
    return {
        "pre": estimate_messages_tokens(before),
        "post": estimate_messages_tokens(after),
        "effective_window": int(budget.effective_window_tokens),
        "auto_threshold": int(budget.auto_threshold_tokens),
        "predictive_threshold": int(budget.predictive_threshold_tokens),
    }


def _raise_context_limit(*, token_state, budget, cause: BaseException | None = None) -> None:
    error = ModelContextLimitExceeded(
        "Context exceeds the blocking limit and must be compacted before the next model turn.",
        token_usage=int(token_state.token_usage),
        blocking_limit_tokens=int(budget.blocking_limit_tokens),
        auto_compact_enabled=bool(budget.auto_compact_enabled),
    )
    if cause is not None:
        raise error from cause
    raise error


def _messages_for_prompt_too_long_retry(messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    source = _strip_compact_retry_marker(messages)
    groups = _api_round_message_groups(source)
    if len(groups) < 2:
        return None
    retry_messages = [deepcopy(message) for group in groups[1:] for message in group]
    if not retry_messages:
        return None
    first_role = str(retry_messages[0].get("role") or "").strip()
    if first_role not in {"user", "system"}:
        retry_messages.insert(0, {"role": "user", "content": COMPACT_PROMPT_TOO_LONG_RETRY_MARKER})
    return retry_messages


def _strip_compact_retry_marker(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []
    first = messages[0]
    if first.get("role") == "user" and str(first.get("content") or "") == COMPACT_PROMPT_TOO_LONG_RETRY_MARKER:
        return messages[1:]
    return messages


def _api_round_message_groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    last_assistant_id: str | None = None
    assistant_sequence = 0
    for message in messages:
        if message.get("role") == "assistant":
            assistant_id = _assistant_round_id(message)
            if not assistant_id:
                assistant_sequence += 1
                assistant_id = f"assistant:{assistant_sequence}"
            if current and assistant_id != last_assistant_id:
                groups.append(current)
                current = [message]
            else:
                current.append(message)
            last_assistant_id = assistant_id
            continue
        current.append(message)
    if current:
        groups.append(current)
    return groups


def _assistant_round_id(message: dict[str, Any]) -> str:
    for key in ("message_id", "provider_message_id", "assistant_message_id", "source_message_id", "id"):
        value = str(message.get(key) or "").strip()
        if value:
            return value
    return ""


def _compact_breaker_open(user_id: int, conversation_id: str) -> bool:
    state = _model_context_state(user_id, conversation_id)
    return int(state.get("consecutive_auto_compact_failures") or 0) >= MAX_CONSECUTIVE_COMPACT_FAILURES


def _record_compact_failure(user_id: int, conversation_id: str) -> None:
    state = _model_context_state(user_id, conversation_id)
    state["consecutive_auto_compact_failures"] = int(state.get("consecutive_auto_compact_failures") or 0) + 1
    _save_model_context_state(user_id, conversation_id, state)


def _reset_compact_failures(user_id: int, conversation_id: str) -> None:
    state = _model_context_state(user_id, conversation_id)
    state["consecutive_auto_compact_failures"] = 0
    _save_model_context_state(user_id, conversation_id, state)


def _persist_token_state(user_id: int, conversation_id: str, *, token_state, budget) -> None:
    state = _model_context_state(user_id, conversation_id)
    state["last_token_state"] = {
        "token_usage": token_state.token_usage,
        "projected_token_usage": token_state.projected_token_usage,
        "percent_left": token_state.percent_left,
        "is_above_auto_compact_threshold": token_state.is_above_auto_compact_threshold,
        "is_above_predictive_threshold": token_state.is_above_predictive_threshold,
        "is_at_blocking_limit": token_state.is_at_blocking_limit,
    }
    state["last_budget"] = {
        "effective_window_tokens": budget.effective_window_tokens,
        "auto_threshold_tokens": budget.auto_threshold_tokens,
        "predictive_threshold_tokens": budget.predictive_threshold_tokens,
        "blocking_limit_tokens": budget.blocking_limit_tokens,
        "auto_compact_enabled": budget.auto_compact_enabled,
    }
    _save_model_context_state(user_id, conversation_id, state)


def _model_context_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    payload = read_runtime_state_payload(user_id, conversation_id) or {}
    runtime_state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), dict) else {}
    state = runtime_state.get(MODEL_CONTEXT_STATE_KEY) if isinstance(runtime_state.get(MODEL_CONTEXT_STATE_KEY), dict) else {}
    return dict(state)


def _save_model_context_state(user_id: int, conversation_id: str, state: dict[str, Any]) -> None:
    for _attempt in range(4):
        payload = read_runtime_state_payload(user_id, conversation_id) or {}
        runtime_state = dict(payload.get("runtime_state") or {}) if isinstance(payload.get("runtime_state"), dict) else {}
        runtime_state[MODEL_CONTEXT_STATE_KEY] = deepcopy(state)
        updated = compare_and_swap_runtime_state_payload(
            user_id,
            conversation_id,
            expected_updated_at=payload.get("runtime_updated_at") or payload.get("updated_at"),
            runtime_state=runtime_state,
        )
        if updated is not None:
            return
