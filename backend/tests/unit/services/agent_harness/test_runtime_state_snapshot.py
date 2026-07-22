from pathlib import Path

from app.services.agent_harness.runtime.state.runtime_snapshot import build_runtime_state_snapshot



def test_runtime_state_snapshot_tracks_current_item_and_artifacts():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-1",
        conversation={
            "id": "conv-1",
            "phase": "executing",
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
            "run_id": "run-1",
            "last_tool": "create_pptx",
            "plan_state": {
                "current_step": "step-2",
                "steps": [
                    {"id": "step-1", "title": "封面页", "status": "completed"},
                    {"id": "step-2", "title": "行业概述页", "status": "in_progress"},
                    {"id": "step-3", "title": "趋势分析页", "status": "pending"},
                ],
            },
        },
        plan_review_state={
            "review_status": "approved",
            "approved_outline": {
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "items": [
                    {"id": "slide-1", "title": "封面页", "order": 1},
                    {"id": "slide-2", "title": "行业概述", "order": 2},
                    {"id": "slide-3", "title": "趋势分析", "order": 3},
                ],
            },
        },
        runtime_state={
            "run_status": "running",
            "artifacts": [{"file_path": "published/design-insights.pptx"}],
        },
    )

    assert snapshot["phase"] == "executing"
    assert snapshot["run_status"] == "running"
    assert snapshot["current_item_id"] == "slide-2"
    assert snapshot["current_action"] == "running:create_pptx"
    assert snapshot["artifacts"] == [{"file_path": "published/design-insights.pptx"}]
    assert [item["status"] for item in snapshot["item_progress"]] == [
        "completed",
        "in_progress",
        "pending",
    ]


def test_runtime_state_snapshot_preserves_artifact_manifest():
    manifest = {
        "version": 1,
        "kind": "spreadsheet",
        "entry": "xlsx-prepared/births.xlsx",
        "title": "Births",
        "renderer": "file",
        "exports": ["xlsx"],
    }

    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-manifest",
        conversation={
            "id": "conv-manifest",
            "phase": "executing",
            "runtime_status": "running",
            "run_state": "executing",
        },
        runtime_state={"artifact_manifest": manifest},
    )

    assert snapshot["artifact_manifest"] == manifest


def test_runtime_state_snapshot_prefers_explicit_current_item_id():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-explicit",
        conversation={
            "id": "conv-explicit",
            "phase": "executing",
            "runtime_status": "running",
            "run_state": "executing",
            "plan_state": {
                "current_step": "step-1",
                "current_item_id": "slide-3",
                "steps": [
                    {"id": "step-1", "title": "正在推进内容", "status": "in_progress"},
                ],
            },
        },
        plan_review_state={
            "review_status": "approved",
            "approved_outline": {
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "items": [
                    {"id": "slide-1", "title": "封面页", "order": 1},
                    {"id": "slide-2", "title": "行业概述", "order": 2},
                    {"id": "slide-3", "title": "趋势分析", "order": 3},
                ],
            },
        },
        runtime_state={"run_status": "running", "artifacts": []},
    )

    assert snapshot["current_item_id"] == "slide-3"
    assert [item["status"] for item in snapshot["item_progress"]] == [
        "pending",
        "pending",
        "in_progress",
    ]


def test_runtime_state_snapshot_keeps_review_phase_pending():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-2",
        conversation={
            "id": "conv-2",
            "phase": "awaiting_plan_review",
            "runtime_status": "waiting_input",
            "run_state": "waiting_review",
            "plan_state": {},
        },
        plan_review_state={
            "review_status": "awaiting_review",
            "draft_outline": {
                "artifact_type": "word",
                "title": "行业报告",
                "items": [
                    {"id": "section-1", "title": "摘要", "order": 1},
                    {"id": "section-2", "title": "正文", "order": 2},
                ],
            },
        },
        runtime_state={"run_status": "waiting_review", "artifacts": []},
    )

    assert snapshot["phase"] == "awaiting_plan_review"
    assert snapshot["run_status"] == "waiting_review"
    assert snapshot["current_item_id"] is None
    assert snapshot["current_action"] == "awaiting_review"
    assert [item["status"] for item in snapshot["item_progress"]] == ["pending", "pending"]


def test_runtime_state_snapshot_does_not_keep_stale_failed_run_status():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-stale-run-status",
        conversation={
            "id": "conv-stale-run-status",
            "phase": "executing",
            "runtime_status": "running",
            "run_state": "executing",
        },
        runtime_state={
            "run_status": "failed",
            "artifacts": [],
        },
    )

    assert snapshot["run_status"] == "running"


def test_plan_review_persistence_updates_runtime_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.runtime.state.runtime_projection_store import persist_plan_review_state
    from app.services.agent_harness.runtime.state.store_core import read_runtime_state
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, update_conversation

    conversation = create_conversation(7, title="Plan Review")
    update_conversation(
        7,
        conversation["id"],
        phase="awaiting_plan_review",
        runtime_status="waiting_input",
        run_state="waiting_review",
        plan_state={"steps": [{"id": "step-1", "title": "摘要", "status": "pending"}]},
    )
    persist_plan_review_state(
        7,
        conversation["id"],
        draft_outline={
            "artifact_type": "word",
            "title": "行业报告",
            "summary": "两章文档",
            "items": [{"id": "section-1", "title": "摘要", "order": 1, "status": "pending"}],
            "constraints": [],
            "style_notes": [],
        },
        review_status="awaiting_review",
        revision_session=None,
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="execution_progress_updated",
        data={
            "message": "等待确认大纲",
            "status": "waiting_review",
        },
    )

    runtime_state = read_runtime_state(7, conversation["id"])

    assert runtime_state["phase"] == "awaiting_plan_review"
    assert runtime_state["review_status"] == "awaiting_review"
    assert runtime_state["item_progress"][0]["title"] == "摘要"


