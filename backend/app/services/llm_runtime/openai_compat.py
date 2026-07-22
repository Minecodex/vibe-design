from __future__ import annotations

import copy
import json
import uuid
from typing import Any


def sanitize_openai_content_parts(content: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    for part in content:
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and not str(part.get("text") or "").strip()
        ):
            continue
        sanitized.append(part)
    return sanitized


def tool_call_name(tool_call: dict[str, Any]) -> str:
    function_payload = tool_call.get("function")
    if isinstance(function_payload, dict):
        return str(function_payload.get("name", "") or "")
    return str(tool_call.get("name", "") or "")


def tool_call_arguments(tool_call: dict[str, Any]) -> Any:
    function_payload = tool_call.get("function")
    if isinstance(function_payload, dict) and "arguments" in function_payload:
        return function_payload.get("arguments", "{}")
    return tool_call.get("arguments", "{}")


def to_openai_messages(messages: list[dict[str, Any]], system: str | None) -> list[dict[str, Any]]:
    openai_messages: list[dict[str, Any]] = []

    if system:
        openai_messages.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")

        if role == "system":
            openai_messages.append({"role": "system", "content": msg.get("content", "")})
            continue

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = sanitize_openai_content_parts(content)
                if not content:
                    content = ""
            openai_messages.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant"}
            content = msg.get("content", "")
            if content is None:
                entry["content"] = ""
            elif isinstance(content, str):
                entry["content"] = content
            else:
                entry["content"] = str(content)

            raw_tool_calls = msg.get("tool_calls", [])
            if raw_tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tool_call.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                        "type": "function",
                        "function": {
                            "name": tool_call_name(tool_call),
                            "arguments": (
                                json.dumps(tool_call_arguments(tool_call), ensure_ascii=False)
                                if isinstance(tool_call_arguments(tool_call), dict)
                                else str(tool_call_arguments(tool_call))
                            ),
                        },
                    }
                    for tool_call in raw_tool_calls
                ]
                if not str(entry.get("content") or "").strip():
                    entry.pop("content", None)
            openai_messages.append(entry)
            continue

        if role == "tool":
            openai_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }
            )

    return openai_messages


def resolve_schema_refs(
    node: Any,
    *,
    defs: dict[str, Any],
    definitions: dict[str, Any],
) -> Any:
    if isinstance(node, list):
        return [resolve_schema_refs(item, defs=defs, definitions=definitions) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str):
        target: Any | None = None
        if ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/", 2)[-1])
        elif ref.startswith("#/definitions/"):
            target = definitions.get(ref.split("/", 2)[-1])
        if isinstance(target, dict):
            resolved_target = resolve_schema_refs(copy.deepcopy(target), defs=defs, definitions=definitions)
            merged = dict(resolved_target)
            for key, value in node.items():
                if key == "$ref":
                    continue
                merged[key] = resolve_schema_refs(value, defs=defs, definitions=definitions)
            return merged

    return {
        key: resolve_schema_refs(value, defs=defs, definitions=definitions)
        for key, value in node.items()
    }


def clean_schema_node(node: Any, *, in_properties: bool = False) -> Any:
    if isinstance(node, list):
        return [clean_schema_node(item, in_properties=False) for item in node]
    if not isinstance(node, dict):
        return node

    for any_of_key in ("anyOf", "any_of"):
        if any_of_key in node:
            return {any_of_key: clean_schema_node(node[any_of_key], in_properties=False)}

    skip_keys = {"title", "additionalProperties", "$defs", "definitions", "default", "enum", "const"}
    cleaned: dict[str, Any] = {}
    for key, val in node.items():
        if in_properties:
            cleaned[key] = clean_schema_node(val, in_properties=False)
            continue
        if key in skip_keys:
            continue
        if key == "properties" and isinstance(val, dict):
            cleaned[key] = clean_schema_node(val, in_properties=True)
        else:
            cleaned[key] = clean_schema_node(val, in_properties=False)
    return cleaned


def clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema

    resolved = resolve_schema_refs(
        copy.deepcopy(schema),
        defs=schema.get("$defs", {}) if isinstance(schema.get("$defs"), dict) else {},
        definitions=schema.get("definitions", {}) if isinstance(schema.get("definitions"), dict) else {},
    )
    cleaned = clean_schema_node(resolved)
    return cleaned if isinstance(cleaned, dict) else {}


def normalize_openai_compatible_schema_node(node: Any) -> Any:
    if isinstance(node, list):
        return [normalize_openai_compatible_schema_node(item) for item in node]
    if not isinstance(node, dict):
        return node

    normalized: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            normalized[key] = {
                property_name: normalize_openai_compatible_schema_node(property_schema)
                for property_name, property_schema in value.items()
            }
            continue
        normalized[key] = normalize_openai_compatible_schema_node(value)

    schema_type = normalized.get("type")
    if isinstance(schema_type, list):
        non_null_types = [item for item in schema_type if item != "null"]
        if len(non_null_types) == 1:
            normalized["type"] = non_null_types[0]

    for union_key in ("anyOf", "any_of", "oneOf", "allOf"):
        variants = normalized.get(union_key)
        if not isinstance(variants, list):
            continue

        non_null_variants = [
            variant
            for variant in variants
            if not (isinstance(variant, dict) and variant.get("type") == "null")
        ]

        if len(non_null_variants) == 1 and isinstance(non_null_variants[0], dict):
            merged = dict(non_null_variants[0])
            for key, value in normalized.items():
                if key != union_key:
                    merged.setdefault(key, value)
            normalized = merged
            break

        inferred_union_type: str | None = None
        candidate_types = [
            str(variant.get("type"))
            for variant in non_null_variants
            if isinstance(variant, dict) and isinstance(variant.get("type"), str)
        ]
        for preferred_type in ("object", "array", "string", "integer", "number", "boolean"):
            if preferred_type in candidate_types:
                inferred_union_type = preferred_type
                break
        if inferred_union_type is None:
            inferred_union_type = "string"

        normalized.pop(union_key, None)
        normalized["type"] = inferred_union_type
        break

    if "$ref" in normalized and "type" not in normalized:
        normalized.pop("$ref", None)
        normalized["type"] = "object"

    if "type" not in normalized:
        if isinstance(normalized.get("properties"), dict):
            normalized["type"] = "object"
        elif "items" in normalized:
            normalized["type"] = "array"
        else:
            normalized["type"] = "string"

    for any_of_key in ("anyOf", "any_of"):
        variants = normalized.get(any_of_key)
        if isinstance(variants, list):
            normalized.pop(any_of_key, None)
    for union_key in ("oneOf", "allOf"):
        if union_key in normalized:
            normalized.pop(union_key, None)
    normalized.pop("$ref", None)

    return normalized


def normalize_gemini_schema_node(node: Any) -> Any:
    return normalize_openai_compatible_schema_node(node)


def prepare_openai_compatible_tools(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tools:
        return tools

    prepared_tools: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            prepared_tools.append(tool)
            continue

        cloned = copy.deepcopy(tool)
        function_payload = cloned.get("function")
        if isinstance(function_payload, dict):
            parameters = function_payload.get("parameters")
            if isinstance(parameters, dict):
                function_payload["parameters"] = normalize_openai_compatible_schema_node(
                    clean_schema(parameters)
                )

        input_schema = cloned.get("input_schema")
        if isinstance(input_schema, dict):
            cloned["input_schema"] = normalize_openai_compatible_schema_node(
                clean_schema(input_schema)
            )

        prepared_tools.append(cloned)
    return prepared_tools


def prepare_tools_for_model(model: str, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    return prepare_openai_compatible_tools(tools)
