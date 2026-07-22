from __future__ import annotations

import json
from typing import Any

from app.services.agent_harness.core.utils.token_counter import estimate_tokens

from .models import PromptBlock, TurnSpec


def estimate_block_tokens(block: PromptBlock) -> int:
    return estimate_tokens(str(block.content or ""))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return estimate_tokens(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))


def build_trace(
    *,
    spec: TurnSpec,
    included_blocks: list[PromptBlock],
    omitted_fragments: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    included = [
        {
            "id": block.id,
            "layer": block.layer,
            "rule_family": block.rule_family,
            "stability": (
                str(block.metadata.get("fragment_stability"))
                if isinstance(block.metadata, dict) and block.metadata.get("fragment_stability")
                else "dynamic"
            ),
            "token_estimate": estimate_block_tokens(block),
        }
        for block in included_blocks
    ]
    rule_family_counts: dict[str, int] = {}
    long_doc_summaries: list[dict[str, Any]] = []
    state_payload_sizes: dict[str, int] = {}
    truncation_reasons: list[dict[str, Any]] = []

    for block in included_blocks:
        if block.rule_family:
            rule_family_counts[block.rule_family] = rule_family_counts.get(block.rule_family, 0) + 1
        provider = block.metadata.get("provider") if isinstance(block.metadata, dict) else None
        if provider and block.metadata.get("record_as_long_doc_summary", True):
            long_doc_summaries.append({"fragment_id": block.id, "provider": provider})
        if block.layer == "state":
            state_payload_sizes[block.id.split(".", 1)[-1]] = len(str(block.content or ""))
        reason = block.metadata.get("truncation_reason") if isinstance(block.metadata, dict) else None
        if reason:
            truncation_reasons.append({"fragment_id": block.id, "reason": reason})

    return {
        "mode": spec.mode.value,
        "phase": spec.phase_value,
        "included_fragments": included,
        "omitted_fragments": omitted_fragments,
        "rule_family_counts": rule_family_counts,
        "long_doc_summaries": long_doc_summaries,
        "state_payload_sizes": state_payload_sizes,
        "truncation_reasons": truncation_reasons,
        "message_token_estimate": estimate_messages_tokens(messages),
    }
