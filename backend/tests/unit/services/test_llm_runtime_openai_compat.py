from __future__ import annotations

from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools.ask_user import AskUserTool
from app.services.agent_harness.capabilities.tools.write_file import WriteFileTool
from app.services.llm_runtime.openai_compat import clean_schema, prepare_tools_for_model

_UNSUPPORTED_SCHEMA_KEYS = (
    "anyOf",
    "any_of",
    "oneOf",
    "allOf",
    "$ref",
    "$defs",
    "definitions",
    "default",
    "title",
    "const",
)


def _walk_for_key(node, target_key: str) -> bool:
    if isinstance(node, dict):
        if target_key in node:
            return True
        return any(_walk_for_key(value, target_key) for value in node.values())
    if isinstance(node, list):
        return any(_walk_for_key(item, target_key) for item in node)
    return False


def _schema_violations(node, path: list[str]) -> list[str]:
    violations: list[str] = []
    if isinstance(node, dict):
        if "properties" in node and isinstance(node["properties"], dict):
            for key, value in node["properties"].items():
                property_path = [*path, "properties", key]
                if not isinstance(value, dict):
                    violations.append(f"non-object property schema at {'.'.join(property_path)}")
                    continue
                if "type" not in value:
                    violations.append(f"missing type at {'.'.join(property_path)}")
                violations.extend(_schema_violations(value, property_path))
        if "items" in node:
            violations.extend(_schema_violations(node["items"], [*path, "items"]))
        for unsupported in _UNSUPPORTED_SCHEMA_KEYS:
            if unsupported in node:
                violations.append(f"unsupported {unsupported} at {'.'.join(path)}")
        for key, value in node.items():
            if key not in {"properties", "items"}:
                violations.extend(_schema_violations(value, [*path, key]))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            violations.extend(_schema_violations(value, [*path, str(index)]))
    return violations


def test_clean_schema_removes_const_from_literal_fields():
    raw_schema = {
        "type": "object",
        "properties": {"kind": {"type": "string", "const": "file"}},
    }

    assert _walk_for_key(raw_schema, "const")

    cleaned_schema = clean_schema(raw_schema)

    assert not _walk_for_key(cleaned_schema, "const")


def test_prepare_tools_for_model_removes_const_from_function_parameters():
    tools = [WriteFileTool().to_api_schema(fmt="openai", language="en")]

    prepared_tools = prepare_tools_for_model("claude-opus-4-7", tools)

    assert prepared_tools is not None
    parameters = prepared_tools[0]["function"]["parameters"]
    assert not _walk_for_key(parameters, "const")


def test_prepare_tools_for_model_normalizes_nullable_nested_property_types():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "resolve_selection",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "object",
                            "properties": {
                                "id": {"type": ["string", "null"]},
                                "confidence": {"type": "number"},
                            },
                            "required": ["confidence"],
                        }
                    },
                    "required": ["skill"],
                },
            },
        }
    ]

    prepared_tools = prepare_tools_for_model("gpt-4.1", tools)

    assert prepared_tools is not None
    skill_id_schema = prepared_tools[0]["function"]["parameters"]["properties"]["skill"]["properties"]["id"]
    assert skill_id_schema["type"] == "string"


def test_prepare_tools_for_model_normalizes_annotation_only_write_file_content():
    tools = [WriteFileTool().to_api_schema(fmt="openai", language="zh")]

    prepared_tools = prepare_tools_for_model("claude-opus-4-7", tools)

    assert prepared_tools is not None
    content_schema = prepared_tools[0]["function"]["parameters"]["properties"]["content"]
    assert content_schema["type"] == "string"
    assert "内容" in content_schema["description"]
    assert "title" not in content_schema
    assert "default" not in content_schema


def test_prepare_tools_for_model_normalizes_choice_question_schema():
    tools = [AskUserTool().to_api_schema(fmt="openai", language="zh")]

    prepared_tools = prepare_tools_for_model("claude-opus-4-7", tools)

    assert prepared_tools is not None
    parameters = prepared_tools[0]["function"]["parameters"]
    question_schema = parameters["properties"]["questions"]["items"]
    assert question_schema["properties"]["question"]["type"] == "string"
    assert question_schema["properties"]["options"]["type"] == "array"
    assert "schema" not in parameters["properties"]
    assert "default_value" not in question_schema["properties"]
    assert _schema_violations(parameters, ["ask_user", "parameters"]) == []


def test_prepare_tools_for_model_normalizes_all_harness_tool_schemas():
    registry = create_harness_registry()
    tools = registry.to_api_schemas(fmt="openai", language="en")

    prepared_tools = prepare_tools_for_model("claude-opus-4-7", tools)

    assert prepared_tools is not None

    violations: list[str] = []

    for tool in prepared_tools:
        function_payload = tool.get("function", {})
        tool_name = function_payload.get("name", "<unknown>")
        parameters = function_payload.get("parameters", {})
        violations.extend(_schema_violations(parameters, [tool_name, "parameters"]))

    assert violations == []
