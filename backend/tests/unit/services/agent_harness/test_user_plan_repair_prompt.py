from __future__ import annotations

from app.services.agent_harness.authoring.planning.user_plan import build_user_plan_repair_prompt


def test_html_user_plan_repair_prompt_includes_explicit_outline_shape():
    prompt = build_user_plan_repair_prompt(
        {
            "title": "设计行业服务落地页线框规划",
            "summary": "生成单页落地页线框",
            "user_plan": {
                "artifact_type": "html",
            },
        },
        mode="html",
        issues=["missing_outline_items"],
        language="zh",
    )

    assert "重新调用 request_plan_approval" in prompt
    assert "`update_planning_draft.draft_outline` 必须是数组" in prompt
    assert '"draft_outline":[' in prompt
    assert '"open_questions":[]' in prompt
    assert "Hero 区" in prompt
