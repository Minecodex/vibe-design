from app.services.agent_harness.capabilities.skills import get_skill, list_skills_for_mode


def test_mode_skill_lists_include_all_skills_in_the_mode():
    image_poster = get_skill("image-poster")
    video_shortform = get_skill("video-shortform")
    motion_frames = get_skill("motion-frames")

    assert image_poster is not None
    assert image_poster.artifact_mode == "image"
    assert image_poster.id in {skill.id for skill in list_skills_for_mode("image")}

    assert video_shortform is not None
    assert video_shortform.artifact_mode == "video"
    assert video_shortform.id in {skill.id for skill in list_skills_for_mode("video")}

    assert motion_frames is not None
    assert motion_frames.artifact_mode == "web"
    assert motion_frames.id in {skill.id for skill in list_skills_for_mode("web")}


def test_runtime_strategy_metadata_is_loaded_for_template_and_free_generate_skills():
    html_ppt = get_skill("html-ppt")
    kami_landing = get_skill("kami-landing")
    dashboard = get_skill("dashboard")
    docx = get_skill("docx")
    pptx = get_skill("pptx")
    web = get_skill("web")
    kami_deck = get_skill("kami-deck")

    assert html_ppt is not None
    assert html_ppt.execution_strategy == "template_driven_deck"
    assert "templates" in html_ppt.template_roots
    assert html_ppt.preview_entry == "index.html"

    assert kami_landing is not None
    assert kami_landing.execution_strategy == "free_generate"
    assert kami_landing.preview_entry in {"index.html", "example.html", None}
    assert any(str(item.get("name") or item.get("id") or "") == "output_format" for item in kami_landing.parameters)

    assert dashboard is not None
    assert dashboard.execution_strategy == "free_generate"
    assert dashboard.seed_assets == []
    assert dashboard.metadata_health["frontmatter_status"] == "ok"

    assert docx is not None
    assert docx.execution_strategy == "office_pipeline"
    assert docx.mode == "document"
    assert docx.design_system.requires is True
    assert docx.scenario == "narrative"

    assert pptx is not None
    assert pptx.execution_strategy == "office_pipeline"
    assert pptx.mode == "document"
    assert pptx.artifact_mode == "slides"
    assert pptx.design_system.requires is True

    assert web is not None
    assert web.execution_strategy == "free_generate"
    assert web.mode == "prototype"
    assert web.surface == "web"
    assert web.design_system.requires is True

    assert kami_deck is not None
    assert kami_deck.directions == []
    assert any(
        str(item.get("runtime_scope") or "") == "live_preview"
        for item in kami_landing.parameters
    )
