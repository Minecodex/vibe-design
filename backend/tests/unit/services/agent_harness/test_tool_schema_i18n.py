from app.services.agent_harness.capabilities.tools import create_harness_registry


def _tool_schema_by_name(language: str) -> dict[str, dict]:
    registry = create_harness_registry()
    schemas = registry.to_api_schemas(language=language)
    return {schema["function"]["name"]: schema["function"] for schema in schemas}


def test_default_harness_tool_schemas_use_minimal_set():
    tool_names = set(_tool_schema_by_name("zh"))

    assert tool_names == {
        "analyze_image",
        "edit_file",
        "ask_user",
        "exec_command",
        "fetch_webpage",
        "generate_image",
        "generate_video",
        "glob_files",
        "grep_files",
        "list_files",
        "publish_output",
        "read_file",
        "register_artifact",
        "search_harness_history",
        "Agent",
        "request_plan_approval",
        "update_execution_progress",
        "update_planning_draft",
        "web_search",
        "workspace_map",
        "write_file",
    }
    assert "list_available_assets" not in tool_names
    assert "validate_artifact" not in tool_names
    assert "validate_file" not in tool_names
    assert "artifact_session" not in tool_names
    assert "shell_command" not in tool_names
    assert "write_structured_file" not in tool_names
    assert "spawn_subagent" not in tool_names
    assert "capture_artifact_evidence" not in tool_names


def test_tool_schemas_localize_descriptions_and_parameter_help():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    assert zh_tools["ask_user"]["description"] != en_tools["ask_user"]["description"]
    assert "向用户" in zh_tools["ask_user"]["description"]
    assert "ask_user 只承接用户决策" in zh_tools["ask_user"]["description"]
    assert "必须先用普通 assistant 正文展示完整内容" in zh_tools["ask_user"]["description"]
    assert "Ask the user" in en_tools["ask_user"]["description"]
    assert "only captures the user's decision" in en_tools["ask_user"]["description"]
    assert "normal assistant text before calling ask_user" in en_tools["ask_user"]["description"]

    zh_questions = zh_tools["ask_user"]["parameters"]["properties"]["questions"]["description"]
    en_questions = en_tools["ask_user"]["parameters"]["properties"]["questions"]["description"]
    zh_title = zh_tools["ask_user"]["parameters"]["properties"]["title"]["description"]
    zh_description = zh_tools["ask_user"]["parameters"]["properties"]["description"]["description"]
    en_description = en_tools["ask_user"]["parameters"]["properties"]["description"]["description"]
    en_answers = en_tools["ask_user"]["parameters"]["properties"]["answers"]["description"]
    assert "问题数组" in zh_questions
    assert "questions" in en_questions.lower()
    assert "交互卡标题" in zh_title
    assert "不得承载方案、简报、阶段成果或选择依据" in zh_description
    assert "must not carry proposals, briefs, stage results" in en_description
    assert "prior answers" in en_answers


def test_tool_schemas_localize_publish_and_plan_fields():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    zh_entry = zh_tools["register_artifact"]["parameters"]["properties"]["entry"]["description"]
    en_entry = en_tools["register_artifact"]["parameters"]["properties"]["entry"]["description"]
    zh_user_plan = zh_tools["request_plan_approval"]["parameters"]["properties"]["user_plan"]["description"]
    en_user_plan = en_tools["request_plan_approval"]["parameters"]["properties"]["user_plan"]["description"]
    # publish_output takes no parameters; localization lives on the description.
    zh_publish = zh_tools["publish_output"]["description"]
    en_publish = en_tools["publish_output"]["description"]
    assert "最终主文件" in zh_entry
    assert "primary file" in en_entry.lower()
    assert "manifest" in zh_publish
    assert "manifest" in en_publish.lower()
    assert "可选展示与文件元数据" in zh_user_plan
    assert "metadata" in en_user_plan.lower()


def test_file_tool_schemas_describe_safe_editing_and_serialization():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    zh_write_description = zh_tools["write_file"]["description"]
    en_write_description = en_tools["write_file"]["description"]
    zh_edit_description = zh_tools["edit_file"]["description"]
    en_edit_description = en_tools["edit_file"]["description"]

    assert "工作区" in zh_write_description
    assert "workspace" in en_write_description.lower()
    assert "替换" in zh_edit_description
    assert "replacement" in en_edit_description.lower()


def test_path_sensitive_tool_schemas_explain_workspace_paths():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    assert "相对该 base" in zh_tools["write_file"]["parameters"]["properties"]["path"]["description"]
    assert "relative to that base" in en_tools["read_file"]["parameters"]["properties"]["path"]["description"]
    assert "CONVERSATION_DIR/project" in zh_tools["exec_command"]["description"]
    assert "python foo.py" in en_tools["exec_command"]["description"]
    assert "python project/foo.py" in en_tools["exec_command"]["description"]
    # publish_output takes no parameters; it documents the manifest entry in its description.
    assert "artifact_manifest.entry" in zh_tools["publish_output"]["description"]
    assert "artifact_manifest.entry" in en_tools["publish_output"]["description"]
    assert "location" not in zh_tools["read_file"]["parameters"]["properties"]
    assert "location" not in zh_tools["write_file"]["parameters"]["properties"]
    assert "location" not in zh_tools["exec_command"]["parameters"]["properties"]


def test_exec_command_schema_steers_multiline_scripts_to_write_file_first():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    assert "多行脚本" in zh_tools["exec_command"]["description"]
    assert "write_file" in zh_tools["exec_command"]["description"]
    assert "multi-line scripts" in en_tools["exec_command"]["description"]
    assert "write_file" in en_tools["exec_command"]["description"]


def test_all_registered_tools_have_localized_schema_text():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    for tool_name in zh_tools:
        assert zh_tools[tool_name]["description"] != en_tools[tool_name]["description"]

    assert "列出" in zh_tools["list_files"]["description"]
    assert "list" in en_tools["list_files"]["description"].lower()
    assert "glob" in en_tools["glob_files"]["description"].lower()
    assert "正则" in zh_tools["grep_files"]["parameters"]["properties"]["pattern"]["description"]
    assert "Regular expression" in en_tools["grep_files"]["parameters"]["properties"]["pattern"]["description"]
    assert "file_type" in zh_tools["grep_files"]["parameters"]["properties"]
    assert "type" not in zh_tools["grep_files"]["parameters"]["properties"]
    assert "文件类型过滤" in zh_tools["grep_files"]["parameters"]["properties"]["file_type"]["description"]
    assert "file type filter" in en_tools["grep_files"]["parameters"]["properties"]["file_type"]["description"]
    assert "工作区映射" in zh_tools["workspace_map"]["description"]
    assert "workspace map" in en_tools["workspace_map"]["description"].lower()
    assert "文件路径" in zh_tools["write_file"]["parameters"]["properties"]["path"]["description"]
    assert "file path" in en_tools["write_file"]["parameters"]["properties"]["path"]["description"].lower()
    assert "文件内容" in zh_tools["write_file"]["parameters"]["properties"]["content"]["description"]
    assert "file content" in en_tools["write_file"]["parameters"]["properties"]["content"]["description"].lower()
    assert "register_artifact" in zh_tools["publish_output"]["description"]
    assert "register_artifact" in en_tools["publish_output"]["description"]
    assert "supporting_files" in zh_tools["register_artifact"]["description"]
    assert "supporting_files" in en_tools["register_artifact"]["description"]
    assert "搜索类型" in zh_tools["web_search"]["parameters"]["properties"]["search_type"]["description"]
    assert "Search type" in en_tools["web_search"]["parameters"]["properties"]["search_type"]["description"]
    assert "网页地址" in zh_tools["fetch_webpage"]["parameters"]["properties"]["url"]["description"]
    assert "URL" in en_tools["fetch_webpage"]["parameters"]["properties"]["url"]["description"]
    assert "历史上下文" in zh_tools["search_harness_history"]["description"]
    assert "past harness context" in en_tools["search_harness_history"]["description"].lower()
    assert "搜索关键词" in zh_tools["search_harness_history"]["parameters"]["properties"]["query"]["description"]
    assert "Search terms" in en_tools["search_harness_history"]["parameters"]["properties"]["query"]["description"]


def test_agent_schema_exposes_claude_code_style_fields_and_public_profiles_only():
    zh_tools = _tool_schema_by_name("zh")
    agent = zh_tools["Agent"]
    properties = agent["parameters"]["properties"]

    assert set(properties) == {"description", "prompt", "subagent_type"}
    assert properties["subagent_type"]["enum"] == ["general-purpose", "Explore", "Plan"]
    assert "QualityReview" not in properties["subagent_type"]["enum"]


def test_dynamic_generation_parameter_help_follows_language():
    zh_tools = _tool_schema_by_name("zh")
    en_tools = _tool_schema_by_name("en")

    zh_image_ratio = zh_tools["generate_image"]["parameters"]["properties"]["aspect_ratio"]["description"]
    en_image_ratio = en_tools["generate_image"]["parameters"]["properties"]["aspect_ratio"]["description"]
    zh_video_duration = zh_tools["generate_video"]["parameters"]["properties"]["duration"]["description"]
    en_video_duration = en_tools["generate_video"]["parameters"]["properties"]["duration"]["description"]

    assert "当前模型支持" in zh_image_ratio
    assert "Current model supports" in en_image_ratio
    assert "视频时长" in zh_video_duration
    assert "Video duration" in en_video_duration


def test_web_search_tool_schema_is_hidden_by_default_and_visible_when_enabled():
    disabled_registry = create_harness_registry(web_search_enabled=False)
    disabled_names = {
        schema["function"]["name"]
        for schema in disabled_registry.to_api_schemas(language="zh")
    }
    enabled_registry = create_harness_registry(web_search_enabled=True)
    enabled_names = {
        schema["function"]["name"]
        for schema in enabled_registry.to_api_schemas(language="zh")
    }

    assert "web_search" not in disabled_names
    assert "web_search" in enabled_names
