from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

from app.core.billing_pricing import get_model_label

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
    update_conversation,
    update_conversation_async,
)
from app.services.agent_harness.runtime.execution_support.billing import (
    charge_harness_amount,
    get_harness_db_session_factory,
    resolve_harness_billing_label,
)


logger = logging.getLogger(__name__)


class BillingEngineProtocol(Protocol):
    user_id: int
    current_parent_usage_log_id: int | None


def get_db_session_factory():
    return get_harness_db_session_factory()


def _usage_int(usage: dict[str, Any] | None, *keys: str) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in keys:
        try:
            value = int(usage.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _usage_optional_int(usage: dict[str, Any] | None, *keys: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for key in keys:
        if key not in usage or usage.get(key) is None:
            continue
        try:
            return int(usage.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    return None


def has_billable_usage(usage: dict[str, Any] | None) -> bool:
    """Only provider responses with real token usage are billable."""
    return bool(
        _usage_int(usage, "input_tokens", "prompt_tokens")
        or _usage_int(usage, "output_tokens", "completion_tokens")
    )


def _usage_str(usage: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(usage, dict):
        return None
    for key in keys:
        value = usage.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _usage_request_metadata(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    provider_bill = usage.get("provider_bill")
    provider_bill = provider_bill if isinstance(provider_bill, dict) else {}
    metadata: dict[str, Any] = {}
    request_id = _usage_str(usage, "request_id", "x_request_id") or _usage_str(provider_bill, "request_id")
    oneapi_request_id = (
        _usage_str(usage, "oneapi_request_id", "x_oneapi_request_id")
        or _usage_str(provider_bill, "oneapi_request_id")
    )
    provider_code = _usage_str(usage, "provider_code") or _usage_str(provider_bill, "provider_code")
    if request_id:
        metadata["request_id"] = request_id
    if oneapi_request_id:
        metadata["oneapi_request_id"] = oneapi_request_id
    if provider_code:
        metadata["provider_code"] = provider_code
    if provider_bill:
        metadata["provider_bill"] = provider_bill
    return metadata


def _usage_cache_metadata(usage: dict[str, Any] | None) -> dict[str, int]:
    metadata: dict[str, int] = {}
    for param_key, usage_keys in {
        "cached_tokens": ("cached_tokens",),
        "cache_read_tokens": ("cache_read_tokens",),
        "cache_creation_tokens": ("cache_creation_tokens",),
    }.items():
        value = _usage_optional_int(usage, *usage_keys)
        if value is not None:
            metadata[param_key] = value
    return metadata


def _conversation_mode(conversation: dict[str, Any]) -> str | None:
    return str(conversation.get("artifact_mode") or "").strip().lower() or None


def _ctx_has_billing_state(ctx: HarnessContext) -> bool:
    return bool(
        ctx.accumulated_amount_cents
        or ctx.billing_breakdown
        or ctx.billing_counts
        or ctx.billing_models
        or ctx.billing_model_stats
        or ctx.billing_elapsed_ms
    )


def _summary_list(summary: dict[str, Any], key: str) -> list[Any]:
    value = summary.get(key)
    return list(value) if isinstance(value, list) else []


def _hydrate_category_from_summary(
    ctx: HarnessContext,
    summary: dict[str, Any],
    *,
    category: str,
    calls_key: str,
    models_key: str,
    stats_key: str,
) -> None:
    try:
        calls = int(summary.get(calls_key) or 0)
    except (TypeError, ValueError):
        calls = 0
    if calls > 0:
        ctx.billing_counts[category] = calls

    models = {
        str(item).strip()
        for item in _summary_list(summary, models_key)
        if str(item).strip()
    }
    if models:
        ctx.billing_models[category] = models

    stats_by_model: dict[str, dict[str, Any]] = {}
    for item in _summary_list(summary, stats_key):
        if not isinstance(item, dict):
            continue
        model_name = str(item.get("model_name") or "").strip()
        if not model_name:
            continue
        stats_by_model[model_name] = {
            "model_name": model_name,
            "model_label": str(item.get("model_label") or "").strip() or get_model_label(model_name),
            "calls": int(item.get("calls") or 0),
            "success_calls": int(item.get("success_calls") or 0),
            "failed_calls": int(item.get("failed_calls") or 0),
        }
    if stats_by_model:
        ctx.billing_model_stats[category] = stats_by_model


def _hydrate_context_billing_from_usage_log(ctx: HarnessContext, log: Any) -> None:
    params = log.params if isinstance(getattr(log, "params", None), dict) else {}
    summary = params.get("billing_summary") if isinstance(params, dict) else None
    if not isinstance(summary, dict):
        return

    ctx.accumulated_amount_cents = float(getattr(log, "amount_cents", 0) or 0)
    _hydrate_category_from_summary(
        ctx,
        summary,
        category="multimodal",
        calls_key="multimodal_calls",
        models_key="multimodal_models",
        stats_key="multimodal_model_stats",
    )
    _hydrate_category_from_summary(
        ctx,
        summary,
        category="image_analysis",
        calls_key="image_analysis_calls",
        models_key="image_analysis_models",
        stats_key="image_analysis_model_stats",
    )
    _hydrate_category_from_summary(
        ctx,
        summary,
        category="image_generation",
        calls_key="image_generation_calls",
        models_key="image_models",
        stats_key="image_model_stats",
    )
    _hydrate_category_from_summary(
        ctx,
        summary,
        category="video_generation",
        calls_key="video_generation_calls",
        models_key="video_models",
        stats_key="video_model_stats",
    )
    _hydrate_category_from_summary(
        ctx,
        summary,
        category="context_compression",
        calls_key="context_compression_calls",
        models_key="context_compression_models",
        stats_key="context_compression_model_stats",
    )
    try:
        total_elapsed_ms = int(summary.get("total_elapsed_ms") or getattr(log, "elapsed_ms", 0) or 0)
    except (TypeError, ValueError):
        total_elapsed_ms = 0
    if total_elapsed_ms > 0:
        target_category = next(
            (category for category in ("multimodal", "image_analysis", "image_generation", "video_generation", "context_compression") if ctx.billing_counts.get(category, 0) > 0),
            "multimodal",
        )
        ctx.billing_elapsed_ms[target_category] = total_elapsed_ms


async def hydrate_context_billing_from_parent_log(ctx: HarnessContext) -> None:
    if ctx.parent_usage_log_id is None or _ctx_has_billing_state(ctx):
        return
    session_factory = get_db_session_factory()
    async with session_factory() as db:
        from app.models.billing import UsageLog

        log = await db.get(UsageLog, ctx.parent_usage_log_id)
        if log is None:
            return
        _hydrate_context_billing_from_usage_log(ctx, log)


async def create_parent_usage_log(
    engine: BillingEngineProtocol,
    *,
    conversation: dict[str, Any],
    ctx: HarnessContext,
) -> None:
    if ctx.parent_usage_log_id is not None:
        await hydrate_context_billing_from_parent_log(ctx)
        engine.current_parent_usage_log_id = ctx.parent_usage_log_id
        return

    session_factory = get_db_session_factory()
    async with session_factory() as db:
        from app.services.billing_service import BillingService

        log = await BillingService(db).create_usage_log(
            user_id=engine.user_id,
            parent_id=None,
            task_id=None,
            model_name="agent_harness",
            task_type="agent",
            amount_cents=int(ctx.accumulated_amount_cents),
            params=ctx.build_usage_log_params(),
            task_status="pending",
            billing_label=resolve_harness_billing_label(
                mode=_conversation_mode(conversation),
                skill_id=conversation.get("skill_id"),
            ),
            elapsed_ms=0,
        )
        ctx.parent_usage_log_id = log.id
        conversation["parent_usage_log_id"] = log.id
        engine.current_parent_usage_log_id = log.id
        await update_conversation_async(
            engine.user_id,
            conversation["id"],
            parent_usage_log_id=log.id,
        )


async def create_run_parent_usage_log(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    conversation: dict[str, Any],
) -> int:
    from app.services.agent_harness.core.context import create_context
    from app.services.billing_service import BillingService

    billing_conversation = dict(conversation or {})
    billing_conversation["parent_usage_log_id"] = None
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        language=str(billing_conversation.get("language") or "zh"),
        conversation=billing_conversation,
    )
    session_factory = get_db_session_factory()
    async with session_factory() as db:
        log = await BillingService(db).create_usage_log(
            user_id=user_id,
            parent_id=None,
            task_id=None,
            model_name="agent_harness",
            task_type="agent",
            amount_cents=0,
            billing_key=f"harness:parent:{run_id}",
            params=ctx.build_usage_log_params(mode=_conversation_mode(billing_conversation)),
            task_status="pending",
            billing_label=resolve_harness_billing_label(
                mode=_conversation_mode(billing_conversation),
                skill_id=billing_conversation.get("skill_id"),
            ),
            elapsed_ms=0,
        )
        return int(log.id)


async def update_parent_usage_log(
    engine: BillingEngineProtocol,
    *,
    conversation: dict[str, Any],
    ctx: HarnessContext,
    status: str,
) -> None:
    if ctx.parent_usage_log_id is None:
        return

    session_factory = get_db_session_factory()
    async with session_factory() as db:
        from app.services.billing_service import BillingService

        billing_summary = ctx.build_billing_summary()
        await BillingService(db).refresh_parent_usage_log(
            ctx.parent_usage_log_id,
            params=ctx.build_usage_log_params(mode=_conversation_mode(conversation)),
            status_override=status,
            fallback_amount_cents=int(ctx.accumulated_amount_cents),
            billing_label=resolve_harness_billing_label(
                mode=_conversation_mode(conversation),
                skill_id=conversation.get("skill_id"),
            ),
            elapsed_ms=billing_summary.get("total_elapsed_ms") or 0,
        )
        engine.current_parent_usage_log_id = ctx.parent_usage_log_id


async def record_preflight_model_billing(
    engine: BillingEngineProtocol,
    *,
    conversation: dict[str, Any],
    ctx: HarnessContext,
    model_name: str | None,
    usage: dict[str, Any] | None,
    elapsed_ms: int,
    kind: str,
    billing_key: str | None = None,
) -> bool:
    """Charge model calls that happen before the main agent loop starts.

    When ``billing_key`` is provided, the child usage log uses that key for
    DB-level deduplication. This is critical for preflight calls because the
    HTTP request handler reruns preflight before the agent run is enqueued —
    a client retry with the same turn idempotency key would otherwise double
    charge.
    """
    await create_parent_usage_log(engine, conversation=conversation, ctx=ctx)

    recorded = await record_model_usage_billing(
        user_id=engine.user_id,
        ctx=ctx,
        model_name=model_name,
        usage=usage,
        elapsed_ms=elapsed_ms,
        kind=kind,
        billing_key=billing_key,
    )
    await update_parent_usage_log(engine, conversation=conversation, ctx=ctx, status="pending")
    return recorded


async def record_model_usage_billing(
    *,
    user_id: int,
    ctx: HarnessContext,
    model_name: str | None,
    usage: dict[str, Any] | None,
    elapsed_ms: int,
    kind: str | None = None,
    category: str = "multimodal",
    billing_key: str | None = None,
) -> bool:
    """Record one effective model call in a Harness billing context.

    ``billing_key`` is an optional caller-supplied dedup key. When set it is
    used as the usage log's ``billing_key`` to prevent duplicate charges if
    the same logical call is retried (e.g. preflight calls re-issued on
    client retry). Subagent calls derive their own key automatically.
    """
    if not model_name or not has_billable_usage(usage):
        return False

    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
    request_metadata = _usage_request_metadata(usage)
    cache_metadata = _usage_cache_metadata(usage)
    provider_code = request_metadata.get("provider_code") or "apimart"
    provider_request_id = request_metadata.get("oneapi_request_id") or request_metadata.get("request_id")
    provider_trace_id = request_metadata.get("request_id")
    sidechain_idempotency_key = (
        _sidechain_usage_idempotency_key(
            ctx=ctx,
            model_name=model_name,
            usage=usage,
            kind=kind,
            request_metadata=request_metadata,
        )
        if ctx.is_subagent
        else None
    )
    effective_billing_key = sidechain_idempotency_key or (str(billing_key).strip() if billing_key else None)
    child_params: dict[str, Any] = {
        "kind": kind or "agent_llm",
        "agent_run_id": ctx.run_id,
        "conversation_id": ctx.conversation_id,
        "parent_run_id": ctx.parent_run_id,
        "parent_usage_log_id": ctx.parent_usage_log_id,
        "model_name": model_name,
        "provider_code": provider_code,
        "provider_request_id": provider_request_id,
        "provider_trace_id": provider_trace_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        **request_metadata,
        **cache_metadata,
    }
    if ctx.is_subagent:
        child_params.update({
            "sidechain_task_id": ctx.subagent_run_id or ctx.run_id,
            "subagent_task_id": ctx.subagent_run_id or ctx.run_id,
            "child_run_id": ctx.run_id,
            "subagent_run_id": ctx.subagent_run_id or ctx.run_id,
            "subagent_label": ctx.subagent_label,
            "subagent_type": ctx.subagent_type,
            "idempotency_key": sidechain_idempotency_key,
        })

    if provider_code == "ollama":
        cost = 0
        child_status = "success"
        detail: dict[str, Any] = {
            "model_name": model_name,
            "elapsed_ms": elapsed_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **request_metadata,
            **cache_metadata,
        }
        if kind:
            detail["kind"] = kind
        if ctx.parent_usage_log_id is not None:
            session_factory = get_db_session_factory()
            async with session_factory() as db:
                from app.services.billing_service import BillingService

                billing_svc = BillingService(db)
                created_result = await billing_svc.create_usage_log(
                    user_id=user_id,
                    parent_id=ctx.parent_usage_log_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=category,
                    amount_cents=cost,
                    billing_key=effective_billing_key,
                    params=child_params,
                    task_status=child_status,
                    billing_label="billing.labels.multimodal_call",
                    elapsed_ms=elapsed_ms,
                    provider_code=provider_code,
                    provider_request_id=provider_request_id,
                    provider_trace_id=provider_trace_id,
                    billing_mode="local_zero_cost",
                    return_created=bool(effective_billing_key),
                )
                if effective_billing_key:
                    _log, created = created_result
                    if not created:
                        logger.info(
                            "Skipped duplicate Ollama usage billing for key %s",
                            effective_billing_key,
                        )
                        return False
                await billing_svc.refresh_parent_usage_log(ctx.parent_usage_log_id)
        ctx.record_billing(
            category=category,
            amount=cost,
            detail=detail,
        )
        return True

    if request_metadata.get("provider_code") == "lingyaai":
        cost = 0
        child_status = "pending" if request_metadata.get("oneapi_request_id") else "blocked"
        if ctx.parent_usage_log_id is not None and effective_billing_key:
            session_factory = get_db_session_factory()
            async with session_factory() as db:
                from app.services.billing_service import BillingService

                billing_svc = BillingService(db)
                _log, created = await billing_svc.create_provider_reconcile_usage_log(
                    user_id=user_id,
                    parent_id=ctx.parent_usage_log_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=category,
                    provider_code="lingyaai",
                    provider_request_id=request_metadata.get("oneapi_request_id"),
                    provider_trace_id=request_metadata.get("request_id"),
                    billing_key=effective_billing_key,
                    params=child_params,
                    billing_label="billing.labels.multimodal_call",
                    elapsed_ms=elapsed_ms,
                    return_created=True,
                )
                if not created:
                    logger.info(
                        "Skipped duplicate sidechain provider usage billing for key %s",
                        effective_billing_key,
                    )
                    return False
            detail: dict[str, Any] = {
                "model_name": model_name,
                "elapsed_ms": elapsed_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                **request_metadata,
                **cache_metadata,
            }
            if kind:
                detail["kind"] = kind
            ctx.record_billing(
                category=category,
                amount=cost,
                detail=detail,
            )
            return True
    else:
        if ctx.parent_usage_log_id is not None and effective_billing_key:
            session_factory = get_db_session_factory()
            async with session_factory() as db:
                from app.services.billing_service import BillingService

                billing_svc = BillingService(db)
                placeholder, created = await billing_svc.create_usage_log(
                    user_id=user_id,
                    parent_id=ctx.parent_usage_log_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=category,
                    amount_cents=0,
                    billing_key=effective_billing_key,
                    params=child_params | {"billing_phase": "reserved"},
                    task_status="pending",
                    billing_label="billing.labels.multimodal_call",
                    elapsed_ms=elapsed_ms,
                    provider_code=provider_code,
                    provider_request_id=provider_request_id,
                    provider_trace_id=provider_trace_id,
                    billing_mode="local_price",
                    return_created=True,
                )
                if not created:
                    logger.info(
                        "Skipped duplicate usage billing for key %s",
                        effective_billing_key,
                    )
                    return False
                placeholder_id = placeholder.id

            cost = await charge_harness_amount(
                user_id,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            child_status = "success"
            detail: dict[str, Any] = {
                "model_name": model_name,
                "elapsed_ms": elapsed_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                **request_metadata,
                **cache_metadata,
            }
            if kind:
                detail["kind"] = kind
            ctx.record_billing(
                category=category,
                amount=cost,
                detail=detail,
            )
            async with session_factory() as db:
                from app.services.billing_service import BillingService

                billing_svc = BillingService(db)
                await billing_svc.update_usage_log(
                    placeholder_id,
                    {
                        "amount_cents": int(cost),
                        "amount_cents_original": int(cost),
                        "status": child_status,
                        "params": child_params,
                    },
                )
                await billing_svc.refresh_parent_usage_log(ctx.parent_usage_log_id)
            return True

        cost = await charge_harness_amount(
            user_id,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        child_status = "success"
    detail: dict[str, Any] = {
        "model_name": model_name,
        "elapsed_ms": elapsed_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        **request_metadata,
        **cache_metadata,
    }
    if kind:
        detail["kind"] = kind
    ctx.record_billing(
        category=category,
        amount=cost,
        detail=detail,
    )
    if ctx.parent_usage_log_id is not None:
        session_factory = get_db_session_factory()
        async with session_factory() as db:
            from app.services.billing_service import BillingService

            billing_svc = BillingService(db)
            if request_metadata.get("provider_code") == "lingyaai":
                created_result = await billing_svc.create_provider_reconcile_usage_log(
                    user_id=user_id,
                    parent_id=ctx.parent_usage_log_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=category,
                    provider_code="lingyaai",
                    provider_request_id=request_metadata.get("oneapi_request_id"),
                    provider_trace_id=request_metadata.get("request_id"),
                    billing_key=effective_billing_key,
                    params=child_params,
                    billing_label="billing.labels.multimodal_call",
                    elapsed_ms=elapsed_ms,
                    return_created=bool(effective_billing_key),
                )
                if effective_billing_key:
                    _log, created = created_result
                    if not created:
                        logger.info(
                            "Skipped duplicate provider usage billing for key %s",
                            effective_billing_key,
                        )
                        return False
            else:
                await billing_svc.create_usage_log(
                    user_id=user_id,
                    parent_id=ctx.parent_usage_log_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=category,
                    amount_cents=int(cost),
                    billing_key=effective_billing_key,
                    params=child_params,
                    task_status=child_status,
                    billing_label="billing.labels.multimodal_call",
                    elapsed_ms=elapsed_ms,
                    provider_code=provider_code,
                    provider_request_id=provider_request_id,
                    provider_trace_id=provider_trace_id,
                    billing_mode="local_price",
                )
            await billing_svc.refresh_parent_usage_log(ctx.parent_usage_log_id)
    return True


def _sidechain_usage_idempotency_key(
    *,
    ctx: HarnessContext,
    model_name: str,
    usage: dict[str, Any] | None,
    kind: str | None,
    request_metadata: dict[str, Any],
) -> str:
    request_id = request_metadata.get("oneapi_request_id") or request_metadata.get("request_id")
    if request_id:
        return f"sidechain:{ctx.conversation_id}:{ctx.subagent_run_id or ctx.run_id}:{request_id}"
    payload = {
        "conversation_id": ctx.conversation_id,
        "parent_run_id": ctx.parent_run_id,
        "run_id": ctx.run_id,
        "subagent_run_id": ctx.subagent_run_id,
        "model_name": model_name,
        "kind": kind or "agent_llm",
        "usage": usage or {},
    }
    return "sidechain:" + hashlib.sha256(str(payload).encode("utf-8")).hexdigest()[:32]


async def record_context_compression_billing(
    *,
    user_id: int,
    ctx: HarnessContext,
    model_name: str | None,
    usage: dict[str, Any] | None,
    elapsed_ms: int,
    kind: str,
) -> bool:
    return await record_model_usage_billing(
        user_id=user_id,
        ctx=ctx,
        model_name=model_name,
        usage=usage,
        elapsed_ms=elapsed_ms,
        kind=kind,
        category="context_compression",
    )

