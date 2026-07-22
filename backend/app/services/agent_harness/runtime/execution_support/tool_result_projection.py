"""Project a tool's full execution output into the model-facing content.

Mirrors Claude Code's ``mapToolResultToToolResultBlockParam`` + ``maxResultSizeChars``
behaviour: the model receives the *raw* tool output verbatim, capped by a
per-tool character budget. The full output is always persisted to a blob, so
when the budget is exceeded the prompt gets a truncated prefix plus a pointer
to the persisted result instead of a lossy summary.

Failure / no-progress guidance produced by ``reviewer.review_tool_result`` is
preserved on top of the raw output so the model still gets actionable repair
hints (this is intentionally richer than upstream Claude Code).
"""

from __future__ import annotations

from typing import Any

_GUIDANCE_KEYS = (
    "failure",
    "failure_kind",
    "root_cause_hint",
    "required_next_action",
    "recovery_hint",
    "no_progress_signature",
)


def _blob_ref(blob_artifact: Any) -> str:
    if isinstance(blob_artifact, dict):
        ref = str(blob_artifact.get("ref") or "").strip()
        if ref:
            return ref
    return "the persisted tool-result blob"


def apply_char_budget(
    output: str,
    *,
    max_chars: int,
    blob_artifact: Any = None,
) -> tuple[str, bool, int]:
    """Return ``(text, truncated, total_chars)`` for the model-facing output.

    When ``output`` fits within ``max_chars`` it is returned unchanged. Otherwise
    it is truncated to ``max_chars`` with a trailing marker pointing at the blob
    that holds the full result.
    """

    text = str(output or "")
    total = len(text)
    budget = max(0, int(max_chars or 0))
    if total <= budget:
        return text, False, total
    marker = (
        f"\n\n[output truncated: {budget}/{total} chars — "
        f"full result persisted at {_blob_ref(blob_artifact)}]"
    )
    return text[:budget] + marker, True, total


def _failure_guidance_fields(review: Any) -> dict[str, Any]:
    if not isinstance(review, dict):
        return {}
    if not _has_actionable_guidance(review):
        return {}
    fields: dict[str, Any] = {}
    for key in _GUIDANCE_KEYS:
        value = review.get(key)
        if value is not None and value != "":
            fields[key] = value
    return fields


def _has_actionable_guidance(review: dict[str, Any]) -> bool:
    for key in (
        "failure_kind",
        "root_cause_hint",
        "required_next_action",
        "recovery_hint",
        "no_progress_signature",
    ):
        if review.get(key):
            return True
    failure = review.get("failure")
    if not isinstance(failure, dict):
        return False
    return any(
        failure.get(key)
        for key in (
            "failure_kind",
            "root_cause_hint",
            "required_next_action",
            "recovery_hint",
            "failure_signature",
        )
    )


def build_model_tool_content(
    *,
    tool_name: str,
    output: str,
    review: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    blob_artifact: Any = None,
    max_chars: int,
) -> dict[str, Any]:
    """Build the JSON payload a tool result contributes to the model prompt.

    Success path: raw ``output`` capped at ``max_chars`` (overflow → blob pointer).
    Error / noop path: same raw output as evidence, plus reviewer guidance fields.
    """

    outcome = outcome if isinstance(outcome, dict) else {}
    is_error = bool(outcome.get("is_error"))
    status = "failed" if is_error else (str(outcome.get("status") or "").strip() or "completed")

    text, truncated, total = apply_char_budget(output, max_chars=max_chars, blob_artifact=blob_artifact)

    payload: dict[str, Any] = {"status": status, "output": text}
    if truncated:
        payload["output_truncated"] = True
        payload["output_total_chars"] = total

    payload.update(_failure_guidance_fields(review))

    if blob_artifact:
        payload["blob_artifact"] = blob_artifact

    return {key: value for key, value in payload.items() if value is not None and value != ""}
