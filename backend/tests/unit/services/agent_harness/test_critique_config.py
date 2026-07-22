from dataclasses import replace

import pytest

from app.core.config import Settings
from app.services.agent_harness.runtime.critique.config import load_critique_config
from app.services.agent_harness.runtime.critique.contracts import CritiqueConfig
from app.services.agent_harness.runtime.critique.eligibility import (
    should_critique_active_entry,
    should_critique_manifest_entry,
    should_run_critique,
)


def test_critique_defaults_match_open_design_contract():
    cfg = load_critique_config(Settings(_env_file=None))

    assert cfg.enabled is True
    assert cfg.max_rounds == 3
    assert cfg.score_scale == 10
    assert cfg.score_threshold == 8.0
    assert cfg.protocol_version == 1
    assert cfg.fallback_policy == "ship_best"


def test_critique_only_runs_for_home_web_and_html_ppt():
    cfg = CritiqueConfig(enabled=True)

    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="html", skill_id="web")
    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="web", skill_id="web")
    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="document", skill_id="doc-html")
    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="slides", skill_id="deck-html")
    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="web", skill_id="open-design-landing")
    assert should_run_critique(cfg, runtime_profile="home", artifact_mode="slides", skill_id="html-ppt")
    assert not should_run_critique(cfg, runtime_profile="canvas", artifact_mode="html", skill_id="web")
    assert not should_run_critique(cfg, runtime_profile="home", artifact_mode="web", skill_id="")
    assert not should_run_critique(cfg, runtime_profile="home", artifact_mode="spreadsheet", skill_id="xlsx")
    assert not should_run_critique(cfg, runtime_profile="home", artifact_mode="image", skill_id="image-poster")
    assert not should_run_critique(cfg, runtime_profile="home", artifact_mode="video", skill_id="video-shortform")


def test_critique_active_entry_only_allows_html_inside_current_work_root():
    assert should_critique_active_entry(
        active_entry="web-prepared/index.html",
        artifact_work_root="web-prepared",
    )
    assert should_critique_active_entry(
        active_entry="web-prepared",
        artifact_work_root="web-prepared",
    )
    assert should_critique_active_entry(
        active_entry="project/web-prepared/",
        artifact_work_root="project/web-prepared",
    )
    assert should_critique_active_entry(
        active_entry="html-ppt-prepared/index.htm",
        artifact_work_root="html-ppt-prepared",
    )
    for entry in [
        "web-prepared/report.doc",
        "web-prepared/report.docx",
        "web-prepared/deck.ppt",
        "web-prepared/deck.pptx",
        "web-prepared/sheet.xls",
        "web-prepared/sheet.xlsx",
        "web-prepared/data.csv",
        "web-prepared/export.pdf",
        "other-prepared/index.html",
        "index.html",
    ]:
        assert not should_critique_active_entry(
            active_entry=entry,
            artifact_work_root="web-prepared",
        )


def test_critique_manifest_only_allows_html_visual_entries():
    assert should_critique_manifest_entry(
        {"entry": "web-prepared/index.html", "kind": "html", "renderer": "html"},
        artifact_work_root="web-prepared",
    )
    assert should_critique_manifest_entry(
        {"entry": "html-ppt-prepared/index.html", "kind": "deck", "renderer": "deck-html"},
        artifact_work_root="html-ppt-prepared",
    )
    assert should_critique_manifest_entry(
        {
            "entry": "web-prepared",
            "kind": "html",
            "renderer": "html",
            "validation": {"kind": "html_bundle"},
        },
        artifact_work_root="web-prepared",
    )
    assert should_critique_manifest_entry(
        {
            "entry": "doc-prepared/report.html",
            "kind": "code",
            "renderer": "html",
            "validation": {"details": {"kind": "html_bundle"}},
        },
        artifact_work_root="doc-prepared",
    )
    for manifest in [
        {"entry": "web-prepared/report.docx", "kind": "document", "renderer": "file"},
        {"entry": "web-prepared/deck.pptx", "kind": "deck", "renderer": "file"},
        {"entry": "web-prepared/export.pdf", "kind": "document", "renderer": "file"},
        {"entry": "web-prepared/index.html", "kind": "deck", "renderer": "file"},
        {"entry": "other-prepared/index.html", "kind": "html", "renderer": "html"},
    ]:
        assert not should_critique_manifest_entry(manifest, artifact_work_root="web-prepared")


def test_critique_config_rejects_threshold_above_scale():
    with pytest.raises(ValueError, match="score_threshold"):
        replace(CritiqueConfig(), score_threshold=11).validate()

