from __future__ import annotations

import importlib
import sys


def test_skill_catalog_imports_and_exposes_representative_skills() -> None:
    sys.modules.pop("app.services.agent_harness.capabilities.skills", None)

    skills = importlib.import_module("app.services.agent_harness.capabilities.skills")

    docx = skills.get_skill("docx")
    html_ppt = skills.get_skill("html-ppt")
    kami_landing = skills.get_skill("kami-landing")

    assert docx is not None
    assert docx.execution_strategy == "office_pipeline"
    assert html_ppt is not None
    assert html_ppt.execution_strategy == "template_driven_deck"
    assert kami_landing is not None
    assert kami_landing.artifact_mode == "web"


def test_get_skill_loads_requested_skill_without_full_catalog(monkeypatch) -> None:
    sys.modules.pop("app.services.agent_harness.capabilities.skills", None)

    skills = importlib.import_module("app.services.agent_harness.capabilities.skills")

    def _fail_full_catalog_load():
        raise AssertionError("get_skill should not load the full skill catalog")

    monkeypatch.setattr(skills, "_load_skills_from_md", _fail_full_catalog_load)

    xlsx = skills.get_skill("xlsx")

    assert xlsx is not None
    assert xlsx.id == "xlsx"
