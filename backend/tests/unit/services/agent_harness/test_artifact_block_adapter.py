from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.artifacts.manifest import read_artifact_manifest
from app.services.agent_harness.runtime.open_design.artifact_adapter import (
    capture_artifact_block,
    has_artifact_open_tag,
)
from app.services.agent_harness.runtime.open_design.artifact_block import ArtifactBlockError, parse_artifact_block
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def test_has_artifact_open_tag_matches_real_tag_only() -> None:
    assert has_artifact_open_tag('<artifact type="text/html">') is True
    assert has_artifact_open_tag("<artifact>") is True
    assert has_artifact_open_tag("intro\n<ARTIFACT identifier=x>") is True
    # The Design Jury critique protocol embeds <ARTIFACT_REF .../> inside its
    # <ROUND> XML; it must NOT be mistaken for an inline artifact block.
    assert has_artifact_open_tag('<ARTIFACT_REF entry="deck/index.html" />') is False
    assert has_artifact_open_tag("<ROUND n=\"1\"><ARTIFACT_REF entry=\"a/index.html\" /></ROUND>") is False
    assert has_artifact_open_tag("no tags here") is False


@pytest.mark.asyncio
async def test_capture_artifact_block_ignores_critique_artifact_ref(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        7,
        title="Critique round",
        runtime_profile="home",
        artifact_mode="slides",
        skill_id="html-ppt",
        resolved_skill_id="html-ppt",
    )
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-critique-round",
        workspace_root=tmp_path,
        runtime_profile="home",
        artifact_mode="slides",
        skill_id="html-ppt",
    )
    ctx.ensure_dirs()
    ctx.artifact_work_root = "html-ppt-prepared"

    # A Design Jury round references the artifact via <ARTIFACT_REF>. Capture must
    # bow out (return None) so the critique pipeline can score the round, instead
    # of hijacking it and emitting a repair instruction.
    result = await capture_artifact_block(
        ctx,
        '<ROUND n="1"><PANELIST role="designer">'
        '<ARTIFACT_REF entry="html-ppt-prepared/index.html" />'
        '</PANELIST></ROUND>',
        protocol=SimpleNamespace(provider="open_design", mode="slides", surface="slides", family="open_design_free_web"),
        return_errors=True,
    )

    assert result is None


def test_parse_artifact_block_accepts_single_complete_html_artifact() -> None:
    block = parse_artifact_block(
        '<artifact identifier="landing" type="text/html" title="Landing">'
        '<!doctype html><html><body><h1>Launch</h1></body></html>'
        '</artifact>'
    )

    assert block.identifier == "landing"
    assert block.title == "Landing"
    assert block.type == "text/html"
    assert "<!doctype html>" in block.html


def test_parse_artifact_block_rejects_multiple_blocks() -> None:
    with pytest.raises(ArtifactBlockError):
        parse_artifact_block(
            "<artifact><!doctype html><html><body>A</body></html></artifact>"
            "<artifact><!doctype html><html><body>B</body></html></artifact>"
        )


def test_parse_artifact_block_rejects_non_html_body() -> None:
    with pytest.raises(ArtifactBlockError):
        parse_artifact_block("<artifact type=\"text/html\">summary only</artifact>")


@pytest.mark.asyncio
async def test_capture_artifact_block_writes_prepared_entry_and_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        7,
        title="Artifact capture",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-artifact-capture",
        workspace_root=tmp_path,
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
    )
    ctx.ensure_dirs()
    ctx.prepared_workspace = SimpleNamespace(entry_path="landing-prepared/index.html", artifact_work_root="landing-prepared")
    ctx.artifact_work_root = "landing-prepared"
    ctx.prepared_entry_file = "index.html"

    result = await capture_artifact_block(
        ctx,
        '<artifact identifier="landing" type="text/html" title="Landing">'
        '<!doctype html><html><body><h1>Launch</h1></body></html>'
        '</artifact>',
        protocol=SimpleNamespace(provider="open_design", mode="prototype", surface="web", family="open_design_free_web"),
    )

    assert result is not None
    assert result.entry == "landing-prepared/index.html"
    assert (ctx.project_dir / "landing-prepared" / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    manifest = read_artifact_manifest(7, conversation["id"])
    assert manifest is not None
    assert manifest["entry"] == "landing-prepared/index.html"
    assert manifest["kind"] == "html"


@pytest.mark.asyncio
async def test_capture_artifact_block_returns_repair_instruction_for_invalid_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        7,
        title="Artifact capture invalid",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-artifact-capture-invalid",
        workspace_root=tmp_path,
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
    )
    ctx.ensure_dirs()
    ctx.artifact_work_root = "landing"

    result = await capture_artifact_block(
        ctx,
        '<artifact identifier="landing" type="text/html" title="Landing">summary only</artifact>',
        protocol=SimpleNamespace(provider="open_design", mode="prototype", surface="web", family="open_design_free_web"),
        return_errors=True,
    )

    assert result is not None
    assert result.entry is None
    assert result.manifest is None
    assert result.error_text
    assert "artifact body must be a complete standalone html document" in result.error_text
