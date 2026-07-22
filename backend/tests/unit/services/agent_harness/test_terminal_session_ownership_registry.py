from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator, RedisCoordinator
from app.services.agent_harness.capabilities.tools._internal.command_runner import (
    CommandSessionSnapshot,
)
from app.services.agent_harness.capabilities.tools._internal.terminal_session_registry import (
    TerminalSessionOwnershipRegistry,
)
from app.services.agent_harness.capabilities.tools.exec_command import (
    ExecCommandInput,
    ExecCommandTool,
)
from app.services.agent_harness.core.context import HarnessContext


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-terminal-owner",
        run_id="run-terminal-owner",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    return ctx


@pytest.mark.asyncio
async def test_terminal_session_registry_reports_owned_elsewhere_without_sensitive_payload(
    monkeypatch,
    tmp_path: Path,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)

    owner = TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30)
    observer = TerminalSessionOwnershipRegistry(owner_id="worker-b", ttl_seconds=30)

    await owner.register(ctx=ctx, session_id="session-1")
    status = await observer.describe(ctx=ctx, session_id="session-1")

    assert status.status == "owned_elsewhere"
    assert status.owner_id == "worker-a"
    snapshot_values = list(coordinator._snapshots.values())
    assert snapshot_values
    snapshot_text = repr(snapshot_values[0]).lower()
    assert "command" not in snapshot_text
    assert str(ctx.conversation_dir).lower() not in snapshot_text


@pytest.mark.asyncio
async def test_terminal_session_registry_reports_expired_owner(monkeypatch, tmp_path: Path):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)
    owner = TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30)
    key = owner._key(ctx=ctx, session_id="session-1")
    await coordinator.set_snapshot(
        key,
        {
            "status": "running",
            "session_id": "session-1",
            "owner_id": "worker-a",
            "expires_at": time.time() - 1,
            "capabilities": ["read", "stop"],
        },
        ttl_seconds=30,
    )

    status = await TerminalSessionOwnershipRegistry(owner_id="worker-b").describe(
        ctx=ctx,
        session_id="session-1",
    )

    assert status.status == "expired"


@pytest.mark.asyncio
async def test_terminal_session_registry_reports_completed_hint(monkeypatch, tmp_path: Path):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)
    owner = TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30)

    await owner.register(ctx=ctx, session_id="session-1")
    await owner.complete(ctx=ctx, session_id="session-1")
    status = await TerminalSessionOwnershipRegistry(owner_id="worker-b").describe(
        ctx=ctx,
        session_id="session-1",
    )

    assert status.status == "completed"
    assert status.owner_id == "worker-a"


@pytest.mark.asyncio
async def test_terminal_session_registry_write_failures_do_not_break_local_owner(monkeypatch, tmp_path: Path):
    # Real production behaviour: when the Redis client raises, RedisCoordinator
    # logs and falls back to its in-process coordinator (set_snapshot is not a
    # strict operation). The registry must not surface the underlying failure
    # to its callers (e.g. exec_command).
    class FailingClient:
        async def ping(self):
            return True

        async def set(self, *args, **kwargs):
            raise RuntimeError("redis unavailable")

        async def get(self, *args, **kwargs):
            return None

    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.05,
        ),
        client=FailingClient(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)
    owner = TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30)

    await owner.register(ctx=ctx, session_id="session-1")
    await owner.renew(ctx=ctx, session_id="session-1")
    await owner.complete(ctx=ctx, session_id="session-1")


@pytest.mark.asyncio
async def test_exec_command_read_returns_non_owner_terminal_status(monkeypatch, tmp_path: Path):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)
    await TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30).register(
        ctx=ctx,
        session_id="session-1",
    )

    class FakeRunner:
        def has_session(self, session_id):
            return False

        def validate_command(self, command):
            return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.get_command_runner",
        lambda: FakeRunner(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.TerminalSessionOwnershipRegistry",
        lambda: TerminalSessionOwnershipRegistry(owner_id="worker-b", ttl_seconds=30),
    )

    result = await ExecCommandTool().execute(
        ExecCommandInput(action="read", session_id="session-1"),
        ctx,
    )
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["ownership_status"] == "owned_elsewhere"
    assert result.metadata["owner_id"] == "worker-a"


@pytest.mark.parametrize("action", ["read", "stop"])
@pytest.mark.asyncio
async def test_exec_command_owner_can_read_and_stop_local_terminal_session(
    action: str,
    monkeypatch,
    tmp_path: Path,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)

    class FakeRunner:
        def has_session(self, session_id):
            return session_id == "session-1"

        def validate_command(self, command):
            return None

        async def read(self, *, session_id, timeout):
            return CommandSessionSnapshot(
                session_id=session_id,
                running=True,
                exit_code=None,
                elapsed_ms=10,
                cwd=str(ctx.conversation_dir),
                stdout="still running",
            )

        async def stop(self, *, session_id):
            return CommandSessionSnapshot(
                session_id=session_id,
                running=False,
                exit_code=0,
                elapsed_ms=20,
                cwd=str(ctx.conversation_dir),
                stdout="stopped",
            )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.get_command_runner",
        lambda: FakeRunner(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.TerminalSessionOwnershipRegistry",
        lambda: TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30),
    )

    result = await ExecCommandTool().execute(
        ExecCommandInput(action=action, session_id="session-1"),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["session_id"] == "session-1"
    assert result.metadata["stdout"] == ("still running" if action == "read" else "stopped")


@pytest.mark.parametrize("action", ["write", "stop"])
@pytest.mark.asyncio
async def test_exec_command_write_and_stop_return_non_owner_terminal_status(
    action: str,
    monkeypatch,
    tmp_path: Path,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.terminal_session_registry.get_redis_coordinator",
        lambda: coordinator,
    )
    ctx = _ctx(tmp_path)
    await TerminalSessionOwnershipRegistry(owner_id="worker-a", ttl_seconds=30).register(
        ctx=ctx,
        session_id="session-1",
    )

    class FakeRunner:
        def has_session(self, session_id):
            return False

        def validate_command(self, command):
            return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.get_command_runner",
        lambda: FakeRunner(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.exec_command.TerminalSessionOwnershipRegistry",
        lambda: TerminalSessionOwnershipRegistry(owner_id="worker-b", ttl_seconds=30),
    )

    result = await ExecCommandTool().execute(
        ExecCommandInput(action=action, session_id="session-1", input="hello" if action == "write" else None),
        ctx,
    )
    payload = json.loads(result.output)

    assert result.is_error is True
    assert payload["ownership_status"] == "owned_elsewhere"
    assert result.metadata["owner_id"] == "worker-a"
