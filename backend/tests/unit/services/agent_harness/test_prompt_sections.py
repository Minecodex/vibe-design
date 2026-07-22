from __future__ import annotations

from app.services.agent_harness.authoring.prompt.sections import PromptSections


def test_planning_prompt_uses_latest_draft_outline_for_approval():
    prompt = PromptSections.plan_gate(
        phase="planning",
        language="zh",
        has_skill=True,
        has_plan=False,
        execution_locked=False,
    )

    assert "request_plan_approval 会提交最新草稿大纲用于审批" in prompt
    assert "update_planning_draft.draft_outline" in prompt
    assert "user_plan.outline.sections" not in prompt
    assert '"draft_outline"' in prompt
    assert "Hero 区" in prompt


def test_specialized_planning_prompt_uses_loaded_skill_before_asking_user():
    prompt = PromptSections.plan_gate(
        phase="planning",
        language="zh",
        has_skill=True,
        has_plan=False,
        execution_locked=False,
    )

    assert "当前已加载所选 skill" in prompt
    assert "先基于已加载 skill、用户输入和参考资料" in prompt
    assert "草稿不会展示开始执行按钮" in prompt
