from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result, review_user_visible_summary
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult


def test_successful_validate_output_review_has_no_failure_guidance():
    result = ToolResult(
        output='{"file_path": ".work/file_outputs/new_abc/output.xlsx", "status": "passed"}',
        metadata={
            "file_path": ".work/file_outputs/new_abc/output.xlsx",
            "status": "passed",
        },
    )

    review = review_tool_result(
        "validate_output",
        {"path": ".work/file_outputs/new_abc/output.xlsx", "kind": "xlsx"},
        result,
    )

    assert review["outcome"] == "success"
    assert review["root_cause_hint"] is None
    assert review["required_next_action"] is None


def test_preflight_path_outside_workspace_gets_targeted_guidance():
    # Mirrors preflight _blocked() metadata: denied + failure_kind from reason_code.
    result = ToolResult(
        output="Preflight blocked this command. Command references a path outside the workspace.",
        is_error=True,
        metadata={
            "status": "blocked",
            "reason": "path_outside_workspace",
            "failure_kind": "path_outside_workspace",
            "denied": True,
        },
    )

    review = review_tool_result(
        "exec_command",
        {"command": "npx tsx ../skill/scripts/compose.ts", "base": "work"},
        result,
    )

    assert review["outcome"] == "error"
    assert review["failure_kind"] == "path_outside_workspace"
    # Targeted guidance instead of the generic "The tool failed." fallback.
    assert review["required_next_action"]
    assert "unsafe path" in (review["required_next_action"] or "").lower() or "workspace boundary" in (
        review["root_cause_hint"] or ""
    ).lower()


def test_successful_shell_read_does_not_trigger_low_progress_recovery():
    result = ToolResult(output="[exit code: 0]\n[stdout]\nhello", metadata={"stdout": "hello", "exit_code": 0})
    review = review_tool_result(
        "exec_command",
        {"command": "cat /tmp/doc.txt"},
        result,
    )
    assert review["outcome"] == "success"
    assert review["no_progress_signature"] is None
    assert review["required_next_action"] is None


def test_completed_job_install_command_is_not_flagged_as_low_progress_success():
    result = ToolResult(output="[exit code: 0]\n[stdout]\ninstalled", metadata={"stdout": "installed", "exit_code": 0})
    review = review_tool_result(
        "exec_command",
        {"command": "npm install pptxgenjs"},
        result,
    )

    assert review["outcome"] == "success"
    assert review["no_progress_signature"] is None
    assert review["required_next_action"] is None


def test_repeated_read_file_success_is_flagged_as_low_progress():
    result = ToolResult(
        output="# template",
        metadata={
            "path": "skill/assets/template.html",
            "content": "# template",
            "repeated_read": True,
            "unchanged": True,
        },
    )

    review = review_tool_result(
        "read_file",
        {"file_path": "assets/template.html", "base": "skill"},
        result,
    )

    assert review["outcome"] == "success"
    assert review["failure_kind"] == "no_progress"
    assert review["no_progress_signature"] == "read_file_repeat:skill/assets/template.html"
    assert review["required_next_action"] == "Do not read the same unchanged file again. Use the latest contents to take a different concrete next step."


def test_different_read_file_window_is_not_flagged_as_low_progress():
    result = ToolResult(
        output="[read_file window: lines 223-447 of 447]\ncontent",
        metadata={
            "path": "skill/schema.ts",
            "content": "content",
            "repeated_read": True,
            "unchanged": False,
            "offset": 222,
            "limit": 260,
        },
    )

    review = review_tool_result(
        "read_file",
        {"file_path": "schema.ts", "base": "skill", "offset": 222, "limit": 260},
        result,
    )

    assert review["outcome"] == "success"
    assert review["failure_kind"] is None
    assert review["no_progress_signature"] is None


def test_workspace_map_success_is_low_signal_no_progress():
    result = ToolResult(output='{"root":"CONVERSATION_DIR"}', metadata={"root": "CONVERSATION_DIR"})

    review = review_tool_result("workspace_map", {}, result)

    assert review["outcome"] == "success"
    assert review["failure_kind"] == "no_progress"
    assert review["no_progress_signature"] == "workspace_map:consulted"
    assert review["no_progress_group"] == "low_signal_exploration"
    assert review["recovery_hint"]["avoid_tools"] == ["workspace_map", "list_files"]


def test_empty_list_files_success_is_low_signal_no_progress():
    result = ToolResult(
        output='{"entries":[],"entry_count":0}',
        metadata={"entries": [], "entry_count": 0, "root": "project", "recursive": False},
    )

    review = review_tool_result("list_files", {"base": "project", "path": "project", "recursive": False}, result)

    assert review["outcome"] == "success"
    assert review["failure_kind"] == "no_progress"
    assert review["no_progress_signature"] == "list_files_empty:project:project:recursive=false"
    assert review["no_progress_group"] == "low_signal_exploration"


def test_security_boundary_failure_is_classified_as_path_outside_workspace():
    result = ToolResult(
        output="Text project files must live under project/. Use a project path like project/foo.py, not ../secret.txt.",
        is_error=True,
    )
    review = review_tool_result("write_file", {"path": "../secret.txt"}, result)

    assert review["failure_kind"] == "path_outside_workspace"


def test_html_dependency_failure_provides_copy_then_reference_guidance():
    result = ToolResult(
        output=(
            "html dependency may not reference .skill_runtime: .skill_runtime/landing/assets/base.css. "
            "Final HTML must not reference skill-runtime files directly; copy the required files from SKILL_DIR "
            "into the candidate directory under work/, then reference those copied files with candidate-relative paths."
        ),
        is_error=True,
    )

    review = review_tool_result("write_file", {"file_path": "site/index.html"}, result)

    assert review["failure_kind"] == "html_dependency_error"
    assert review["root_cause_hint"] == "The HTML candidate references local dependencies that are not valid publishable bundle members yet."
    assert "copy the required files from the read-only skill/ or references/ roots" in (review["required_next_action"] or "")
    assert review["recovery_hint"]["preferred_tools"] == ["exec_command", "write_file", "register_artifact", "publish_output"]


def test_missing_python_dependency_failure_provides_patch_then_rerun_guidance():
    result = ToolResult(
        output=(
            "[exit code: 1]\n[stderr]\n"
            "Traceback (most recent call last):\n"
            "  File \"/app/work/generate_population_data.py\", line 2, in <module>\n"
            "    import matplotlib.pyplot as plt\n"
            "ModuleNotFoundError: No module named 'matplotlib'\n"
        ),
        is_error=True,
        metadata={
            "semantic_error_type": "Traceback",
            "failure_kind": "missing_dependency",
        },
    )

    review = review_tool_result("exec_command", {"command": "python generate_population_data.py"}, result)

    assert review["failure_kind"] == "missing_dependency"
    assert review["root_cause_hint"] == "The current runtime is missing a dependency required by the generated command."
    assert "remove the unnecessary dependency" in (review["required_next_action"] or "")
    assert review["recovery_hint"]["preferred_tools"] == ["read_file", "edit_file", "exec_command"]


def test_missing_shell_tool_failure_is_runtime_dependency_missing():
    result = ToolResult(
        output="[exit code: 127]\n[stderr]\n/bin/sh: 1: tsx: not found",
        is_error=True,
        metadata={"exit_code": 127, "stderr": "/bin/sh: 1: tsx: not found"},
    )

    review = review_tool_result("exec_command", {"command": "tsx scripts/compose.ts inputs.json out/index.html"}, result)

    assert review["failure_kind"] == "runtime_dependency_missing"
    assert "available execution strategy" in (review["required_next_action"] or "")
    assert review["recovery_hint"]["avoid_tools"] == ["exec_command"]


def test_prepared_composer_undefined_property_remains_generic_command_failure():
    result = ToolResult(
        output=(
            "[exit code: 1]\n[stderr]\n"
            "TypeError: Cannot read properties of undefined (reading 'map')\n"
            "    at renderHero (scripts/compose.ts:189:30)\n"
        ),
        is_error=True,
        metadata={"stderr": "Cannot read properties of undefined (reading 'map')\n    at scripts/compose.ts:189:30"},
    )

    review = review_tool_result("exec_command", {"command": "node scripts/compose.ts inputs.json out/index.html"}, result)

    assert review["failure_kind"] == "unknown_failure"
    assert review["required_next_action"] == "Use the error output to choose a different concrete next action."


def test_old_text_patch_failure_is_classified_from_output_text():
    result = ToolResult(
        output="old_text for edit #1 was not found in project/index.html",
        is_error=True,
    )

    review = review_tool_result("edit_file", {"path": "index.html"}, result)

    assert review["failure_kind"] == "patch_target_not_found"
    assert review["recovery_hint"]["preferred_tools"] == ["read_file", "edit_file"]


def test_policy_block_failure_is_distinct_from_execution_failure():
    result = ToolResult(
        output="Quoted or embedded newlines in shell commands are blocked.",
        is_error=True,
        metadata={"denied": True, "failure_kind": "dangerous_command", "risk_tags": ["shell_obfuscation"]},
    )

    review = review_tool_result("exec_command", {"command": "printf 'a\nb'"}, result)

    assert review["failure_kind"] == "command_policy_blocked"
    assert "Do not retry the blocked shell form" in (review["required_next_action"] or "")


def test_protocol_write_effect_policy_failure_is_distinct():
    result = ToolResult(
        output="references is read-only",
        is_error=True,
        metadata={
            "failure_kind": "readonly_input_write",
            "protocol_failure": {"failure_kind": "readonly_input_write"},
        },
    )

    review = review_tool_result("exec_command", {"command": "npm install"}, result)

    assert review["failure_kind"] == "write_effect_policy"
    assert "allowed write root" in (review["required_next_action"] or "")


def test_protocol_failure_reviewer_reuses_tool_guidance_for_recovery():
    result = ToolResult(
        output="协议要求在 deck-prepared 内登记和发布，不能发布 design-trends-2025/index.html。",
        is_error=True,
        metadata={
            "failure_kind": "artifact_work_root_mismatch",
            "protocol_failure": {
                "failure_kind": "artifact_work_root_mismatch",
                "message": "当前 manifest entry 不在 artifact work directory 内。",
                "allowed_artifact_work_root": "deck-prepared",
                "suggested_next_tool": "register_artifact",
                "suggested_action": "请把最终文件放回 deck-prepared 后重新 register_artifact。",
                "protocol_family": "manifest",
            },
            "recovery_hint": {
                "instruction": "回到 deck-prepared 继续，不要登记平行目录。",
                "constraints": ["不要继续使用 design-trends-2025/index.html 作为交付入口。"],
                "preferred_tools": ["read_file", "edit_file", "register_artifact", "publish_output"],
                "avoid_tools": ["write_file"],
            },
        },
    )

    review = review_tool_result(
        "publish_output",
        {},
        result,
    )

    assert review["failure_kind"] == "artifact_work_root_mismatch"
    assert review["required_next_action"] == "回到 deck-prepared 继续，不要登记平行目录。"
    assert review["recovery_hint"]["preferred_tools"] == ["read_file", "edit_file", "register_artifact", "publish_output"]
    assert review["recovery_hint"]["avoid_tools"] == ["write_file"]


def test_web_search_image_excerpt_keeps_local_image_and_source_url():
    result = ToolResult(
        output='{"provider":"duckduckgo","search_type":"image"}',
        metadata={
            "query": "Nietzsche portrait",
            "search_type": "image",
            "results": [
                {
                    "title": "Nietzsche portrait",
                    "image_url": "assets/references/web_image_001/original.jpg",
                    "local_image_path": "assets/references/web_image_001/original.jpg",
                    "source_url": "https://example.com/nietzsche",
                    "width": 1024,
                    "height": 1024,
                }
            ],
        },
    )

    review = review_tool_result(
        "web_search",
        {"query": "Nietzsche portrait", "search_type": "image"},
        result,
    )

    assert '"local_image_path": "assets/references/web_image_001/original.jpg"' in review["output_excerpt"]
    assert '"source_url": "https://example.com/nietzsche"' in review["output_excerpt"]


def test_phase_tool_blocked_review_is_marked_internal_only():
    result = ToolResult(
        output="当前仍处于计划修订阶段，不能执行该工具。请调用 update_planning_draft 或 request_plan_approval 修订计划。",
        metadata={
            "noop": True,
            "phase_tool_blocked": True,
            "blocked_tool": "exec_command",
            "phase": "revising_plan",
        },
    )

    review = review_tool_result(
        "exec_command",
        {"command": "python generate.py"},
        result,
    )

    assert review["outcome"] == "noop"
    assert review["failure_kind"] == "phase_tool_blocked"
    assert review["user_visible"] is False
    assert review["recovery_hint"]["preferred_tools"] == ["update_planning_draft", "request_plan_approval", "read_file", "fetch_webpage"]
    assert review_user_visible_summary(review) is None


def test_revision_search_budget_exhausted_review_exposes_structured_failure_and_recovery_hint():
    result = ToolResult(
        output="计划更新或制作阶段，联网搜索最多调用 3 次。",
        metadata={
            "noop": True,
            "phase": "revising_plan",
            "failure_kind": "revision_search_budget_exhausted",
            "recovery_hint": {
                "instruction": "Continue revising with known information instead of expanding the search scope.",
                "preferred_tools": ["fetch_webpage", "update_planning_draft"],
                "avoid_tools": ["web_search"],
            },
        },
    )

    review = review_tool_result(
        "web_search",
        {"query": "Japan births"},
        result,
    )

    assert review["failure"]["failure_kind"] == "revision_search_budget_exhausted"
    assert review["failure"]["failure_stage"] == "revising_plan"
    assert review["failure"]["summary"] == review["summary"]
    assert '"results": []' in review["failure"]["summary"]
    assert review["failure"]["recovery_hint"]["avoid_tools"] == ["web_search"]

