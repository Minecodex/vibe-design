from __future__ import annotations

import json

import pytest

from app.services.agent_harness.capabilities.tools._internal.json_content import (
    JsonContentError,
    normalize_json_content,
    serialize_jsonl_content,
)


def test_json_normalizer_serializes_objects_and_arrays_as_documents() -> None:
    object_result = normalize_json_content({"name": "Harness", "ok": True})
    array_result = normalize_json_content([{"step": 1}, {"step": 2}])

    assert json.loads(object_result.text) == {"name": "Harness", "ok": True}
    assert json.loads(array_result.text) == [{"step": 1}, {"step": 2}]
    assert object_result.metadata["json_content_shape"] == "object"
    assert array_result.metadata["json_content_shape"] == "array"


def test_json_normalizer_parses_object_and_array_strings_without_double_encoding() -> None:
    object_result = normalize_json_content('{"template_path":"project/template.html"}')
    array_result = normalize_json_content('[{"path":"project/a.txt"}]')

    assert json.loads(object_result.text) == {"template_path": "project/template.html"}
    assert json.loads(array_result.text) == [{"path": "project/a.txt"}]
    assert object_result.metadata["json_normalization"] == "parsed_json_string"
    assert array_result.metadata["json_normalization"] == "parsed_json_string"


def test_json_normalizer_rejects_invalid_json_like_strings() -> None:
    with pytest.raises(JsonContentError) as exc:
        normalize_json_content('{"template_path": "project/template.html"')

    assert "kind=json" in str(exc.value)
    assert "valid JSON object or array" in str(exc.value)


def test_json_normalizer_rejects_scalar_strings_without_explicit_opt_in() -> None:
    with pytest.raises(JsonContentError) as exc:
        normalize_json_content('"just a string"')

    assert "JSON scalar" in str(exc.value)
    assert "allow_json_scalar" in str(exc.value)


def test_json_normalizer_allows_scalar_strings_with_explicit_opt_in() -> None:
    result = normalize_json_content('"just a string"', allow_json_scalar=True)

    assert json.loads(result.text) == "just a string"
    assert result.metadata["json_content_shape"] == "scalar"


def test_jsonl_serialization_remains_list_based() -> None:
    assert serialize_jsonl_content([{"a": 1}, {"b": 2}]) == '{"a": 1}\n{"b": 2}'

    with pytest.raises(JsonContentError):
        serialize_jsonl_content({"a": 1})
