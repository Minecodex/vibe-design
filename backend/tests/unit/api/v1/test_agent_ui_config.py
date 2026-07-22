import pytest

from app.api.v1.endpoints.harness import get_harness_ui_config
from app.core.config import settings
from app.services.agent_harness import catalog
from app.services.agent_harness.catalog import CatalogSnapshot, SkillSummary


def _skill_summary(skill_id: str, *, canvas_explicit: bool = False) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name=skill_id,
        name_en=skill_id,
        name_zh=skill_id,
        description="",
        description_en="",
        description_zh="",
        icon="",
        color="",
        triggers=[],
        mode="image",
        surface=None,
        platform=None,
        scenario=None,
        artifact_mode="image",
        default_for=[],
        featured=None,
        preview_type="none",
        preview_entry=None,
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider=None,
        protocol_family=None,
        protocol_metadata={},
        capabilities={"canvas_explicit": canvas_explicit, "phase_enabled": True},
        example_prompt=None,
        has_example_html=False,
    )


@pytest.fixture(autouse=True)
def _agent_catalog_for_ui_config(monkeypatch):
    skills = [
        _skill_summary("brand_strategy_architect", canvas_explicit=True),
        _skill_summary("logo", canvas_explicit=True),
        _skill_summary("menswear-ecommerce-hero", canvas_explicit=True),
        _skill_summary("vi-design-guide", canvas_explicit=True),
        _skill_summary("web", canvas_explicit=False),
    ]
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(kind="skills", source_digest="test-skills", generated_at=1, items=skills),
    )
    monkeypatch.setattr(
        catalog,
        "_LOCAL_DESIGN_SYSTEM_SNAPSHOT",
        CatalogSnapshot(kind="design-systems", source_digest="test-design", generated_at=1, items=[]),
    )


def test_agent_hidden_tool_calls_setting_parses_csv(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AGENT_HIDDEN_TOOL_CALLS",
        "lc_read_skill_file, lc_search_web ,read_internal_doc",
    )

    assert settings.agent_hidden_tool_calls == [
        "lc_read_skill_file",
        "lc_search_web",
        "read_internal_doc",
    ]


def test_agent_hidden_tool_calls_empty_by_default(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_HIDDEN_TOOL_CALLS", "")

    assert settings.agent_hidden_tool_calls == []


@pytest.mark.asyncio
async def test_get_harness_ui_config_returns_hidden_tool_calls(monkeypatch):
    monkeypatch.setattr(
        settings,
        "AGENT_HIDDEN_TOOL_CALLS",
        "lc_read_skill_file, lc_search_web ,read_internal_doc",
    )

    response = await get_harness_ui_config()

    assert response.hidden_tool_calls == [
        "lc_read_skill_file",
        "lc_search_web",
        "read_internal_doc",
    ]


@pytest.mark.asyncio
async def test_get_harness_ui_config_returns_canvas_skill_policy():
    response = await get_harness_ui_config()

    assert response.canvas_default_skill_id == "design_workflow"
    assert response.canvas_explicit_skill_ids == [
        "brand_strategy_architect",
        "logo",
        "menswear-ecommerce-hero",
        "vi-design-guide",
    ]
