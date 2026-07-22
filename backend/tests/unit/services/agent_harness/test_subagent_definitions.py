import pytest

from app.services.agent_harness.capabilities.subagents import (
    SubagentContext,
    SubagentDefinition,
    SubagentRequest,
    SubagentResult,
    SubagentTaskSpec,
    get_subagent_definition,
    list_public_subagent_definitions,
    list_subagent_definitions,
)
from app.services.agent_harness.capabilities.subagents.definitions import _build_definitions_by_name
from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.core.context import HarnessContext


def test_subagent_types_define_agent_style_contract_fields():
    definition = SubagentDefinition(
        name="custom",
        description="Custom subagent",
        system_prompt="You are focused.",
        allowed_tools=("grep_files", "glob_files"),
        disallowed_tools=("Agent",),
        read_only=True,
        max_turns=6,
        internal=True,
    )
    request = SubagentRequest(
        task_id="sub-task-1",
        spec=SubagentTaskSpec(
            description="Formula audit",
            prompt="Inspect workbook formulas",
            subagent_type="Explore",
        ),
    )
    result = SubagentResult(
        task_id="task-1",
        status="completed",
        summary="No issues found.",
        result={"issues": []},
    )
    context = SubagentContext(
        parent_run_id="parent-run",
        subagent_run_id="child-run",
        subagent_type="Explore",
        label="Formula audit",
        skill_id="xlsx",
    )

    assert definition.name == "custom"
    assert definition.description == "Custom subagent"
    assert definition.system_prompt == "You are focused."
    assert definition.allowed_tools == ("grep_files", "glob_files")
    assert definition.disallowed_tools == ("Agent",)
    assert definition.read_only is True
    assert definition.max_turns == 6
    assert definition.tool_result_summary_chars == 4000
    assert definition.internal is True

    assert request.task == "Inspect workbook formulas"
    assert request.label == "Formula audit"
    assert request.subagent_type == "Explore"
    assert request.spec.to_dict() == {
        "description": "Formula audit",
        "prompt": "Inspect workbook formulas",
        "subagent_type": "Explore",
    }

    assert result.task_id == "task-1"
    assert result.status == "completed"
    assert result.summary == "No issues found."
    assert result.result == {"issues": []}

    assert context.parent_run_id == "parent-run"
    assert context.subagent_run_id == "child-run"
    assert context.subagent_type == "Explore"
    assert context.label == "Formula audit"
    assert context.skill_id == "xlsx"


def test_subagent_task_spec_defaults_to_general_purpose():
    spec = SubagentTaskSpec.from_mapping(
        {
            "description": "Inspect files",
            "prompt": "Read the files and summarize risks.",
        }
    )

    assert spec.description == "Inspect files"
    assert spec.prompt == "Read the files and summarize risks."
    assert spec.subagent_type == "general-purpose"


def test_builtin_definitions_expose_public_profiles_and_hide_quality_review():
    definitions = {definition.name: definition for definition in list_subagent_definitions()}
    public = {definition.name for definition in list_public_subagent_definitions()}

    assert {"general-purpose", "Explore", "Plan", "QualityReview"} <= set(definitions)
    assert public == {"general-purpose", "Explore", "Plan"}

    explore = get_subagent_definition("Explore")
    plan = get_subagent_definition("Plan")
    general = get_subagent_definition("general-purpose")
    quality = get_subagent_definition("QualityReview")

    assert explore == definitions["Explore"]
    assert plan == definitions["Plan"]
    assert general == definitions["general-purpose"]
    assert quality == definitions["QualityReview"]

    readonly_expected = {
        "analyze_image",
        "glob_files",
        "grep_files",
        "list_files",
        "read_file",
        "workspace_map",
        "web_search",
    }
    assert set(explore.allowed_tools) == readonly_expected
    assert set(plan.allowed_tools) == readonly_expected
    assert {"edit_file", "write_file", "Agent", "ask_user", "publish_output", "register_artifact"} <= set(
        explore.disallowed_tools
    )
    assert explore.read_only is True
    assert plan.read_only is True

    assert {"ask_user", "Agent"} <= set(general.disallowed_tools)
    assert general.read_only is False

    assert quality.internal is True
    assert quality.read_only is True
    for definition in definitions.values():
        assert definition.max_turns == 10
        assert definition.tool_result_summary_chars == 4000
    assert get_subagent_definition("missing-subagent") is None


def test_quality_review_tool_pool_is_internal_read_only_and_controlled(tmp_path):
    parent_ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        language="en",
        workspace_root=tmp_path,
    )
    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={"id": "conv-1"},
        parent_context=parent_ctx,
        parent_registry=create_harness_registry(web_search_enabled=True),
        language="en",
    )

    child_registry = runner._child_registry("QualityReview")
    child_tool_names = {tool.name for tool in child_registry.get_tools_for_skill(None)}

    assert child_tool_names == {
        "analyze_image",
        "capture_artifact_evidence",
        "glob_files",
        "grep_files",
        "list_files",
        "read_file",
        "workspace_map",
    }
    assert not {
        "Agent",
        "ask_user",
        "edit_file",
        "write_file",
        "exec_command",
        "generate_image",
        "generate_video",
        "publish_output",
        "register_artifact",
        "web_search",
        "fetch_webpage",
    } & child_tool_names


def test_subagent_status_treats_final_text_after_tool_error_as_completed():
    assert HarnessSubagentRunner._status(
        [
            {
                "tool": "grep_files",
                "is_error": True,
                "review": {"outcome": "error"},
            }
        ],
        assistant_text='{"review_id":"critique-1"}',
    ) == "completed"


def test_subagent_prompts_follow_requested_language():
    explore = get_subagent_definition("Explore")
    quality = get_subagent_definition("QualityReview")

    assert "只读探索型" in explore.get_system_prompt("zh")
    assert "read-only exploration" in explore.get_system_prompt("en")
    assert "designer、critic、brand、a11y、copy" in quality.get_system_prompt("zh")
    assert "Design Jury" in quality.get_system_prompt("en")


def test_subagent_context_and_tools_follow_parent_language_and_web_search_flag(tmp_path, monkeypatch):
    parent_ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        language="en",
        workspace_root=tmp_path,
    )
    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={"id": "conv-1"},
        parent_context=parent_ctx,
        parent_registry=create_harness_registry(web_search_enabled=False),
        language="en",
    )

    child_ctx = runner._child_context(
        parent_ctx,
        SubagentRequest(
            task_id="sub-inspect-files",
            spec=SubagentTaskSpec(
                description="Inspect files",
                prompt="Inspect files",
                subagent_type="Explore",
            ),
        ),
    )
    child_registry = runner._child_registry("Explore")
    child_tool_names = {tool.name for tool in child_registry.get_tools_for_skill(None)}
    system_prompt = runner._system_prompt("Read-only inspection.", child_registry)

    assert child_ctx.language == "en"
    assert "web_search" not in child_tool_names
    assert "## Subagent Scope" in system_prompt
    assert "Available tools" in system_prompt
    assert "constrained synchronous subagent" in system_prompt
    assert "Current runtime time:" in system_prompt
    assert "Current date:" in system_prompt
    assert "You are Harness Agent, a tool-first engineering agent" not in system_prompt


def test_build_definitions_by_name_rejects_duplicate_names():
    duplicate = SubagentDefinition(
        name="Explore",
        description="Duplicate",
        system_prompt="Duplicate prompt",
    )

    with pytest.raises(ValueError, match="Duplicate subagent definition name: Explore"):
        _build_definitions_by_name((get_subagent_definition("Explore"), duplicate))
