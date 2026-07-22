from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.services.agent_harness.runtime.execution_support.harness_model_provider import create_harness_model_provider
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context

from .models import Phase, PromptMode, TurnSpec
from .assembler import PromptRuntime
from .tracing import persist_prompt_bundle_trace

logger = logging.getLogger(__name__)

_PROMPT_RUNTIME = PromptRuntime()

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_classifier_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a classifier response.

    The classifier is instructed to return a bare JSON object, but models
    occasionally wrap it in Markdown fences or wrap it in prose. A bare
    ``json.loads`` would raise in those cases, and because the model call was
    already issued (and billed by the provider) the captured usage would be
    discarded along with the exception. We strip fences and fall back to the
    first balanced ``{...}`` slice so a formatting wobble never costs us a
    billing record.
    """
    raw = (text or "").strip()
    if not raw:
        return {}
    candidates: list[str] = []
    fenced = _JSON_FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


async def _call_side_classifier_model(
    *,
    system_prompt: str,
    user_prompt: str,
    model_name: str,
    response_schema: dict[str, Any],
    provider_code: str | None = None,
    api_key: str = "",
) -> dict[str, Any]:
    provider = create_harness_model_provider(
        api_key=api_key,
        multimodal_provider=provider_code,
    )
    chunks: list[str] = []
    usage: dict[str, Any] | None = None
    started = time.monotonic()
    async for chunk in provider.chat_stream(
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
        tools=[],
        model=model_name,
        temperature=0.0,
        max_tokens=300,
    ):
        if chunk.usage:
            usage = chunk.usage
        if chunk.content:
            chunks.append(str(chunk.content))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    # Parse defensively: the provider has already charged this call, so the
    # captured usage must be propagated for billing even when the content is
    # not clean JSON. An unparseable response degrades to an empty label
    # (the caller falls back to a default route) rather than dropping the
    # usage on the floor.
    parsed = _parse_classifier_json("".join(chunks))
    if not parsed:
        logger.warning(
            "side classifier returned unparseable content (model=%s); "
            "preserving usage for billing and falling back to default route",
            model_name,
        )
    if provider_code and isinstance(usage, dict):
        usage = {**usage, "provider_code": provider_code}
    parsed["_preflight_model_call"] = {
        "model_name": model_name,
        "usage": usage,
        "elapsed_ms": elapsed_ms,
        "kind": "home_turn_router",
        "provider_code": provider_code,
    }
    return parsed


async def classify_side_payload(
    *,
    label_space: list[str],
    payload: dict[str, Any],
    model_name: str,
    provider_code: str | None = None,
    user_id: int | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.SIDE_CLASSIFIER,
            phase=Phase.PLANNING,
            language="en",
            side_payload={
                **payload,
                "label_space": list(label_space),
            },
        )
    )
    persist_prompt_bundle_trace(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        bundle=bundle,
        summary="Prompt bundle assembled (side classifier)",
    )
    result = await _call_side_classifier_model(
        system_prompt=bundle.rendered_system,
        user_prompt=str(bundle.messages[0]["content"]),
        model_name=model_name,
        response_schema={"label": "string", "confidence": "number"},
        provider_code=provider_code,
        api_key=(await resolve_user_apimart_key_for_context(user_id) if user_id is not None else ""),
    )
    response = {
        "label": str(result.get("label") or "").strip(),
        "confidence": float(result.get("confidence") or 0.0),
    }
    model_call = result.get("_preflight_model_call")
    if isinstance(model_call, dict):
        response["_preflight_model_call"] = model_call
    return response

