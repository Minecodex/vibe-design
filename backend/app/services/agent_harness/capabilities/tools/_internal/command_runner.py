from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.agent_harness.isolation.sandbox import SandboxPolicy, SandboxRequest, get_sandbox_executor
from app.services.agent_harness.isolation.security import extract_command_diagnostics, literal_env_cwd_error as _literal_env_cwd_error
from app.services.agent_harness.isolation.security.commands import detect_semantic
from app.services.agent_harness.isolation.security.paths import active_artifact_work_root, allowed_cwd_roots, artifact_work_dir
from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.isolation.sandbox.output_truncation import OUTPUT_TRUNCATION_MARKER_TEMPLATE

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

DEFAULT_MAX_OUTPUT_BYTES = 16_384


@dataclass(slots=True)
class CommandRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    elapsed_ms: int = 0
    timed_out: bool = False
    denied: bool = False
    denied_reason: str | None = None
    truncated: bool = False
    semantic_error: dict[str, str] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.denied or self.timed_out or (self.exit_code is not None and self.exit_code != 0) or self.semantic_error is not None


@dataclass(slots=True)
class CommandSessionSnapshot:
    session_id: str
    running: bool
    exit_code: int | None
    elapsed_ms: int
    cwd: str
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    semantic_error: dict[str, str] | None = None

    @property
    def is_error(self) -> bool:
        return (not self.running and self.exit_code not in (0, None)) or self.semantic_error is not None


@dataclass(slots=True)
class _CommandSession:
    session_id: str
    proc: asyncio.subprocess.Process
    cwd: Path
    command: str
    started_at: float
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    stdout_task: asyncio.Task | None = None
    stderr_task: asyncio.Task | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class CommandRunner:
    def __init__(self, *, max_output_chars: int = DEFAULT_MAX_OUTPUT_BYTES) -> None:
        self.max_output_chars = max_output_chars
        self._sessions: dict[str, _CommandSession] = {}

    def validate_command(self, command: str) -> str | None:
        decision = get_security_service().check_command(None, command=command, cwd="project")
        return decision.reason if not decision.allowed else None

    def has_session(self, session_id: str | None) -> bool:
        return bool(session_id) and session_id in self._sessions

    async def run_once(self, *, ctx: "HarnessContext", command: str, cwd: str, timeout: int) -> CommandRunResult:
        ctx.ensure_dirs()
        command_decision = get_security_service().check_command(ctx, command=command, cwd=cwd)
        if not command_decision.allowed:
            return CommandRunResult(
                denied=True,
                denied_reason=command_decision.reason,
                metadata={
                    "failure_kind": command_decision.reason_code,
                    **(command_decision.metadata or {}),
                },
            )
        effective_command = str(command_decision.normalized_value or command)
        resolved_cwd_decision = get_security_service().check_command_session_cwd(ctx, cwd=cwd)
        if not resolved_cwd_decision.allowed:
            return CommandRunResult(
                denied=True,
                denied_reason=resolved_cwd_decision.reason,
                metadata={"failure_kind": resolved_cwd_decision.reason_code},
            )
        resolved_cwd = resolved_cwd_decision.resolved_cwd
        assert resolved_cwd is not None
        normalization_metadata = _normalization_metadata(command_decision, effective_cwd=resolved_cwd)

        env_error = validate_workspace_env_paths(
            HARNESS_PROJECT_DIR=ctx.project_dir.resolve(),
            CONVERSATION_DIR=ctx.conversation_dir.resolve(),
        )
        if env_error:
            return CommandRunResult(denied=True, denied_reason=env_error, metadata={"failure_kind": "workspace_configuration_error"})

        sandbox_result = await get_sandbox_executor().run(
            SandboxRequest(
                command=effective_command,
                cwd=resolved_cwd,
                env=build_env(ctx),
                timeout_seconds=timeout,
                policy=build_policy(ctx, max_output_bytes=self.max_output_chars),
            )
        )
        semantic = detect_semantic(sandbox_result.stdout, sandbox_result.stderr)
        diagnostic_metadata = extract_command_diagnostics(
            cwd=resolved_cwd,
            command=effective_command,
            stdout=sandbox_result.stdout,
            stderr=sandbox_result.stderr,
        )
        return CommandRunResult(
            stdout=sandbox_result.stdout,
            stderr=sandbox_result.stderr,
            exit_code=sandbox_result.exit_code,
            elapsed_ms=sandbox_result.elapsed_ms,
            timed_out=sandbox_result.timed_out,
            denied=sandbox_result.denied,
            denied_reason=sandbox_result.denied_reason,
            truncated=sandbox_result.truncated,
            semantic_error=semantic,
            metadata={
                **sandbox_result.metadata,
                **diagnostic_metadata,
                **normalization_metadata,
                "effective_cwd": str(resolved_cwd),
            },
        )

    async def start(self, *, ctx: "HarnessContext", command: str, cwd: str, timeout: int) -> CommandSessionSnapshot | CommandRunResult:
        ctx.ensure_dirs()
        command_decision = get_security_service().check_command(ctx, command=command, cwd=cwd)
        if not command_decision.allowed:
            return CommandRunResult(
                denied=True,
                denied_reason=command_decision.reason,
                metadata={
                    "failure_kind": command_decision.reason_code,
                    **(command_decision.metadata or {}),
                },
            )
        effective_command = str(command_decision.normalized_value or command)
        resolved_cwd_decision = get_security_service().check_command_session_cwd(ctx, cwd=cwd)
        if not resolved_cwd_decision.allowed:
            return CommandRunResult(
                denied=True,
                denied_reason=resolved_cwd_decision.reason,
                metadata={"failure_kind": resolved_cwd_decision.reason_code},
            )
        resolved_cwd = resolved_cwd_decision.resolved_cwd
        assert resolved_cwd is not None

        env_error = validate_workspace_env_paths(
            HARNESS_PROJECT_DIR=ctx.project_dir.resolve(),
            CONVERSATION_DIR=ctx.conversation_dir.resolve(),
        )
        if env_error:
            return CommandRunResult(denied=True, denied_reason=env_error, metadata={"failure_kind": "workspace_configuration_error"})

        try:
            proc = await get_sandbox_executor().spawn(
                SandboxRequest(
                    command=effective_command,
                    cwd=resolved_cwd,
                    env=build_env(ctx),
                    timeout_seconds=timeout,
                    policy=build_policy(ctx, max_output_bytes=self.max_output_chars),
                )
            )
        except Exception as exc:
            return CommandRunResult(stderr=f"Failed to execute: {exc}", metadata={"exception_type": type(exc).__name__})

        session = _CommandSession(
            session_id=uuid.uuid4().hex[:12],
            proc=proc,
            cwd=resolved_cwd,
            command=effective_command,
            started_at=time.monotonic(),
        )
        session.stdout_task = asyncio.create_task(self._drain_stream(proc.stdout, session, "stdout"))
        session.stderr_task = asyncio.create_task(self._drain_stream(proc.stderr, session, "stderr"))
        self._sessions[session.session_id] = session
        await self._wait(session, timeout)
        return self.snapshot(session.session_id, remove_finished=True)

    async def read(self, *, session_id: str, timeout: int) -> CommandSessionSnapshot:
        session = self._sessions[session_id]
        await self._wait(session, timeout)
        return self.snapshot(session_id)

    async def stop(self, *, session_id: str) -> CommandSessionSnapshot:
        session = self._sessions[session_id]
        if session.proc.returncode is None:
            _terminate_process_tree(session.proc)
            try:
                await asyncio.wait_for(session.proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                session.proc.kill()
                await session.proc.wait()
        for task in (session.stdout_task, session.stderr_task):
            if task and not task.done():
                task.cancel()
        return self.snapshot(session_id, remove=True)

    async def write(self, *, session_id: str, text: str) -> int:
        session = self._sessions[session_id]
        if session.proc.returncode is not None or session.proc.stdin is None:
            raise RuntimeError(f"Session is not running: {session_id}")
        session.proc.stdin.write(text.encode("utf-8"))
        await session.proc.stdin.drain()
        return len(text)

    def snapshot(self, session_id: str, *, remove: bool = False, remove_finished: bool = False) -> CommandSessionSnapshot:
        session = self._sessions[session_id]
        stdout = "".join(session.stdout)
        stderr = "".join(session.stderr)
        stdout_truncated = session.stdout_truncated
        stderr_truncated = session.stderr_truncated
        session.stdout.clear()
        session.stderr.clear()
        session.stdout_truncated = False
        session.stderr_truncated = False
        running = session.proc.returncode is None
        semantic = detect_semantic(stdout, stderr)
        diagnostic_metadata = extract_command_diagnostics(
            cwd=session.cwd,
            command=session.command,
            stdout=stdout,
            stderr=stderr,
        )
        snapshot = CommandSessionSnapshot(
            session_id=session.session_id,
            running=running,
            exit_code=session.proc.returncode,
            elapsed_ms=int((time.monotonic() - session.started_at) * 1000),
            cwd=str(session.cwd),
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            semantic_error=None if semantic is None else {**semantic, **diagnostic_metadata},
        )
        if remove or (remove_finished and not running):
            self._sessions.pop(session_id, None)
        return snapshot

    async def _drain_stream(self, stream: asyncio.StreamReader | None, session: _CommandSession, stream_name: str) -> None:
        if stream is None:
            return
        target = session.stdout if stream_name == "stdout" else session.stderr
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            already_truncated = session.stdout_truncated if stream_name == "stdout" else session.stderr_truncated
            if already_truncated:
                continue
            text = chunk.decode("utf-8", errors="replace")
            current_bytes = len("".join(target).encode("utf-8"))
            if current_bytes + len(text.encode("utf-8")) <= self.max_output_chars:
                target.append(text)
                continue
            remaining = max(self.max_output_chars - current_bytes, 0)
            if remaining > 0:
                encoded = text.encode("utf-8")[:remaining]
                while encoded:
                    try:
                        target.append(encoded.decode("utf-8"))
                        break
                    except UnicodeDecodeError:
                        encoded = encoded[:-1]
            target.append(OUTPUT_TRUNCATION_MARKER_TEMPLATE.format(max_bytes=self.max_output_chars))
            if stream_name == "stdout":
                session.stdout_truncated = True
            else:
                session.stderr_truncated = True

    @staticmethod
    async def _wait(session: _CommandSession, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if session.proc.returncode is not None:
                break
            await asyncio.sleep(0.1)


def get_command_runner() -> CommandRunner:
    return _RUNNER


def _normalization_metadata(decision, *, effective_cwd: Path | None = None) -> dict[str, object]:
    if not getattr(decision, "warnings", None):
        return {}
    warning = decision.warnings[0]
    original = (
        "<current-project-absolute-command>"
        if warning.kind == "current_project_absolute_path"
        else warning.original_value
    )
    return {
        "normalization_kind": warning.kind,
        "normalization_warning": warning.warning,
        "normalized_command": decision.normalized_value,
        "original_input": original,
        "shell_path_diagnostic": {
            "effective_cwd": str(effective_cwd) if effective_cwd is not None else "project",
            "original_command": original,
            "normalized_command": decision.normalized_value,
            "normalization_kind": warning.kind,
            "correction_applied": True,
        },
    }


def resolve_cwd(ctx: "HarnessContext", cwd: str) -> Path | None:
    decision = get_security_service().check_command_session_cwd(ctx, cwd=cwd)
    return decision.resolved_cwd if decision.allowed else None


def literal_env_cwd_error(cwd: str) -> str | None:
    return _literal_env_cwd_error(cwd)


def build_env(ctx: "HarnessContext") -> dict[str, str]:
    conversation_dir = ctx.conversation_dir.resolve()
    project_dir = ctx.project_dir.resolve()
    artifact_root = active_artifact_work_root(ctx)
    artifact_dir = artifact_work_dir(ctx)
    references_dir = ctx.references_dir.resolve()
    published_dir = ctx.published_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    if artifact_root:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    cache_root = (artifact_dir if artifact_root else project_dir) / ".cache"
    npm_cache = cache_root / "npm"
    cache_root.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(cache_root.resolve()) if artifact_root else str(project_dir),
        "XDG_CACHE_HOME": str(cache_root.resolve()),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
        "CONVERSATION_DIR": str(conversation_dir),
        "HARNESS_CONVERSATION_DIR": str(conversation_dir),
        "HARNESS_PROJECT_DIR": str(project_dir),
        "HARNESS_ARTIFACT_WORK_DIR": str(artifact_dir),
        "HARNESS_ARTIFACT_WORK_ROOT": artifact_root or "",
        "HARNESS_REFERENCES_DIR": str(references_dir),
        "HARNESS_REFERENCE_INPUTS_DIR": str(ctx.reference_inputs_dir.resolve()),
        "HARNESS_REFERENCE_SOURCES_DIR": str(ctx.reference_sources_dir.resolve()),
        "HARNESS_REFERENCE_GENERATED_DIR": str(ctx.reference_generated_dir.resolve()),
        "HARNESS_PUBLISHED_DIR": str(published_dir),
        "HARNESS_AUTHOR_NAME": "Harness",
        "NPM_CONFIG_REGISTRY": "https://registry.npmmirror.com",
        "npm_config_registry": "https://registry.npmmirror.com",
        "NPM_CONFIG_CACHE": str(npm_cache.resolve()),
        "npm_config_cache": str(npm_cache.resolve()),
    }
    playwright_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if playwright_browsers_path:
        env["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers_path
    active_skill_dir = getattr(ctx, "active_skill_dir", None)
    env["HARNESS_SKILL_ROOT"] = str(Path(active_skill_dir).resolve()) if active_skill_dir else str(ctx.skill_dir.resolve())
    return env


def build_policy(ctx: "HarnessContext", *, max_output_bytes: int) -> SandboxPolicy:
    active_skill_dir = getattr(ctx, "active_skill_dir", None)
    return SandboxPolicy(
        workspace_root=ctx.conversation_dir.resolve(),
        writable_roots=(
            ctx.project_dir.resolve(),
        ),
        readonly_roots=(
            ctx.references_dir.resolve(),
            ctx.published_dir.resolve(),
            ctx.skill_dir.resolve(),
            ctx.agent_dir.resolve(),
            ctx.meta_dir.resolve(),
            ctx.logs_dir.resolve(),
            *tuple(Path(active_skill_dir).resolve() for active_skill_dir in [active_skill_dir] if active_skill_dir),
        ),
        max_output_bytes=max_output_bytes,
        max_timeout_seconds=300,
    )


def validate_workspace_env_paths(**paths: Path) -> str | None:
    for name, path in paths.items():
        if not path.is_absolute():
            return f"Workspace configuration error: {name} must be an absolute path, got {path!s}"
    return None


def _allowed_cwd_roots(ctx: "HarnessContext") -> tuple[Path, ...]:
    return allowed_cwd_roots(ctx)


def _is_under_any(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def format_run_output(stdout: str, stderr: str, exit_code: int | None) -> str:
    parts = [f"[exit code: {exit_code}]" if exit_code is not None else "[exit code: none]"]
    if stdout:
        parts.append("[stdout]\n" + stdout)
    if stderr:
        parts.append("[stderr]\n" + stderr)
    return "\n".join(parts)


def format_session_output(snapshot: CommandSessionSnapshot) -> str:
    lines = [
        f"[session: {snapshot.session_id}]",
        f"[running: {snapshot.running}]",
        f"[exit code: {snapshot.exit_code}]",
    ]
    if snapshot.stdout:
        lines.append("[stdout]\n" + snapshot.stdout)
    if snapshot.stderr:
        lines.append("[stderr]\n" + snapshot.stderr)
    return "\n".join(lines)


def _terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.terminate()
    except Exception:
        pass


_RUNNER = CommandRunner()
