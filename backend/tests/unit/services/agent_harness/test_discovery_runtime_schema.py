import pytest

from app.services.agent_harness.authoring.planning import discovery_runtime
from app.services.agent_harness.authoring.planning.discovery_runtime import (
    _DiscoveryModelResult,
    _call_discovery_schema_model,
    _validate_generated_quick_brief_schema,
    generate_quick_brief_schema,
)
from app.services.agent_harness.prompt_runtime import Phase, PromptMode, PromptRuntime, TurnSpec


def _base_field(index: int) -> dict:
    return {
        "id": f"field_{index}",
        "label": f"Field {index}",
        "type": "text",
        "required": False,
    }


def test_quick_brief_schema_allows_twelve_fields_and_truncates_extra_fields():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief",
            "submit_label": "Submit",
            "fields": [_base_field(index) for index in range(1, 15)],
        }
    )

    assert errors == []
    assert schema is not None
    assert len(schema["fields"]) == 12
    assert schema["fields"][-1]["id"] == "field_12"


def test_quick_brief_schema_normalizes_model_output_without_retrying_for_safe_fields():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief " + ("x" * 200),
            "description": "d" * 1000,
            "submitLabel": "Submit " + ("x" * 100),
            "fields": [
                {
                    "id": "Slide Count",
                    "label": "Slide Count " + ("x" * 200),
                    "type": "select",
                    "required": True,
                    "options": [
                        {"label": "5 to 8 slides"},
                        {"label": "9 to 12 slides", "value": "9_12"},
                    ],
                },
                {
                    "id": "audience",
                    "label": "Audience",
                    "type": "text",
                    "required": True,
                },
                {
                    "id": "tone",
                    "label": "Tone",
                    "type": "radio",
                    "required": True,
                    "defaultValue": "Professional",
                    "options": [
                        {"label": "Professional", "value": "professional"},
                        {"label": "Playful", "value": "playful"},
                    ],
                },
            ],
        }
    )

    assert errors == []
    assert schema is not None
    assert schema["title"].endswith("x" * 200)
    assert schema["description"] == "d" * 1000
    assert schema["submit_label"].endswith("x" * 100)
    assert schema["fields"][0]["id"] == "slide_count"
    assert schema["fields"][0]["options"][0]["value"] == "5_to_8_slides"
    assert schema["fields"][0]["default_value"] == "5_to_8_slides"
    assert schema["fields"][1]["default_value"] == "Audience"
    assert schema["fields"][2]["default_value"] == "professional"


def test_quick_brief_schema_normalizes_string_options():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief",
            "submit_label": "Submit",
            "fields": [
                {
                    "id": "slide_count",
                    "label": "Slide count",
                    "type": "select",
                    "required": True,
                    "options": ["5-8", "10-15"],
                    "default_value": "10-15",
                },
                {"id": "audience", "label": "Audience", "type": "text", "required": False},
            ],
        }
    )

    assert errors == []
    assert schema is not None
    assert schema["fields"][0]["options"] == [
        {"label": "5-8", "value": "5-8"},
        {"label": "10-15", "value": "10-15"},
    ]
    assert schema["fields"][0]["default_value"] == "10-15"


def test_quick_brief_schema_does_not_turn_textarea_placeholder_into_default_value():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief",
            "submit_label": "Submit",
            "fields": [
                {
                    "id": "brand_reference",
                    "label": "Brand reference",
                    "type": "textarea",
                    "required": False,
                    "placeholder": "e.g. one-line intro or 1-2 reference links",
                },
                {
                    "id": "constraints",
                    "label": "Constraints",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "e.g. mobile first",
                },
            ],
        }
    )

    assert errors == []
    assert schema is not None
    assert "default_value" not in schema["fields"][0]
    assert "default_value" not in schema["fields"][1]


def test_quick_brief_schema_accepts_chinese_options_with_generated_values():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief",
            "submit_label": "Submit",
            "fields": [
                {
                    "id": "style_tone",
                    "label": "希望的语气与气质",
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"label": "专业克制", "value": "专业克制"},
                        {"label": "自信现代", "value": "自信现代"},
                        "温暖亲和",
                        {"label": "高级品牌感"},
                    ],
                },
                {"id": "audience", "label": "目标受众", "type": "text", "required": False},
            ],
        }
    )

    assert errors == []
    assert schema is not None
    assert schema["fields"][0]["options"] == [
        {"label": "专业克制", "value": "option_1"},
        {"label": "自信现代", "value": "option_2"},
        {"label": "温暖亲和", "value": "option_3"},
        {"label": "高级品牌感", "value": "option_4"},
    ]
    assert schema["fields"][0]["default_value"] == "option_1"


def test_quick_brief_schema_still_rejects_unsupported_field_type():
    schema, errors = _validate_generated_quick_brief_schema(
        {
            "title": "Quick brief",
            "submit_label": "Submit",
            "fields": [
                {"id": "output", "label": "Output", "type": "dropdown"},
                {"id": "audience", "label": "Audience", "type": "text"},
            ],
        }
    )

    assert schema is None
    assert errors == ["field[0] must include valid id, label, and supported type"]


def test_planning_schema_prompt_contract_matches_validator():
    bundle = PromptRuntime().build_bundle(
        TurnSpec(
            mode=PromptMode.PLANNING_SCHEMA_GENERATION,
            phase=Phase.PLANNING,
            language="en",
            side_payload={"runtime_time": {"now": "2026-05-29T00:00:00Z"}},
        )
    )
    system = bundle.rendered_system

    assert "2 to 12 field objects" in system
    assert '{"label":"Option label","value":"option_value"}' in system
    assert "Do not use other field types such as dropdown, multiselect, number, date, switch, or boolean." in system
    assert '"fields": [' in system
    assert '"type": "select"' in system


@pytest.mark.asyncio
async def test_discovery_schema_model_accepts_tool_call_payload(monkeypatch):
    captured: dict[str, object] = {}

    class FakeProvider:
        async def chat_stream(self, **kwargs):
            captured.update(kwargs)
            yield type(
                "Chunk",
                (),
                {
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": "submit_quick_brief_schema",
                                "arguments": {
                                    "schema": {
                                        "title": "Quick brief",
                                        "submit_label": "Submit",
                                        "fields": [_base_field(1), _base_field(2)],
                                    }
                                },
                            }
                        }
                    ],
                },
            )()

    monkeypatch.setattr(discovery_runtime, "create_harness_model_provider", lambda **_: FakeProvider())

    result = await _call_discovery_schema_model(
        system_prompt="system",
        user_prompt="user",
        model_name="model",
    )

    assert result.payload == {
        "title": "Quick brief",
        "submit_label": "Submit",
        "fields": [_base_field(1), _base_field(2)],
    }
    tools = captured["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "submit_quick_brief_schema"
    assert captured["tool_choice"] == {"type": "function", "function": {"name": "submit_quick_brief_schema"}}


@pytest.mark.asyncio
async def test_discovery_schema_model_accepts_normalized_tool_call_payload(monkeypatch):
    class FakeProvider:
        async def chat_stream(self, **kwargs):
            yield type(
                "Chunk",
                (),
                {
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "submit_quick_brief_schema",
                            "arguments": {
                                "schema": {
                                    "title": "Quick brief",
                                    "submit_label": "Submit",
                                    "fields": [_base_field(1), _base_field(2)],
                                }
                            },
                        }
                    ],
                },
            )()

    monkeypatch.setattr(discovery_runtime, "create_harness_model_provider", lambda **_: FakeProvider())

    result = await _call_discovery_schema_model(
        system_prompt="system",
        user_prompt="user",
        model_name="model",
    )

    assert result.payload == {
        "title": "Quick brief",
        "submit_label": "Submit",
        "fields": [_base_field(1), _base_field(2)],
    }


@pytest.mark.asyncio
async def test_quick_brief_schema_retry_diagnostics_record_validation_errors(monkeypatch):
    calls = [
        _DiscoveryModelResult(
            payload={
                "title": "Quick brief",
                "submit_label": "Submit",
                "fields": [{"id": "output", "label": "Output", "type": "dropdown"}],
            },
            usage={"input_tokens": 1, "output_tokens": 1},
            elapsed_ms=11,
        ),
        _DiscoveryModelResult(
            payload={
                "title": "Quick brief",
                "submit_label": "Submit",
                "fields": [_base_field(1), _base_field(2)],
            },
            usage={"input_tokens": 2, "output_tokens": 2},
            elapsed_ms=22,
        ),
    ]

    async def fake_call(**_kwargs):
        return calls.pop(0)

    monkeypatch.setattr(discovery_runtime, "_call_discovery_schema_model", fake_call)
    diagnostics: list[dict] = []

    schema = await generate_quick_brief_schema(
        conversation={"id": "conv-1"},
        language="en",
        artifact_family="slides",
        skill=object(),
        has_reference_attachments=False,
        retry_diagnostics=diagnostics,
    )

    assert schema["fields"] == [_base_field(1), _base_field(2)]
    assert diagnostics == [
        {
            "attempt": 1,
            "validation_errors": ["fields must contain at least 2 items"],
            "field_shapes": [{"id": "output", "type": "dropdown", "required": None, "option_count": None}],
        }
    ]
