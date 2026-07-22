"""Repro tests pinning presentation-v2 block reduction edge cases.

These exercise the pure block-merge helpers in ``projection_store`` (no DB) so
they can be run in isolation. They document the front/back consistency contract:
the backend ``_apply_block_op`` must preserve nested children the same way the
frontend ``mergeIncomingBlock`` reducer does.
"""

from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime.presentation_v2.projection_store import _apply_block_op, _extract_text
from app.services.agent_harness.runtime.presentation_v2.reducer import reduce_event_to_ops


def _op(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "presentation.block.upsert",
        "block_key": "",
        "parent_block_key": None,
        "order": 0,
        "status": "running",
        "revision": 0,
        "source_sequence": 0,
        "payload": {},
        "block": {},
    }
    base.update(overrides)
    return base


def _block(block_key: str, ui_kind: str, status: str, revision: int) -> dict[str, Any]:
    return {
        "id": block_key,
        "block_key": block_key,
        "kind": "content",
        "ui_kind": ui_kind,
        "uiKind": ui_kind,
        "order": 0,
        "status": status,
        "visible": True,
        "payload": {"status": status},
        "children": [],
        "revision": revision,
        "source_sequence": revision,
    }


def test_subagent_terminal_upsert_preserves_streamed_child_blocks():
    # 1) A child tool block is streamed *under* the subagent card via parent_block_key.
    blocks = _apply_block_op(
        [],
        _op(
            type="presentation.block.complete",
            block_key="tool:call-1",
            parent_block_key="subagent:task-1",
            status="completed",
            revision=2,
            source_sequence=2,
            block=_block("tool:call-1", "tool_call", "completed", revision=2),
        ),
    )
    card = next(b for b in blocks if b["block_key"] == "subagent:task-1")
    assert len(card["children"]) == 1, "sanity: child block should be attached to the subagent card"

    # 2) The subagent card itself receives a terminal status update. This op carries
    #    no children (it is a top-level card upsert, not a child op). The backend must
    #    keep the previously-streamed children, mirroring the frontend reducer.
    blocks = _apply_block_op(
        blocks,
        _op(
            type="presentation.block.complete",
            block_key="subagent:task-1",
            status="completed",
            revision=5,
            source_sequence=5,
            payload={"status": "completed"},
            block=_block("subagent:task-1", "subagent_card", "completed", revision=5),
        ),
    )
    card = next(b for b in blocks if b["block_key"] == "subagent:task-1")
    assert card["status"] == "completed"
    # Today this FAILS: `{**existing, **block}` overwrites children with the op's [].
    assert len(card["children"]) == 1, "subagent child blocks must survive a terminal card upsert"


def test_parented_block_op_removes_stray_top_level_copy():
    blocks = [
        {
            "id": "analyze-image-text-call-1",
            "block_key": "analyze-image-text-call-1",
            "kind": "text",
            "ui_kind": "text",
            "uiKind": "text",
            "status": "running",
            "visible": True,
            "payload": {"text": "analysis", "toolName": "analyze_image"},
            "children": [],
            "revision": 1,
            "source_sequence": 1,
        },
        _block("subagent:task-1", "subagent_card", "running", revision=1),
    ]

    blocks = _apply_block_op(
        blocks,
        _op(
            type="presentation.block.complete",
            block_key="analyze-image-text-call-1",
            parent_block_key="subagent:task-1",
            status="completed",
            revision=2,
            source_sequence=2,
            block={
                "id": "analyze-image-text-call-1",
                "block_key": "analyze-image-text-call-1",
                "kind": "text",
                "ui_kind": "text",
                "uiKind": "text",
                "status": "completed",
                "visible": True,
                "payload": {"text": "analysis", "toolName": "analyze_image"},
                "children": [],
                "revision": 2,
                "source_sequence": 2,
            },
        ),
    )

    assert [block["block_key"] for block in blocks] == ["subagent:task-1"]
    card = blocks[0]
    assert [child["block_key"] for child in card["children"]] == ["analyze-image-text-call-1"]


def test_extract_text_does_not_bubble_subagent_tool_child_text():
    blocks = [
        {
            "id": "subagent:quality-review-1",
            "block_key": "subagent:quality-review-1",
            "kind": "content",
            "ui_kind": "subagent_card",
            "uiKind": "subagent_card",
            "status": "running",
            "visible": True,
            "payload": {"status": "running"},
            "children": [
                {
                    "id": "analyze-image-text-call-1",
                    "block_key": "analyze-image-text-call-1",
                    "kind": "text",
                    "ui_kind": "text",
                    "uiKind": "text",
                    "status": "completed",
                    "visible": True,
                    "payload": {"text": "image analysis", "toolName": "analyze_image"},
                    "children": [],
                },
            ],
        },
        {
            "id": "answer",
            "block_key": "answer",
            "kind": "text",
            "ui_kind": "text",
            "uiKind": "text",
            "status": "completed",
            "visible": True,
            "payload": {"text": "final answer"},
            "children": [],
        },
    ]

    assert _extract_text(blocks) == "final answer"


def test_interaction_submitted_emits_form_submitted_patch_and_user_bubble():
    """The server owns the `submitted` state: reducing an interaction_submitted
    event must emit a block.patch marking the pending form submitted, plus the
    user submission bubble."""
    event = {
        "type": "interaction_submitted",
        "lane": "user",
        "sequence": 12,
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "payload": {
            "request_id": "req-9",
            "answer": "Yes",
            "answers": {"q1": "Yes"},
            "display_label": "Yes, proceed",
            "approved": True,
            "kind": "ask_user",
        },
    }
    ops = reduce_event_to_ops(event)

    patch = next(o for o in ops if o["type"] == "presentation.block.patch")
    assert patch["message_key"] == "interaction:req-9"
    assert patch["block_key"] == "interaction-form:req-9"
    assert patch["status"] == "submitted"
    assert patch["payload"]["payload"]["status"] == "submitted"
    assert patch["payload"]["payload"]["answers"] == {"q1": "Yes"}

    bubble = next(o for o in ops if o["type"] == "presentation.message.upsert")
    assert bubble["role"] == "user"


def test_interaction_submitted_user_bubble_prefers_display_label():
    event = {
        "type": "interaction_submitted",
        "lane": "user",
        "sequence": 12,
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "payload": {
            "request_id": "req-1",
            "answer": "yes",
            "answers": {"choice": "yes"},
            "display_label": "Yes, proceed",
            "kind": "ask_user",
        },
    }

    ops = reduce_event_to_ops(event)

    bubble = next(o for o in ops if o["type"] == "presentation.message.upsert")
    assert bubble["role"] == "user"
    assert bubble["payload"]["content"] == "Yes, proceed"
    assert bubble["payload"]["content"] != "yes"


def test_planning_draft_updated_emits_dedicated_planning_draft_card():
    event = {
        "type": "planning_draft_updated",
        "lane": "user",
        "sequence": 22,
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "payload": {
            "planning_draft": {
                "summary": "先收拢需求再请求批准。",
                "confirmed_inputs": {"audience": "潜在客户"},
                "assumptions": ["使用占位联系表单。"],
                "draft_outline": [
                    {"id": "section-1", "title": "Hero", "summary": "价值主张。"},
                    {"id": "section-2", "title": "Contact", "summary": "联系转化。"},
                ],
                "open_questions": ["是否已有品牌色？"],
                "updated_at": "2026-06-07T10:52:10+00:00",
            },
        },
    }

    ops = reduce_event_to_ops(event)

    assert len(ops) == 1
    op = ops[0]
    assert op["type"] == "presentation.block.upsert"
    assert op["message_key"] == "home-planning-draft"
    assert op["block_key"] == "home-planning-draft-card"
    assert op["status"] == "draft"
    assert op["block"]["ui_kind"] == "planning_draft_card"
    assert op["block"]["render_key"] == "home-planning-draft"
    assert op["payload"]["draft_outline"][0]["title"] == "Hero"
    assert op["payload"]["open_questions"] == ["是否已有品牌色？"]


def test_current_outline_updated_emits_phase_patch_and_plan_card():
    event = {
        "type": "current_outline_updated",
        "lane": "user",
        "sequence": 43,
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "payload": {
            "outline": {
                "plan_instance_id": "plan-1",
                "version": 1,
                "snapshot_status": "active",
                "status": "planning_ready",
                "artifact_type": "html",
                "title": "Landing page",
                "summary": "Build a landing page.",
                "items": [
                    {"id": "section-1", "title": "Hero", "summary": "Hero section."},
                ],
            },
            "projection": {
                "plan_instance_id": "plan-1",
                "outline_version": 1,
                "status": "planning_ready",
                "readonly": False,
            },
            "execution_state": {
                "status": "planning_ready",
                "steps": [{"id": "step-1", "title": "Build", "status": "pending"}],
            },
            "change_source": "approval_requested",
        },
    }

    ops = reduce_event_to_ops(event)

    phase_patch = next(o for o in ops if o["type"] == "presentation.conversation.patch")
    assert phase_patch["payload"]["patch"]["phase"] == "planning_ready"

    plan_card = next(o for o in ops if o["type"] == "presentation.block.upsert")
    assert plan_card["message_key"] == "home-user-plan:plan-1:v1"
    assert plan_card["block"]["ui_kind"] == "user_plan_card"
    assert plan_card["payload"]["projection_state"]["readonly"] is False


def test_media_tool_events_do_not_emit_duplicate_generic_tool_blocks():
    ops = reduce_event_to_ops(
        {
            "type": "tool_completed",
            "lane": "user",
            "sequence": 51,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "tool_call_id": "call-image",
            "payload": {
                "tool": "analyze_image",
                "call_id": "call-image",
                "status": "completed",
                "result": {"analysis": "Looks good."},
            },
        }
    )

    assert ops == []


def test_generic_tool_blocks_include_normalized_tool_name_fields():
    ops = reduce_event_to_ops(
        {
            "type": "tool_completed",
            "lane": "user",
            "sequence": 52,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "tool_call_id": "call-shell",
            "payload": {"tool": "exec_command", "status": "completed"},
        }
    )

    assert len(ops) == 1
    payload = ops[0]["payload"]
    assert payload["tool"] == "exec_command"
    assert payload["tool_name"] == "exec_command"
    assert payload["toolName"] == "exec_command"


def test_subagent_card_and_children_route_to_per_subagent_message():
    # A subagent card, a block nested under it, and the critique-derived design
    # jury card must all resolve to the same stable per-subagent message so they
    # group together while still owning their own timeline position.
    card_op = reduce_event_to_ops(
        {
            "type": "presentation.block.upsert",
            "lane": "user",
            "sequence": 10,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "type": "presentation.block.upsert",
                "block_key": "subagent:quality-review-1",
                "block": {"ui_kind": "subagent_card"},
            },
        }
    )[0]
    child_op = reduce_event_to_ops(
        {
            "type": "presentation.block.upsert",
            "lane": "user",
            "sequence": 11,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "type": "presentation.block.upsert",
                "block_key": "analyze-image-text-call-1",
                "parent_block_key": "subagent:quality-review-1",
                "block": {"ui_kind": "text"},
            },
        }
    )[0]
    jury_op = reduce_event_to_ops(
        {
            "type": "critique.round_completed",
            "lane": "user",
            "sequence": 12,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {"critique_run_id": "c-1", "subagent_task_id": "quality-review-1", "round": 1},
        }
    )[0]

    assert card_op["message_key"] == "conv-1:subagent:quality-review-1"
    assert child_op["message_key"] == "conv-1:subagent:quality-review-1"
    assert jury_op["message_key"] == "conv-1:subagent:quality-review-1"

    # A different subagent gets its own message (so they interleave by time
    # instead of collapsing into one run-level assistant bubble).
    other_card_op = reduce_event_to_ops(
        {
            "type": "presentation.block.upsert",
            "lane": "user",
            "sequence": 20,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "type": "presentation.block.upsert",
                "block_key": "subagent:quality-review-2",
                "block": {"ui_kind": "subagent_card"},
            },
        }
    )[0]
    assert other_card_op["message_key"] == "conv-1:subagent:quality-review-2"


def test_critique_event_emits_design_jury_child_under_subagent_card():
    ops = reduce_event_to_ops(
        {
            "type": "critique.degraded",
            "lane": "user",
            "sequence": 53,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "critique_run_id": "critique-1",
                "subagent_task_id": "quality-review-1",
                "status": "degraded",
                "round": 1,
                "warnings": [],
            },
        }
    )

    assert len(ops) == 2
    op = ops[0]
    assert op["type"] == "presentation.block.complete"
    assert op["parent_block_key"] == "subagent:quality-review-1"
    assert op["block"]["ui_kind"] == "design_jury_card"
    assert op["payload"]["critique_run_id"] == "critique-1"
    # The degraded outcome also terminalizes the parent subagent card so a reloaded
    # snapshot does not show it stuck at "running".
    parent_patch = ops[1]
    assert parent_patch["type"] == "presentation.block.patch"
    assert parent_patch["block_key"] == "subagent:quality-review-1"
    assert parent_patch["status"] == "degraded"
    assert parent_patch["payload"]["status"] == "degraded"


def test_critique_round_completed_emits_completed_design_jury_child():
    ops = reduce_event_to_ops(
        {
            "type": "critique.round_completed",
            "lane": "user",
            "sequence": 54,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "critique_run_id": "critique-1",
                "subagent_task_id": "quality-review-1",
                "status": "running",
                "round": 1,
                "warnings": [],
            },
        }
    )

    assert len(ops) == 1
    op = ops[0]
    assert op["type"] == "presentation.block.complete"
    assert op["status"] == "completed"
    assert op["block"]["status"] == "completed"
    assert op["payload"]["status"] == "completed"
    assert op["payload"]["display_status"] == "round_completed"


def test_critique_shipped_emits_design_jury_child():
    ops = reduce_event_to_ops(
        {
            "type": "critique.shipped",
            "lane": "user",
            "sequence": 55,
            "conversation_id": "conv-1",
            "run_id": "run-1",
            "payload": {
                "critique_run_id": "critique-1",
                "subagent_task_id": "quality-review-1",
                "status": "shipped",
                "round": 1,
                "max_rounds": 3,
                "score_scale": 10,
                "scores": {"critic": 8.2, "brand": 8.4},
                "warnings": [],
            },
        }
    )

    assert len(ops) == 2
    op = ops[0]
    assert op["type"] == "presentation.block.complete"
    assert op["status"] == "shipped"
    assert op["parent_block_key"] == "subagent:quality-review-1"
    assert op["block"]["ui_kind"] == "design_jury_card"
    assert op["block"]["status"] == "shipped"
    assert op["payload"]["status"] == "shipped"
    assert op["payload"]["scores"] == {"critic": 8.2, "brand": 8.4}
    parent_patch = ops[1]
    assert parent_patch["type"] == "presentation.block.patch"
    assert parent_patch["block_key"] == "subagent:quality-review-1"
    assert parent_patch["status"] == "completed"


def _tool_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "lane": "user",
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "sequence": 1,
        "payload": payload,
    }


def test_tool_started_event_produces_running_tool_call_block_with_args():
    ops = reduce_event_to_ops(
        _tool_event(
            "tool_started",
            {"tool": "exec_command", "tool_call_id": "call-1", "args": {"command": "pytest -q"}},
        )
    )
    assert len(ops) == 1
    op = ops[0]
    assert op["type"] == "presentation.block.upsert"
    assert op["status"] == "running"
    assert op["block"]["ui_kind"] == "tool_call"
    assert op["block"]["payload"]["toolName"] == "exec_command"
    assert op["block"]["payload"]["args"] == {"command": "pytest -q"}
    assert op["block_key"] == "tool:call-1"


def test_tool_completed_with_is_error_marks_block_failed():
    ops = reduce_event_to_ops(
        _tool_event(
            "tool_completed",
            {"tool": "exec_command", "tool_call_id": "call-1", "is_error": True, "output": "boom"},
        )
    )
    assert len(ops) == 1
    op = ops[0]
    assert op["type"] == "presentation.block.complete"
    assert op["status"] == "failed"
    assert op["block"]["status"] == "failed"


def test_tool_completed_without_error_marks_block_completed():
    ops = reduce_event_to_ops(
        _tool_event(
            "tool_completed",
            {"tool": "read_file", "tool_call_id": "call-2", "is_error": False, "output": "ok"},
        )
    )
    assert len(ops) == 1
    assert ops[0]["status"] == "completed"


def test_dedicated_card_tool_does_not_emit_generic_tool_block():
    ops = reduce_event_to_ops(
        _tool_event("tool_completed", {"tool": "web_search", "tool_call_id": "call-3"})
    )
    assert ops == []
