from app.services.agent_harness.capabilities.skills import get_skill, list_skills_for_mode
from app.services.agent_harness.capabilities.skills.catalog_service import build_skill_catalog_payload


def test_first_phase_classification_marks_supported_hidden_and_disabled_skills() -> None:
    html_ppt_taste = get_skill("html-ppt-taste-brutalist")
    tweaks = get_skill("tweaks")
    hyperframes = get_skill("hyperframes")
    social_media_matrix = get_skill("social-media-matrix-tracker-template")

    assert html_ppt_taste is not None
    assert html_ppt_taste.artifact_mode == "slides"
    assert html_ppt_taste.mode == "deck"
    assert html_ppt_taste.execution_strategy == "template_driven_deck"
    assert html_ppt_taste.runtime_capabilities["rollout_state"] == "selectable"
    assert html_ppt_taste.runtime_capabilities["selection_enabled"] is True

    assert tweaks is not None
    assert tweaks.runtime_capabilities["rollout_state"] == "loaded_hidden"
    assert tweaks.runtime_capabilities["semantic_kind"] == "functional"
    assert tweaks.runtime_capabilities["helper_eligible"] is True
    assert tweaks.runtime_capabilities["home_visible"] is False
    assert tweaks.runtime_capabilities["selection_enabled"] is False

    assert hyperframes is not None
    assert hyperframes.runtime_capabilities["rollout_state"] == "disabled"
    assert hyperframes.runtime_capabilities["phase_enabled"] is False
    assert hyperframes.runtime_capabilities["helper_eligible"] is False
    assert hyperframes.runtime_capabilities["classification_notes"] == "phase_one_disabled"

    assert social_media_matrix is not None
    assert social_media_matrix.artifact_mode == "web"
    assert social_media_matrix.mode == "template"
    assert social_media_matrix.runtime_capabilities["rollout_state"] == "loaded_hidden"
    assert social_media_matrix.runtime_capabilities["home_visible"] is False
    assert social_media_matrix.runtime_capabilities["selection_enabled"] is False


def test_mode_lists_can_filter_for_selectable_and_home_visible_skills() -> None:
    all_slide_skills = {skill.id for skill in list_skills_for_mode("slides")}
    selectable_slide_skills = {skill.id for skill in list_skills_for_mode("slides", selectable_only=True)}
    home_visible_slide_skills = {skill.id for skill in list_skills_for_mode("slides", home_visible_only=True)}

    assert "hyperframes" not in selectable_slide_skills
    assert "hyperframes" not in home_visible_slide_skills
    assert "html-ppt" in selectable_slide_skills
    assert selectable_slide_skills == home_visible_slide_skills


def test_web_mode_hides_non_design_skills_from_home_surface() -> None:
    all_web_skills = {skill.id for skill in list_skills_for_mode("web")}
    home_visible_web_skills = {skill.id for skill in list_skills_for_mode("web", home_visible_only=True)}

    assert "web-prototype" in home_visible_web_skills
    assert "kami-landing" in home_visible_web_skills
    assert "dashboard" in home_visible_web_skills

    assert "blog-post" in all_web_skills
    assert "blog-post" not in home_visible_web_skills
    assert "clinical-case-report" not in home_visible_web_skills
    assert "github-dashboard" not in home_visible_web_skills
    assert "live-dashboard" not in home_visible_web_skills
    assert "orbit-github" not in home_visible_web_skills
    assert "social-carousel" not in home_visible_web_skills


def test_skill_catalog_payload_exposes_rollout_flags() -> None:
    payload = {item["id"]: item for item in build_skill_catalog_payload()}

    tweaks = payload["tweaks"]
    hyperframes = payload["hyperframes"]
    github_dashboard = payload["github-dashboard"]
    design_workflow = payload["design_workflow"]
    pptx = payload["pptx"]

    assert tweaks["capabilities"]["rollout_state"] == "loaded_hidden"
    assert tweaks["capabilities"]["selection_enabled"] is False
    assert tweaks["capabilities"]["helper_eligible"] is True
    assert hyperframes["capabilities"]["rollout_state"] == "disabled"
    assert hyperframes["capabilities"]["phase_enabled"] is False
    assert github_dashboard["capabilities"]["rollout_state"] == "loaded_hidden"
    assert github_dashboard["capabilities"]["home_visible"] is False
    assert github_dashboard["capabilities"]["selection_enabled"] is False
    assert github_dashboard["capabilities"]["helper_eligible"] is False
    assert design_workflow["capabilities"]["canvas_only"] is True
    assert design_workflow["capabilities"]["canvas_default"] is True
    assert pptx["capabilities"]["default_route_for"] == "slides"
