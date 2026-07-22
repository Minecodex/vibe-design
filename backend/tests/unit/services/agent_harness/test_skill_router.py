from __future__ import annotations

from app.services.agent_harness.capabilities.skills import policy_registry, router
from app.services.agent_harness.catalog import CatalogSnapshot, SkillSummary


def _skill(
    skill_id: str,
    *,
    artifact_mode: str = "document",
    selection_enabled: bool = True,
) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name=skill_id,
        name_en=skill_id,
        name_zh=skill_id,
        description=f"{skill_id} skill",
        description_en=f"{skill_id} skill",
        description_zh=f"{skill_id} skill",
        icon="",
        color="",
        triggers=[skill_id],
        mode="prototype",
        surface=None,
        platform=None,
        scenario=None,
        artifact_mode=artifact_mode,
        default_for=[],
        featured=1,
        preview_type="html",
        preview_entry=None,
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider=None,
        protocol_family=None,
        protocol_metadata={},
        capabilities={"selection_enabled": selection_enabled, "phase_enabled": True},
        example_prompt=None,
        has_example_html=False,
    )


def test_resolve_mode_skill_uses_policy_registry_default_when_no_candidates(monkeypatch):
    from app.services.agent_harness import catalog

    monkeypatch.setitem(policy_registry.MODE_DEFAULT_SKILLS, "document", "policy-doc")
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(
            kind="skills",
            source_digest="test",
            generated_at=1,
            items=[_skill("policy-doc", selection_enabled=False)],
        ),
    )

    result = router.resolve_mode_skill(
        artifact_mode="document",
        preferred_skill_id=None,
        prompt="draft a document",
    )

    assert result.skill_id == "policy-doc"
    assert result.source == "fallback_default"


def test_resolve_mode_skill_scores_catalog_summaries_without_full_loader(monkeypatch):
    from app.services.agent_harness import catalog

    def _fail_full_loader(*_args, **_kwargs):
        raise AssertionError("resolve_mode_skill must not load full skills")

    monkeypatch.setattr("app.services.agent_harness.capabilities.skills.get_skill", _fail_full_loader)
    monkeypatch.setattr("app.services.agent_harness.capabilities.skills.list_skills_for_mode", _fail_full_loader)
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(
            kind="skills",
            source_digest="test",
            generated_at=1,
            items=[
                _skill("policy-doc"),
                _skill("research-doc", selection_enabled=True),
            ],
        ),
    )

    result = router.resolve_mode_skill(
        artifact_mode="document",
        preferred_skill_id=None,
        prompt="create a research-doc report",
    )

    assert result.skill_id == "research-doc"
    assert result.source == "auto_routed"
