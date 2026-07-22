from app.services.agent_harness.capabilities.skills.runtime_profiles import (
    CANVAS_DEFAULT_SKILL_ID,
    CANVAS_EXPLICIT_SKILL_IDS,
    build_skill_runtime_capabilities,
    is_canvas_only_skill,
)


def test_canvas_only_skills_are_hidden_from_home_catalog():
    assert is_canvas_only_skill("design_workflow") is True
    assert is_canvas_only_skill("brand_strategy_architect") is True
    assert is_canvas_only_skill("logo") is True
    assert is_canvas_only_skill("menswear-ecommerce-hero") is True
    assert is_canvas_only_skill("product-hero") is True
    assert is_canvas_only_skill("vi-design-guide") is True
    assert is_canvas_only_skill("image-poster") is False

    assert build_skill_runtime_capabilities("design_workflow") == {
        "home_visible": False,
        "canvas_visible": True,
        "canvas_only": True,
        "canvas_default": True,
        "canvas_explicit": False,
    }
    assert build_skill_runtime_capabilities("image-poster") == {
        "home_visible": True,
        "canvas_visible": True,
        "canvas_only": False,
        "canvas_default": False,
        "canvas_explicit": False,
    }

    assert CANVAS_DEFAULT_SKILL_ID == "design_workflow"
    assert CANVAS_EXPLICIT_SKILL_IDS == frozenset({"brand_strategy_architect", "logo", "menswear-ecommerce-hero", "vi-design-guide"})
