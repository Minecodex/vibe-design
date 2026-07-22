from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass
class PreflightBillingEngine:
    user_id: int
    current_parent_usage_log_id: int | None = None


def _field(model_call: Any, name: str, default=None):
    if isinstance(model_call, dict):
        return model_call.get(name, default)
    return getattr(model_call, name, default)


def _normalize_provider_code(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _model_call_provider(model_call: Any, usage: dict[str, Any] | None) -> str | None:
    provider_code = _normalize_provider_code(_field(model_call, "provider_code"))
    if provider_code:
        return provider_code
    if isinstance(usage, dict):
        provider_code = _normalize_provider_code(usage.get("provider_code"))
        if provider_code:
            return provider_code
        provider_bill = usage.get("provider_bill")
        if isinstance(provider_bill, dict):
            return _normalize_provider_code(provider_bill.get("provider_code"))
    return None


def _preflight_billing_key(
    *,
    turn_idempotency_key: str | None,
    conversation_id: str,
    kind: str,
    index: int,
    usage: dict[str, Any] | None,
    model_name: str | None,
) -> str | None:
    """Derive a stable per-call billing key for preflight model usage.

    The key must survive a client retry of the same logical turn so that
    duplicate preflight charges are deduplicated at the DB level via the
    usage log's billing_key unique index. Prefers the provider-issued
    request id (most stable) and falls back to a hash of input shape.
    """
    base = (turn_idempotency_key or "").strip()
    if not base:
        return None
    request_id: str | None = None
    if isinstance(usage, dict):
        rid = usage.get("oneapi_request_id") or usage.get("request_id")
        if rid is not None:
            text = str(rid).strip()
            if text:
                request_id = text
    if request_id is None:
        # Fall back to a deterministic shape-hash so retries that don't yet
        # have a provider id still dedupe consistently.
        shape = sha256(
            f"{conversation_id}|{kind}|{index}|{model_name or ''}|{(usage or {}).get('input_tokens', 0)}|{(usage or {}).get('output_tokens', 0)}".encode("utf-8")
        ).hexdigest()[:16]
        request_id = shape
    return f"preflight:{base}:{kind}:{index}:{request_id}"[:255]


async def record_turn_preflight_model_calls(
    *,
    user_id: int,
    conversation: dict[str, Any],
    artifact_mode: str | None,
    run_id: str,
    preflight_model_calls: list[Any],
    turn_idempotency_key: str | None = None,
) -> int | None:
    model_calls = list(preflight_model_calls or [])
    if not model_calls:
        return None

    from app.services.agent_harness.core.context import create_context
    from app.services.agent_harness.runtime.execution_support.billing_controller import (
        has_billable_usage,
        record_preflight_model_billing,
    )

    billing_conversation = dict(conversation)
    billing_conversation["artifact_mode"] = artifact_mode
    conversation_id = str(conversation["id"])
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        conversation=billing_conversation,
    )
    billing_engine = PreflightBillingEngine(user_id=user_id)
    for index, model_call in enumerate(model_calls):
        usage = _field(model_call, "usage")
        if not has_billable_usage(usage):
            continue
        if _model_call_provider(model_call, usage) == "ollama":
            continue
        kind = str(_field(model_call, "kind", "preflight") or "preflight")
        model_name = _field(model_call, "model_name")
        billing_key = _preflight_billing_key(
            turn_idempotency_key=turn_idempotency_key,
            conversation_id=conversation_id,
            kind=kind,
            index=index,
            usage=usage,
            model_name=model_name,
        )
        await record_preflight_model_billing(
            billing_engine,
            conversation=billing_conversation,
            ctx=ctx,
            model_name=model_name,
            usage=usage,
            elapsed_ms=int(_field(model_call, "elapsed_ms", 0) or 0),
            kind=kind,
            billing_key=billing_key,
        )
    return ctx.parent_usage_log_id


