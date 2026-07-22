from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from app.services.agent_harness.runtime.critique.contracts import CritiqueFinding
from app.services.agent_harness.runtime.critique.workspace_snapshots import (
    restore_round_snapshot,
    snapshot_round,
)


def _context(tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    project_dir = conversation_dir / "project"
    project_dir.mkdir(parents=True)
    return SimpleNamespace(conversation_dir=conversation_dir, project_dir=project_dir)


def test_snapshot_only_copies_current_artifact_work_root(tmp_path):
    ctx = _context(tmp_path)
    (ctx.project_dir / "web-prepared").mkdir()
    (ctx.project_dir / "web-prepared" / "index.html").write_text("round one", encoding="utf-8")
    (ctx.project_dir / "other-prepared").mkdir()
    (ctx.project_dir / "other-prepared" / "keep.txt").write_text("keep", encoding="utf-8")

    snapshot = snapshot_round(
        ctx,
        critique_run_id="run-1",
        round_number=1,
        artifact_work_root="web-prepared",
        active_entry="web-prepared/index.html",
        manifest={"entry": "web-prepared/index.html", "kind": "html"},
        composite=7.5,
        must_fix_count=1,
        findings=(CritiqueFinding(role="execution", text="Fix spacing"),),
        warnings=(
            {"code": "screenshot_unavailable", "message": "No rendered screenshot evidence was provided."},
            {"code": "score_clamped", "message": "A critique score exceeded the configured scale and was clamped."},
            {"code": "composite_mismatch", "message": "Agent-reported composite differed from backend scoring."},
            {"code": "unknown_role", "message": "An unknown critique panelist role was ignored."},
        ),
    )

    assert (snapshot / "artifact-work-root" / "index.html").read_text(encoding="utf-8") == "round one"
    assert not (snapshot / "artifact-work-root" / "other-prepared").exists()
    round_json = json.loads((snapshot / "round.json").read_text(encoding="utf-8"))
    assert round_json["warnings"] == [
        {"code": "screenshot_unavailable", "message": "No rendered screenshot evidence was provided."},
        {"code": "score_clamped", "message": "A critique score exceeded the configured scale and was clamped."},
        {"code": "composite_mismatch", "message": "Agent-reported composite differed from backend scoring."},
        {"code": "unknown_role", "message": "An unknown critique panelist role was ignored."},
    ]


def test_snapshot_excludes_non_deliverable_cache_directories(tmp_path):
    ctx = _context(tmp_path)
    work_root = ctx.project_dir / "web-prepared"
    work_root.mkdir()
    (work_root / "index.html").write_text("round one", encoding="utf-8")
    cache_dir = work_root / ".cache" / "npm" / "node_modules"
    cache_dir.mkdir(parents=True)
    (cache_dir / "ignored.txt").write_text("cache", encoding="utf-8")

    snapshot = snapshot_round(
        ctx,
        critique_run_id="run-1",
        round_number=1,
        artifact_work_root="web-prepared",
        active_entry="web-prepared/index.html",
        manifest={"entry": "web-prepared/index.html", "kind": "html"},
        composite=7.5,
        must_fix_count=1,
        findings=(),
    )

    assert (snapshot / "artifact-work-root" / "index.html").is_file()
    assert not (snapshot / "artifact-work-root" / ".cache").exists()


def test_restore_round_snapshot_does_not_replace_other_project_directories(tmp_path):
    ctx = _context(tmp_path)
    work_root = ctx.project_dir / "web-prepared"
    work_root.mkdir()
    (work_root / "index.html").write_text("best round", encoding="utf-8")
    other = ctx.project_dir / "other-prepared"
    other.mkdir()
    (other / "keep.txt").write_text("keep", encoding="utf-8")
    snapshot = snapshot_round(
        ctx,
        critique_run_id="run-1",
        round_number=1,
        artifact_work_root="web-prepared",
        active_entry="web-prepared/index.html",
        manifest={"entry": "web-prepared/index.html", "kind": "html"},
        composite=7.5,
        must_fix_count=1,
        findings=(),
    )
    (work_root / "index.html").write_text("later round", encoding="utf-8")

    manifest = restore_round_snapshot(
        ctx,
        snapshot_dir=snapshot,
        artifact_work_root="web-prepared",
    )

    assert manifest["entry"] == "web-prepared/index.html"
    assert (work_root / "index.html").read_text(encoding="utf-8") == "best round"
    assert (other / "keep.txt").read_text(encoding="utf-8") == "keep"


def _snapshot_web_prepared(ctx):
    work_root = ctx.project_dir / "web-prepared"
    work_root.mkdir()
    (work_root / "index.html").write_text("best round", encoding="utf-8")
    snapshot = snapshot_round(
        ctx,
        critique_run_id="run-1",
        round_number=1,
        artifact_work_root="web-prepared",
        active_entry="web-prepared/index.html",
        manifest={"entry": "web-prepared/index.html", "kind": "html"},
        composite=7.5,
        must_fix_count=1,
        findings=(),
    )
    (work_root / "index.html").write_text("later round", encoding="utf-8")
    return work_root, snapshot


def test_restore_is_self_describing_without_work_root_argument(tmp_path):
    # A1: restore reads the canonical work root from the snapshot itself, so it
    # works even when the caller passes nothing.
    ctx = _context(tmp_path)
    work_root, snapshot = _snapshot_web_prepared(ctx)

    manifest = restore_round_snapshot(ctx, snapshot_dir=snapshot)

    assert manifest["entry"] == "web-prepared/index.html"
    assert (work_root / "index.html").read_text(encoding="utf-8") == "best round"


@pytest.mark.parametrize("bad_hint", ["", None, "project/web-prepared", "a/b", "   "])
def test_restore_ignores_non_canonical_work_root_hint(tmp_path, bad_hint):
    # A1: a critique run can freeze an empty or non-canonical artifact_work_root.
    # The snapshot's own round.json is authoritative, so restore still succeeds.
    ctx = _context(tmp_path)
    work_root, snapshot = _snapshot_web_prepared(ctx)

    manifest = restore_round_snapshot(ctx, snapshot_dir=snapshot, artifact_work_root=bad_hint)

    assert manifest["entry"] == "web-prepared/index.html"
    assert (work_root / "index.html").read_text(encoding="utf-8") == "best round"


def test_restore_falls_back_to_manifest_entry_when_round_json_missing(tmp_path):
    ctx = _context(tmp_path)
    work_root, snapshot = _snapshot_web_prepared(ctx)
    (snapshot / "round.json").unlink()

    manifest = restore_round_snapshot(ctx, snapshot_dir=snapshot, artifact_work_root="")

    assert manifest["entry"] == "web-prepared/index.html"
    assert (work_root / "index.html").read_text(encoding="utf-8") == "best round"


def test_snapshot_rejects_symlink(tmp_path):
    ctx = _context(tmp_path)
    work_root = ctx.project_dir / "web-prepared"
    work_root.mkdir()
    target = tmp_path / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    try:
        (work_root / "link.txt").symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable on this Windows environment")

    with pytest.raises(ValueError, match="symlink"):
        snapshot_round(
            ctx,
            critique_run_id="run-1",
            round_number=1,
            artifact_work_root="web-prepared",
            active_entry="web-prepared/index.html",
            manifest={"entry": "web-prepared/index.html", "kind": "html"},
            composite=7.5,
            must_fix_count=1,
            findings=(),
        )

