from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta, utc_now, write_json
from app.services.agent_harness.runtime.system_write_lease import system_write_lease


def persist_prompt_cache_debug_usage_trace(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    step_id: str,
    turn: int,
    model: str,
    model_provider: str | None,
    prompt_cache_key: str | None,
    usage: dict[str, Any] | None,
    elapsed_ms: int,
    render_trace_file: str | None = None,
    parent_run_id: str | None = None,
    subagent_task_id: str | None = None,
    subagent_type: str | None = None,
    trace_scope: str = "agent",
) -> None:
    if not bool(getattr(settings, "HARNESS_PROMPT_CACHE_DEBUG", False)):
        return
    usage_payload = usage if isinstance(usage, dict) else {}
    trace_file = f"usage-turn-{turn}-step-{step_id}-{time.time_ns()}-{run_id}.json"
    trace: dict[str, Any] = {
        "version": 1,
        "trace_type": "prompt_cache_usage",
        "trace_file": trace_file,
        "created_at": utc_now(),
        "run_id": run_id,
        "conversation_id": conversation_id,
        "turn": int(turn),
        "workflow_step_id": step_id,
        "model": model,
        "model_provider": model_provider,
        "prompt_cache_key": prompt_cache_key,
        "render_trace_file": render_trace_file,
        "elapsed_ms": int(elapsed_ms or 0),
        "trace_scope": trace_scope,
        "usage": {
            "input_tokens": usage_payload.get("input_tokens"),
            "output_tokens": usage_payload.get("output_tokens"),
            "cached_tokens": usage_payload.get("cached_tokens"),
            "cache_read_tokens": usage_payload.get("cache_read_tokens"),
            "cache_creation_tokens": usage_payload.get("cache_creation_tokens"),
            "provider_code": usage_payload.get("provider_code"),
            "oneapi_request_id": usage_payload.get("oneapi_request_id"),
            "request_id": usage_payload.get("request_id"),
        },
    }
    if parent_run_id:
        trace["parent_run_id"] = parent_run_id
    if subagent_task_id:
        trace["subagent_task_id"] = subagent_task_id
    if subagent_type:
        trace["subagent_type"] = subagent_type

    meta_dir = ensure_harness_meta(user_id, conversation_id)
    debug_dir = meta_dir / "prompt_cache_debug"
    with system_write_lease(
        user_id=user_id,
        conversation_id=conversation_id,
        owner="prompt_cache_debug",
        paths=(".meta/prompt_cache_debug",),
        ttl_seconds=30.0,
        run_id=run_id,
    ):
        write_json(debug_dir / trace_file, trace)
