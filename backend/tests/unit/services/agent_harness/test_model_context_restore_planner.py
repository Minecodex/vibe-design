from __future__ import annotations

from app.services.agent_harness.runtime.model_context.restore_planner import build_restore_plan


def test_restore_planner_keeps_dynamic_runtime_anchors_without_large_state():
    plan = build_restore_plan(
        runtime_contract={
            "direction_id": "direction-a",
            "runtime_execution_contract": {
                "active_entry": "site/index.html",
                "artifact_work_root": "site",
            },
        },
        workspace_runtime_session={
            "artifact_work_root": "site",
            "agent_cwd": "project/site",
            "selected_design_system": "design-system-a",
        },
    )

    assert len(plan.messages) == 1
    content = plan.messages[0]["content"]
    assert "- active_entry: site/index.html" in content
    assert "- artifact_work_root: site" in content
    assert "- agent_cwd: project/site" in content
    assert "- selected_direction: direction-a" in content
    assert "- selected_design_system: design-system-a" in content
    assert "publish_targets" not in content
    assert {"kind": "file", "value": "site/index.html", "source": "active_entry"} in plan.anchors
