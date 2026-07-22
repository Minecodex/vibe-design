from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_recovery_hint(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    instruction = str(value.get("instruction") or "").strip()
    if instruction:
        normalized["instruction"] = instruction
    for key in ("constraints", "preferred_tools", "avoid_tools"):
        items = value.get(key)
        if isinstance(items, list):
            compact = [str(item).strip() for item in items if str(item).strip()]
            if compact:
                normalized[key] = compact
    ask_user_when = str(value.get("ask_user_when") or "").strip()
    if ask_user_when:
        normalized["ask_user_when"] = ask_user_when
    context_patch = value.get("context_patch")
    if isinstance(context_patch, dict) and context_patch:
        normalized["context_patch"] = deepcopy(context_patch)
    return normalized or None


def build_failure_payload(
    *,
    failure_kind: str | None,
    summary: str | None,
    user_visible: bool,
    failure_stage: str | None = None,
    root_cause_hint: str | None = None,
    required_next_action: str | None = None,
    recovery_hint: dict[str, Any] | None = None,
    failure_signature: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any] | None:
    normalized_kind = str(failure_kind or "").strip()
    normalized_summary = str(summary or "").strip()
    normalized_stage = str(failure_stage or "").strip()
    normalized_root = str(root_cause_hint or "").strip()
    normalized_next = str(required_next_action or "").strip()
    normalized_hint = normalize_recovery_hint(recovery_hint)
    normalized_signature = str(failure_signature or "").strip()

    if not any((
        normalized_kind,
        normalized_summary,
        normalized_stage,
        normalized_root,
        normalized_next,
        normalized_hint,
        normalized_signature,
    )):
        return None

    payload: dict[str, Any] = {
        "failure_kind": normalized_kind or None,
        "failure_stage": normalized_stage or None,
        "user_visible": bool(user_visible),
        "summary": normalized_summary or None,
        "root_cause_hint": normalized_root or None,
        "required_next_action": normalized_next or None,
        "recovery_hint": normalized_hint,
        "failure_signature": normalized_signature or None,
    }
    if retryable is not None:
        payload["retryable"] = bool(retryable)
    return payload


def failure_from_review(
    review: dict[str, Any] | None,
    *,
    summary: str | None = None,
    failure_stage: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any] | None:
    if not isinstance(review, dict):
        return None
    return build_failure_payload(
        failure_kind=str(review.get("failure_kind") or "").strip() or None,
        failure_stage=failure_stage or str(review.get("failure_stage") or "").strip() or None,
        user_visible=bool(review.get("user_visible", True)),
        summary=summary if summary is not None else str(review.get("summary") or "").strip() or None,
        root_cause_hint=str(review.get("root_cause_hint") or "").strip() or None,
        required_next_action=str(review.get("required_next_action") or "").strip() or None,
        recovery_hint=review.get("recovery_hint") if isinstance(review.get("recovery_hint"), dict) else None,
        failure_signature=str(review.get("no_progress_signature") or review.get("failure_signature") or "").strip() or None,
        retryable=retryable,
    )


def failure_from_recovery_summary(
    recovery_summary: dict[str, Any] | None,
    *,
    summary: str | None,
    user_visible: bool,
    failure_stage: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any] | None:
    if not isinstance(recovery_summary, dict):
        return None
    review = recovery_summary.get("review") if isinstance(recovery_summary.get("review"), dict) else None
    if review:
        return failure_from_review(
            review,
            summary=summary,
            failure_stage=failure_stage or str(recovery_summary.get("failure_stage") or "").strip() or None,
            retryable=retryable,
        )
    return build_failure_payload(
        failure_kind=str(recovery_summary.get("failure_kind") or "").strip() or None,
        failure_stage=failure_stage or str(recovery_summary.get("failure_stage") or "").strip() or None,
        user_visible=user_visible,
        summary=summary,
        root_cause_hint=str(recovery_summary.get("root_cause_hint") or "").strip() or None,
        required_next_action=str(recovery_summary.get("required_next_action") or "").strip() or None,
        recovery_hint=recovery_summary.get("recovery_hint") if isinstance(recovery_summary.get("recovery_hint"), dict) else None,
        failure_signature=str(recovery_summary.get("failure_signature") or "").strip() or None,
        retryable=retryable,
    )
