from __future__ import annotations

from pathlib import Path
import sys

import pytest

from app.services.agent_harness.isolation.sandbox.sandbox_manager import (
    SandboxExecutor,
    build_bwrap_argv,
)
from app.services.agent_harness.isolation.sandbox.types import SandboxPolicy, SandboxRequest


@pytest.mark.asyncio
async def test_sandbox_denies_cwd_outside_allowed_roots(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()

    result = await SandboxExecutor().run(
        SandboxRequest(
            command="echo nope",
            cwd=denied,
            env={},
            timeout_seconds=1,
            policy=SandboxPolicy(
                workspace_root=allowed,
                writable_roots=(allowed,),
            ),
        )
    )

    assert result.denied is True
    assert "allowed sandbox root" in str(result.denied_reason)


@pytest.mark.asyncio
async def test_sandbox_runs_inside_allowed_root(tmp_path: Path):
    # On dev machines without bwrap this exercises the degraded (plain spawn) path.
    result = await SandboxExecutor().run(
        SandboxRequest(
            command=f'"{sys.executable}" -c "print(\'ok\')"',
            cwd=tmp_path,
            env={},
            timeout_seconds=10,
            policy=SandboxPolicy(
                workspace_root=tmp_path,
                writable_roots=(tmp_path,),
            ),
        )
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.denied is False


def test_build_bwrap_argv_binds_workspace_and_shares_network(tmp_path: Path):
    workspace = tmp_path / "conversation"
    project = workspace / "project"
    project.mkdir(parents=True)

    argv = build_bwrap_argv(
        SandboxRequest(
            command="echo ok",
            cwd=project,
            env={"HARNESS_SKILL_ROOT": "/skills", "PATH": "/usr/bin:/bin"},
            timeout_seconds=5,
            policy=SandboxPolicy(
                workspace_root=workspace,
                writable_roots=(project,),
            ),
        ),
        bwrap="/usr/bin/bwrap",
    )

    assert argv[0] == "/usr/bin/bwrap"
    # read-only whole-root base + writable workspace bound on top
    assert _has_pair(argv, "--ro-bind", "/", "/")
    assert _has_pair(argv, "--bind", str(project.resolve()), str(project.resolve()))
    # process/filesystem isolation, but network is shared (commands may need npm/pip)
    assert "--unshare-pid" in argv
    assert "--die-with-parent" in argv
    assert "--unshare-net" not in argv
    # cwd + env are passed through
    assert _has_value(argv, "--chdir", str(project))
    assert _has_triplet(argv, "--setenv", "HARNESS_SKILL_ROOT", "/skills")
    # the actual command is the final shell invocation
    assert argv[-3:] == ["/bin/sh", "-lc", "echo ok"]


def _has_value(argv: list[str], flag: str, value: str) -> bool:
    for i, token in enumerate(argv):
        if token == flag and i + 1 < len(argv) and argv[i + 1] == value:
            return True
    return False


def _has_pair(argv: list[str], flag: str, a: str, b: str) -> bool:
    for i, token in enumerate(argv):
        if token == flag and argv[i + 1 : i + 3] == [a, b]:
            return True
    return False


def _has_triplet(argv: list[str], flag: str, a: str, b: str) -> bool:
    for i, token in enumerate(argv):
        if token == flag and argv[i + 1 : i + 3] == [a, b]:
            return True
    return False
