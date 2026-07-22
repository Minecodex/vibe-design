from app.services.agent_harness.capabilities.skills.policy_registry import (
    default_skill_id_for_artifact_mode,
    resolve_skill_policy,
)


def test_skill_policy_registry_preserves_core_rollout_decisions() -> None:
    html_deck = resolve_skill_policy(
        skill_id="html-ppt-taste-brutalist",
        artifact_mode="slides",
        mode="deck",
    )
    tweaks = resolve_skill_policy(
        skill_id="tweaks",
        artifact_mode=None,
        mode="utility",
    )
    hyperframes = resolve_skill_policy(
        skill_id="hyperframes",
        artifact_mode="video",
        mode="video",
    )
    hidden_template = resolve_skill_policy(
        skill_id="social-media-matrix-tracker-template",
        artifact_mode=None,
        mode="other",
    )

    assert html_deck.artifact_mode == "slides"
    assert html_deck.mode_override == "deck"
    assert html_deck.rollout_state == "selectable"
    assert html_deck.home_visible is True
    assert html_deck.selection_enabled is True

    assert tweaks.rollout_state == "loaded_hidden"
    assert tweaks.semantic_kind == "functional"
    assert tweaks.helper_eligible is True
    assert tweaks.home_visible is False
    assert tweaks.selection_enabled is False

    assert hyperframes.rollout_state == "disabled"
    assert hyperframes.phase_enabled is False
    assert hyperframes.home_visible is False

    assert hidden_template.artifact_mode == "web"
    assert hidden_template.mode_override == "template"
    assert hidden_template.rollout_state == "loaded_hidden"
    assert hidden_template.home_visible is False


def test_skill_policy_registry_preserves_canvas_and_default_route_decisions() -> None:
    design_workflow = resolve_skill_policy(
        skill_id="design_workflow",
        artifact_mode=None,
        mode="utility",
    )
    logo = resolve_skill_policy(
        skill_id="logo",
        artifact_mode="image",
        mode="image",
    )
    product_hero = resolve_skill_policy(
        skill_id="menswear-ecommerce-hero",
        artifact_mode="image",
        mode="image",
    )
    image_poster = resolve_skill_policy(
        skill_id="image-poster",
        artifact_mode="image",
        mode="image",
    )
    pptx = resolve_skill_policy(
        skill_id="pptx",
        artifact_mode="slides",
        mode="document",
    )

    assert design_workflow.canvas_only is True
    assert design_workflow.canvas_default is True
    assert design_workflow.home_visible is False

    assert logo.canvas_only is True
    assert logo.canvas_explicit is True
    assert logo.home_visible is False

    assert product_hero.canvas_only is True
    assert product_hero.canvas_explicit is True
    assert product_hero.home_visible is False

    legacy_product_hero = resolve_skill_policy(
        skill_id="product-hero",
        artifact_mode="image",
        mode="image",
    )
    assert legacy_product_hero.skill_id == "menswear-ecommerce-hero"
    assert legacy_product_hero.canvas_explicit is True

    assert image_poster.canvas_only is False
    assert image_poster.home_visible is False
    assert image_poster.selection_enabled is False

    assert pptx.default_route_for == "slides"
    assert pptx.default_route_priority > 0
    assert default_skill_id_for_artifact_mode("slides") == "pptx"
