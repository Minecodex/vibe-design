from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_harness.runtime.open_design.eligibility import is_home_open_design_html_run


def _protocol(**overrides):
    values = {
        "provider": "open_design",
        "mode": "prototype",
        "surface": "web",
        "family": "open_design_free_web",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_home_web_open_design_protocol_is_eligible() -> None:
    conversation = {
        "runtime_profile": "home",
        "artifact_mode": "web",
        "skill_id": "open-design-landing",
    }

    assert is_home_open_design_html_run(conversation, _protocol())


def test_canvas_web_open_design_protocol_is_not_eligible() -> None:
    conversation = {
        "runtime_profile": "canvas",
        "artifact_mode": "web",
        "skill_id": "open-design-landing",
    }

    assert not is_home_open_design_html_run(conversation, _protocol())


def test_media_modes_are_not_eligible() -> None:
    for mode in ("image", "video", "audio"):
        conversation = {"runtime_profile": "home", "artifact_mode": mode, "skill_id": mode}

        assert not is_home_open_design_html_run(conversation, _protocol(mode=mode, surface=mode))


def test_office_modes_are_not_eligible() -> None:
    for skill_id, mode in (("docx", "document"), ("xlsx", "spreadsheet"), ("pptx", "slides")):
        conversation = {"runtime_profile": "home", "artifact_mode": mode, "skill_id": skill_id}

        assert not is_home_open_design_html_run(conversation, _protocol(mode=mode, surface="web"))

