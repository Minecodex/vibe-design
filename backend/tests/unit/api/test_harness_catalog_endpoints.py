import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.services.agent_harness import catalog
from app.services.agent_harness.catalog import CatalogSnapshot, DesignSystemSummary, SkillSummary


def _skill(skill_id: str = "html-ppt", *, has_example_html: bool = True) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name="HTML PPT",
        name_en="HTML PPT",
        name_zh="网页幻灯片",
        description="Create HTML slide decks.",
        description_en="Create HTML slide decks.",
        description_zh="生成 HTML 幻灯片。",
        icon="presentation",
        color="rose",
        triggers=["deck"],
        mode="deck",
        surface="web",
        platform=None,
        scenario=None,
        artifact_mode="slides",
        default_for=[],
        featured=1,
        preview_type="html",
        preview_entry="index.html",
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider="open_design",
        protocol_family="template_driven_deck",
        protocol_metadata={},
        capabilities={},
        example_prompt=None,
        has_example_html=has_example_html,
    )


def _design(system_id: str = "application") -> DesignSystemSummary:
    return DesignSystemSummary(
        id=system_id,
        title="Application",
        description="Structured product design system.",
        category="Product & SaaS",
        sections=["Color", "Typography"],
        palette=["#FFFFFF", "#111827"],
        preview=None,
        featured=1,
        is_default=False,
        resolver_summary="Structured product design system.",
        resolver_tags=[],
        preferred_for=[],
        avoid_for=[],
        tone="professional",
        density="balanced",
    )


@pytest.mark.asyncio
async def test_list_harness_skills_returns_open_design_metadata(monkeypatch, tmp_path):
    skill_dir = tmp_path / "html-ppt"
    skill_dir.mkdir(parents=True)
    (skill_dir / "example.html").write_text("<!doctype html><html><body>skill example</body></html>", encoding="utf-8")

    async def _skill_catalog_response():
        return (
            json.dumps([
                {
                    "id": "html-ppt",
                    "name": "HTML PPT",
                    "name_en": "HTML PPT",
                    "name_zh": "网页幻灯片",
                    "description": "Create HTML slide decks.",
                    "description_en": "Create HTML slide decks.",
                    "description_zh": "生成 HTML 幻灯片。",
                    "icon": "presentation",
                    "color": "rose",
                    "triggers": ["deck", "slides"],
                    "mode": "deck",
                    "surface": "web",
                    "platform": "desktop",
                    "scenario": "marketing",
                    "artifact_mode": "slides",
                    "default_for": ["slides"],
                    "featured": 1,
                    "preview_type": "html",
                    "preview_entry": "index.html",
                    "primary_output": "html_slides",
                    "parameters": [],
                    "outputs_secondary": [],
                    "metadata_health": {},
                    "protocol_provider": "open_design",
                    "protocol_family": "template_driven_deck",
                    "protocol_metadata": {
                        "execution_strategy": "template_driven_deck",
                        "design_system": {"requires": True, "sections": ["Color", "Typography"]},
                        "craft": {"requires": ["deck-framework"]},
                        "upstream": "open-design/html-ppt",
                    },
                    "capabilities": {"parameters": [], "secondary_outputs": []},
                    "example_prompt": "Build an investor deck",
                    "has_example_html": True,
                }
            ]).encode("utf-8"),
            "digest",
        )

    monkeypatch.setattr("app.services.agent_harness.catalog.skill_catalog_response", _skill_catalog_response)

    result = await harness_endpoint.list_harness_skills()

    assert result.status_code == 200
    assert result.headers["etag"] == '"digest"'
    payload = json.loads(result.body.decode("utf-8"))
    assert len(payload) == 1
    skill = payload[0]
    assert skill["id"] == "html-ppt"
    assert skill["name_zh"] == "网页幻灯片"
    assert skill["name_en"] == "HTML PPT"
    assert skill["description_en"] == "Create HTML slide decks."
    assert skill["description_zh"] == "生成 HTML 幻灯片。"
    assert skill["artifact_mode"] == "slides"
    assert skill["preview_type"] == "html"
    assert skill["preview_entry"] == "index.html"
    assert skill["protocol_provider"] == "open_design"
    assert skill["protocol_metadata"]["design_system"] == {"requires": True, "sections": ["Color", "Typography"]}
    assert skill["protocol_metadata"]["craft"] == {"requires": ["deck-framework"]}
    assert skill["protocol_metadata"]["execution_strategy"] == "template_driven_deck"
    assert skill["protocol_metadata"]["upstream"] == "open-design/html-ppt"
    assert skill["has_example_html"] is True
    assert "execution_strategy" not in skill


@pytest.mark.asyncio
async def test_list_harness_design_systems_returns_catalog(monkeypatch):
    async def _design_system_catalog_response():
        return (
            json.dumps([
                {
                    "id": "application",
                    "title": "Application",
                    "description": "Structured product design system.",
                    "category": "Product & SaaS",
                    "sections": ["Color", "Typography"],
                    "palette": ["#FFFFFF", "#111827"],
                    "preview": None,
                    "featured": 2,
                    "is_default": False,
                }
            ]).encode("utf-8"),
            "digest",
        )

    monkeypatch.setattr("app.services.agent_harness.catalog.design_system_catalog_response", _design_system_catalog_response)

    result = await harness_endpoint.list_harness_design_systems()

    assert result.status_code == 200
    design_system = json.loads(result.body.decode("utf-8"))[0]
    assert design_system["id"] == "application"
    assert design_system["title"] == "Application"
    assert design_system["description"] == "Structured product design system."
    assert design_system["category"] == "Product & SaaS"
    assert design_system["sections"] == ["Color", "Typography"]
    assert design_system["palette"] == ["#FFFFFF", "#111827"]
    assert design_system["featured"] == 2
    assert design_system["is_default"] is False


@pytest.mark.asyncio
async def test_list_harness_skills_returns_503_when_catalog_unavailable(monkeypatch):
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError

    async def _skill_catalog_response():
        raise AgentCatalogUnavailableError("skill catalog missing")

    monkeypatch.setattr("app.services.agent_harness.catalog.skill_catalog_response", _skill_catalog_response)

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.list_harness_skills()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "skill catalog missing"


@pytest.mark.asyncio
async def test_list_harness_design_systems_returns_503_when_catalog_unavailable(monkeypatch):
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError

    async def _design_system_catalog_response():
        raise AgentCatalogUnavailableError("design system catalog missing")

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.design_system_catalog_response",
        _design_system_catalog_response,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.list_harness_design_systems()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "design system catalog missing"


@pytest.mark.asyncio
async def test_get_harness_skill_example_html_returns_root_example(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "html-ppt"
    skill_dir.mkdir(parents=True)
    (skill_dir / "example.html").write_text("<!doctype html><html><body>skill example</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(kind="skills", source_digest="s", generated_at=1, items=[_skill("html-ppt")]),
    )
    monkeypatch.setattr(catalog, "_skills_dir", lambda: skills_root)
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.skills.get_skill",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("example preview must not load full skills")),
    )

    response = await harness_endpoint.get_harness_skill_example_html("html-ppt")

    assert response.status_code == 200
    assert "skill example" in response.body.decode("utf-8")


@pytest.mark.asyncio
async def test_get_harness_skill_file_rejects_path_traversal(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "html-ppt"
    skill_dir.mkdir(parents=True)
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(kind="skills", source_digest="s", generated_at=1, items=[_skill("html-ppt")]),
    )
    monkeypatch.setattr(catalog, "_skills_dir", lambda: skills_root)

    with pytest.raises(HTTPException):
        await harness_endpoint.get_harness_skill_file("html-ppt", "../secret.txt")


@pytest.mark.asyncio
async def test_get_harness_design_system_preview_html_returns_components_html(monkeypatch, tmp_path):
    systems_root = tmp_path / "design_systems"
    system_dir = systems_root / "application"
    system_dir.mkdir(parents=True)
    (system_dir / "components.html").write_text("<!doctype html><html><body>design preview</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        catalog,
        "_LOCAL_DESIGN_SYSTEM_SNAPSHOT",
        CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design("application")]),
    )
    monkeypatch.setattr(catalog, "_design_systems_dir", lambda: systems_root)
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.design_systems.get_design_system",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preview must not load full design systems")),
    )

    response = await harness_endpoint.get_harness_design_system_preview_html("application")

    assert response.status_code == 200
    assert "design preview" in response.body.decode("utf-8")
