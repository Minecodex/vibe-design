from __future__ import annotations

from app.services.agent_harness.runtime.critique.eligibility import should_critique_manifest_entry


def test_deck_html_manifest_entry_under_work_root_is_critiqueable() -> None:
    assert should_critique_manifest_entry(
        {
            "entry": "html-ppt-prepared/index.html",
            "kind": "deck",
            "renderer": "deck-html",
            "validation": {"details": {"kind": "html_bundle"}},
        },
        artifact_work_root="html-ppt-prepared",
    )


def test_deck_html_manifest_entry_accepts_project_prefixed_paths() -> None:
    assert should_critique_manifest_entry(
        {
            "entry": "project/html-ppt-prepared/index.html",
            "kind": "deck",
            "renderer": "deck-html",
            "validation": {"details": {"kind": "html_bundle"}},
        },
        artifact_work_root="project/html-ppt-prepared",
    )


def test_non_html_deck_manifest_is_not_critiqueable() -> None:
    assert not should_critique_manifest_entry(
        {"entry": "html-ppt-prepared/deck.pptx", "kind": "deck", "renderer": "file"},
        artifact_work_root="html-ppt-prepared",
    )


def test_deck_html_manifest_critiqueable_when_work_root_missing() -> None:
    # The critique run can freeze an empty artifact_work_root; the manifest
    # entry must still be recognized as an eligible deck.
    for work_root in ("", None, "   "):
        assert should_critique_manifest_entry(
            {
                "entry": "html-ppt-prepared/index.html",
                "kind": "deck",
                "renderer": "deck-html",
                "validation": {"details": {"kind": "html_bundle"}},
            },
            artifact_work_root=work_root,
        )


def test_html_manifest_critiqueable_when_work_root_missing_with_project_prefix() -> None:
    assert should_critique_manifest_entry(
        {
            "entry": "project/web-prepared/index.html",
            "kind": "html",
            "renderer": "html",
        },
        artifact_work_root="",
    )


def test_directory_manifest_entry_uses_index_html_candidate() -> None:
    for entry in ("web-prepared", "web-prepared/", "project/web-prepared"):
        assert should_critique_manifest_entry(
            {
                "entry": entry,
                "kind": "html",
                "renderer": "html",
                "validation": {"kind": "html_bundle"},
            },
            artifact_work_root="",
        )


def test_bare_top_level_file_not_critiqueable_when_work_root_missing() -> None:
    # A bare top-level entry has no directory to synthesize a work root from.
    assert not should_critique_manifest_entry(
        {"entry": "index.html", "kind": "deck", "renderer": "deck-html"},
        artifact_work_root="",
    )
