from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools.ecommerce_product import (
    ECOMMERCE_GENERATION_OPTIONS_KIND,
    PrepareEcommerceGenerationParams,
    PrepareEcommerceGenerationTool,
)
from app.services.agent_harness.capabilities.tools.generate_image import GenerateImageParams
from app.services.agent_harness.core.context import HarnessContext

REMOVED_ECOMMERCE_ANALYSIS_TOOL = "_".join(["analyze", "ecommerce", "realshots"])
REMOVED_GENERATE_IMAGE_FIELDS = [
    "_".join(parts)
    for parts in [
        ["workflow", "intent"],
        ["ecommerce", "generation", "purpose"],
    ]
]


def _ctx(tmp_path: Path) -> HarnessContext:
    return HarnessContext(
        user_id=7,
        conversation_id="conv-ecommerce",
        run_id="run-ecommerce",
        workspace_root=tmp_path,
        image_model="gpt-image-2",
        image_provider="builtin",
    )


def test_prepare_ecommerce_generation_params_have_no_business_fields() -> None:
    schema = PrepareEcommerceGenerationParams.model_json_schema()

    assert schema.get("properties") in ({}, None)
    assert schema.get("required") in (None, [])


@pytest.mark.asyncio
async def test_prepare_ecommerce_generation_returns_options_interaction(tmp_path: Path) -> None:
    result = await PrepareEcommerceGenerationTool().execute(
        PrepareEcommerceGenerationParams(),
        _ctx(tmp_path),
    )

    assert result.is_error is False
    assert json.loads(result.output)["kind"] == ECOMMERCE_GENERATION_OPTIONS_KIND
    assert result.metadata
    assert result.metadata["type"] == "interaction"
    interaction = result.metadata["interaction"]
    assert interaction["kind"] == ECOMMERCE_GENERATION_OPTIONS_KIND
    assert interaction["defaults"]["generation_count"] == 4
    assert interaction["defaults"]["generation_count_min"] == 1
    assert interaction["defaults"]["generation_count_max"] == 6
    assert interaction["defaults"]["enable_background_reference"] is False
    assert interaction["defaults"]["enable_model_reference"] is False
    assert interaction["defaults"]["enable_other_main_image_reference"] is False


def test_ecommerce_registry_has_only_prepare_tool_as_ecommerce_specific_tool() -> None:
    registry = create_harness_registry()

    generic_tool_names = {tool.name for tool in registry.get_tools_for_skill(None)}
    assert "prepare_ecommerce_generation" not in generic_tool_names
    assert REMOVED_ECOMMERCE_ANALYSIS_TOOL not in generic_tool_names

    skill_tool_names = {
        tool.name
        for tool in registry.get_tools_for_skill(
            [
                "analyze_image",
                "generate_image",
                "prepare_ecommerce_generation",
            ]
        )
    }

    assert "prepare_ecommerce_generation" in skill_tool_names
    assert REMOVED_ECOMMERCE_ANALYSIS_TOOL not in skill_tool_names


def test_generate_image_schema_has_no_ecommerce_workflow_fields() -> None:
    properties = GenerateImageParams.model_json_schema().get("properties") or {}

    for removed_field in REMOVED_GENERATE_IMAGE_FIELDS:
        assert removed_field not in properties
