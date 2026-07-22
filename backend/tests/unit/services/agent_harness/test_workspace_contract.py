from __future__ import annotations

from app.services.agent_harness.authoring.planning.outline_runtime import build_plan_context_block
from app.services.agent_harness.authoring.prompt.sections import PromptSections
from app.services.agent_harness.authoring.prompt.harness_prompt import build_system_prompt
from app.services.agent_harness.core.contracts.workspace_contract import WorkspaceContract


def test_workspace_contract_mentions_artifact_session_and_not_old_tools():
    text = WorkspaceContract.prompt_section("en")
    assert "references/" in text
    assert "project/" in text
    assert "published/" in text
    assert "skill/" in text
    assert ".skill_runtime" not in text
    assert "CONVERSATION_DIR is the only workspace root" in text
    assert "real physical directory names" in text
    assert "register_artifact" in text
    assert "publish_output" in text
    assert "artifact_manifest.entry" in text
    assert "artifact_session" not in text
    assert "begin_output" not in text
    assert "begin_edit" not in text
    assert ".work/scratch" not in text
    assert "file_versions/" not in text
    assert "HARNESS_OUTPUT_ABS" not in text
    assert "HARNESS_ASSETS_DIR" not in text
    assert "HARNESS_GENERATED_DIR" not in text
    assert "publish_file" not in text
    assert "start_file_edit" not in text
    assert "list_workspace_items" not in text
    assert "source_path" not in text
    assert "output_path" not in text


def test_system_prompt_does_not_duplicate_workspace_contract():
    system = build_system_prompt("en")
    assert ".work/generated" not in system
    assert "publish_file" not in system
    assert "start_file_edit" not in system
    assert len(system.splitlines()) <= 18


def test_system_prompt_injects_language_contract():
    zh_system = build_system_prompt("zh")
    en_system = build_system_prompt("en")

    assert "# Language" in zh_system
    assert "当前会话语言：中文" in zh_system
    assert "工具参数中的用户可见文案" in zh_system
    assert "品牌名、URL、文件路径、代码标识符、API 名称和引用原文保持原样" in zh_system

    assert "# Language" in en_system
    assert "Current conversation language: English" in en_system
    assert "user-facing prose inside tool arguments" in en_system
    assert "Keep brand names, URLs, file paths, code identifiers, API names" in en_system


def test_canvas_ask_user_requires_standalone_brief_before_confirmation_card():
    zh_system = build_system_prompt("zh", runtime_profile="canvas")
    en_system = build_system_prompt("en", runtime_profile="canvas")

    assert "ask_user 只能承接用户决策" in zh_system
    assert "不能作为阶段成果、方案、简报、策略或图稿选择依据的主要展示容器" in zh_system
    assert "先正文、后工具" in zh_system
    assert "只有实际列出具体内容才算完成展示" in zh_system
    assert "description 只能作为短提示，不能替代正文展示" in zh_system
    assert "ask_user may only capture the user's decision" in en_system
    assert "must follow this fixed order" in en_system
    assert "not serve as the primary display container" in en_system
    assert "actually lists the concrete content" in en_system
    assert "must not replace the assistant text" in en_system


def test_context_prompt_includes_workspace_contract_without_unloaded_skill():
    from app.services.agent_harness.authoring.prompt import context_builder

    system = context_builder.render_static_system_context(
        language="en",
        conversation={"artifact_mode": "web", "runtime_profile": "home"},
        model_name="test-model",
        skill=None,
        skill_prompt="Active domain skill text",
        artifact_mode="web",
        skill_id=None,
        skill_runtime_dir=None,
        prepared_workspace=None,
        workspace_runtime_session=None,
        runtime_contract=None,
        tool_schemas=None,
    )

    assert "Workspace contract" in system
    assert "Active domain skill text" not in system


def test_base_system_prompt_stays_short_in_both_languages():
    assert len(build_system_prompt("en").splitlines()) <= 18
    assert len(build_system_prompt("zh").splitlines()) <= 18


def test_plan_gate_for_approved_plan_requires_frequent_updates():
    text = PromptSections.plan_gate(
        phase="executing",
        language="en",
        has_skill=True,
        has_plan=True,
        execution_locked=True,
    )

    assert "started execution" in text
    assert "When a step starts" in text
    assert "when a step finishes" in text
    assert "Normal assistant progress text does not count as a plan update" in text
    assert "final user-facing answer" in text
    assert "update_execution_progress" in text


def test_build_plan_context_block_requires_plan_sync_before_final():
    text = build_plan_context_block(
        {
            "title": "Demo",
            "summary": "Keep plan synced",
            "status": "in_progress",
            "current_step": "step-1",
            "steps": [{"id": "step-1", "title": "Do work", "status": "in_progress"}],
        },
        language="en",
    )

    assert text is not None
    assert "before starting execution" in text
    assert "after a step is completed" in text
    assert "Normal assistant progress text does not count as a plan update" in text
    assert "final user-facing answer" in text
    assert "update_execution_progress" in text


def test_workspace_contract_guidance_uses_write_path_only():
    new_guidance = WorkspaceContract.new_publish_guidance()
    edit_guidance = WorkspaceContract.edit_publish_guidance()

    assert "register_artifact" in new_guidance
    assert "publish_output" in new_guidance
    assert "final file" in new_guidance
    assert "registered entry" in new_guidance
    assert "HARNESS_OUTPUT_ABS" not in new_guidance
    assert "artifact_session" not in new_guidance
    assert "register_artifact" in edit_guidance
    assert "publish_output" in edit_guidance
    assert "final file" in edit_guidance
    assert "HARNESS_INPUT_ABS" not in edit_guidance


def test_workspace_contract_marks_skill_runtime_as_input_only():
    combined = "\n".join(
        [
            WorkspaceContract.prompt_section("en"),
            WorkspaceContract.prompt_section("zh"),
        ]
    )

    assert "skill/" in combined
    assert ".skill_runtime" not in combined
    assert "read-only" in combined
    assert "只读" in combined


def test_workspace_contract_excludes_media_from_version_publishing():
    combined = "\n".join(
        [
            WorkspaceContract.prompt_section("en"),
            WorkspaceContract.prompt_section("zh"),
            WorkspaceContract.new_publish_guidance(),
            WorkspaceContract.edit_publish_guidance(),
        ]
    )

    assert "image or video" not in combined
    assert "图片和视频" in combined
    assert "reference assets" in combined
