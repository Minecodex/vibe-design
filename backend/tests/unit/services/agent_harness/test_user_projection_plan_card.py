"""B1: plan/outline cards must be emitted as *live* presentation ops.

Before the fix, ``emit_current_outline_updated`` / ``emit_execution_started``
only published the domain event (``current_outline_updated`` etc.). That event
is dropped by the frontend live router (not a presentation op, not in the
runtime-adapter allow-list), so the plan card only appeared after a reload.

These tests pin that the emit path now also publishes a ``user_plan_card``
presentation op so the frontend reducer renders it in real time.

Run:
    cd backend && python -m pytest \
      tests/unit/services/agent_harness/test_user_projection_plan_card.py -q
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.agent_harness.authoring.planning import user_projection


def _capture(monkeypatch) -> list[Any]:
    drafts: list[Any] = []

    def _fake_publish_presentation_event(_user_id, _conversation_id, *, run_id, draft):  # noqa: ANN001
        drafts.append(draft)
        return None

    monkeypatch.setattr(user_projection, "publish_presentation_event", _fake_publish_presentation_event)
    # The domain event is irrelevant for these assertions; swallow it.
    monkeypatch.setattr(user_projection, "publish_user_event", lambda *a, **k: None)
    return drafts


def _outline() -> dict[str, Any]:
    return {
        "plan_instance_id": "plan-1",
        "version": 1,
        "snapshot_status": "active",
        "status": "planning_ready",
        "artifact_type": "html",
        "title": "Landing page",
        "summary": "Build a landing page.",
        "items": [{"id": "section-1", "title": "Hero", "summary": "Hero section."}],
        "projection_state": {"plan_instance_id": "plan-1", "outline_version": 1, "status": "planning_ready", "readonly": False},
        "execution_state": {"status": "planning_ready", "steps": []},
    }


def _plan_card_drafts(drafts: list[Any]) -> list[Any]:
    out = []
    for d in drafts:
        payload = getattr(d, "payload", {}) or {}
        block = payload.get("block") if isinstance(payload.get("block"), dict) else {}
        ui_kind = str(block.get("ui_kind") or block.get("uiKind") or "")
        if str(d.event_type).startswith("presentation.") and ui_kind == "user_plan_card":
            out.append(d)
    return out


def test_emit_current_outline_updated_publishes_plan_card_presentation_op(monkeypatch):
    drafts = _capture(monkeypatch)
    user_projection.emit_current_outline_updated(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        current_outline=_outline(),
        created=False,
        change_source="approval_requested",
    )
    plan_cards = _plan_card_drafts(drafts)
    assert plan_cards, f"expected a user_plan_card presentation op, got: {[getattr(d, 'event_type', None) for d in drafts]}"
    payload = plan_cards[0].payload
    assert payload["message_key"] == "home-user-plan:plan-1:v1"
    assert payload["block"]["ui_kind"] == "user_plan_card"
    assert "source_sequence" not in payload
    assert "op_id" not in payload
    assert "revision" not in payload
    assert "source_sequence" not in payload["block"]
    assert "revision" not in payload["block"]


def test_emit_execution_started_publishes_plan_card_presentation_op(monkeypatch):
    drafts = _capture(monkeypatch)
    user_projection.emit_execution_started(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        current_outline=_outline(),
    )
    assert _plan_card_drafts(drafts), "execution_started should also stream the (now executing) plan card"


def test_live_plan_op_and_domain_reduction_converge_to_single_row(tmp_path, monkeypatch):
    """End-to-end: the live presentation op + the domain-event reduction both
    target the same message_key, so the durable projection must contain exactly
    one plan-card row (no duplicate from the extra live emission)."""
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import service as session_service

    user_id = 7
    conv = create_conversation(user_id, title="plan-live", runtime_profile="home")
    conversation_id = conv["id"]

    user_projection.emit_current_outline_updated(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id="run-1",
        current_outline=_outline(),
        created=True,
        change_source="approval_requested",
    )

    messages = session_service.load_messages(user_id, conversation_id)
    plan_rows = [
        m
        for m in messages
        if any(
            str(b.get("ui_kind") or b.get("uiKind") or "") == "user_plan_card"
            for b in (m.get("blocks") or [])
        )
    ]
    assert len(plan_rows) == 1, f"expected exactly one plan-card row, got {len(plan_rows)}: {[m['id'] for m in plan_rows]}"
