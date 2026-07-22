from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.isolation.security.service import HarnessSecurityService
from app.services.agent_harness.isolation.security.types import SecurityVerdict


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-security",
        run_id="run-security",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    return ctx


def test_check_write_path_allows_project_path(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    service = HarnessSecurityService()

    decision = service.check_write_path(ctx, location="project", path="project/foo.py")

    assert decision.verdict == SecurityVerdict.ALLOW
    assert decision.normalized_value == "foo.py"
    assert decision.resolved_path == ctx.project_dir / "foo.py"


def test_check_write_path_rejects_parent_escape(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    service = HarnessSecurityService()

    decision = service.check_write_path(ctx, location="project", path="../foo.py")

    assert decision.verdict == SecurityVerdict.DENY
    assert decision.reason_code == "path_traversal"


def test_check_read_path_allows_active_skill_files(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    skill_dir = tmp_path / "skills" / "xlsx"
    skill_dir.mkdir(parents=True)
    target = skill_dir / "references" / "financial-model.md"
    target.parent.mkdir()
    target.write_text("finance notes", encoding="utf-8")
    ctx.active_skill_dir = skill_dir
    service = HarnessSecurityService()

    decision = service.check_read_path(ctx, location="skill", path="references/financial-model.md")

    assert decision.verdict == SecurityVerdict.ALLOW
    assert decision.resolved_path == target.resolve()


def test_check_read_path_allows_staged_skill_root_without_active_skill(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    target = ctx.skill_dir / "references" / "financial-model.md"
    target.parent.mkdir(parents=True)
    target.write_text("finance notes", encoding="utf-8")
    service = HarnessSecurityService()

    decision = service.check_read_path(ctx, location="skill", path="references/financial-model.md")

    assert decision.verdict == SecurityVerdict.ALLOW
    assert decision.resolved_path == target.resolve()


def test_check_read_path_rejects_skill_parent_escape(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    skill_dir = tmp_path / "skills" / "xlsx"
    skill_dir.mkdir(parents=True)
    ctx.active_skill_dir = skill_dir
    service = HarnessSecurityService()

    decision = service.check_read_path(ctx, location="skill", path="../secrets.txt")

    assert decision.verdict == SecurityVerdict.DENY
    assert decision.reason_code == "path_traversal"


def test_check_command_normalizes_duplicate_project_prefix(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    service = HarnessSecurityService()

    decision = service.check_command(ctx, command="python project/foo.py", cwd="project")

    assert decision.verdict == SecurityVerdict.ALLOW
    assert decision.normalized_value == "python foo.py"
    assert decision.warnings


def test_check_command_rejects_literal_env_cwd(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    service = HarnessSecurityService()

    decision = service.check_command(ctx, command="python foo.py", cwd="HARNESS_PROJECT_DIR")

    assert decision.verdict == SecurityVerdict.DENY
    assert decision.reason_code == "workspace_configuration_error"


def test_check_command_session_cwd_rejects_outside_workspace(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    service = HarnessSecurityService()

    decision = service.check_command_session_cwd(ctx, cwd="../outside")

    assert decision.verdict == SecurityVerdict.DENY
    assert decision.reason_code == "cwd_outside_workspace"


def test_attach_normalization_warning_records_metadata() -> None:
    service = HarnessSecurityService()

    output, metadata = service.attach_normalization_warning(
        output='{"ok":true}',
        metadata={"ok": True},
        normalized_value="foo.py",
        warnings=["Removed redundant work/ prefix from 'work/foo.py'."],
        original="work/foo.py",
        kind="redundant_work_prefix",
    )

    assert metadata["normalization_kind"] == "redundant_work_prefix"
    assert metadata["normalized_value"] == "foo.py"
    assert metadata["original_input"] == "work/foo.py"
    assert output
