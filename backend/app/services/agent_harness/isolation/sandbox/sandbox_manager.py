"""Single bubblewrap-based sandbox execution layer.

Faithful port of claude-code's sandbox model (``src/utils/sandbox/sandbox-adapter.ts``
+ ``Shell.ts``). claude-code keeps the *config + lifecycle* in-repo and delegates the
actual ``bwrap`` argv construction to the closed external package
``@anthropic-ai/sandbox-runtime``. There is no Python equivalent of that package, so the
argv construction (the part that translates the filesystem policy into
``bwrap --bind/--ro-bind/--unshare... -- /bin/sh -lc <cmd>``) is reimplemented here using
standard bubblewrap semantics:

    writable_roots  -> --bind      (read-write)
    readonly_roots  -> covered by  --ro-bind / /  (read-only; this is the denyWrite hardening:
                       .meta/.agent/skill/references/published are in readonly_roots)
    network allowed -> NO --unshare-net

Capability detection mirrors ``isSandboxingEnabled()``: if ``bwrap`` is missing or cannot
create namespaces (Windows/macOS dev machines, restricted hosts) we degrade to a plain
``/bin/sh`` spawn so local development and unit tests keep working.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import time
from typing import Any

from app.core.config import settings

from .output_truncation import truncate_stream_output
from .path_guard import validate_cwd
from .types import SandboxRequest, SandboxResult

# System roots that must stay visible (read-only) inside the sandbox for normal tooling
# (interpreters, shared libraries, certs) to work. We start from a whole-root read-only
# bind and re-bind the writable workspace on top; this keeps the recipe robust across
# base images while still confining *writes* to the workspace.
_PROBE_TIMEOUT_SECONDS = 5.0

_bwrap_available: bool | None = None
_probe_lock: asyncio.Lock | None = None


def _bwrap_path() -> str | None:
    configured = str(getattr(settings, "HARNESS_SANDBOX_BWRAP_PATH", "") or "").strip()
    if configured:
        return configured if os.path.isabs(configured) else shutil.which(configured)
    return shutil.which("bwrap")


def _sandbox_setting_enabled() -> bool:
    return bool(getattr(settings, "HARNESS_SANDBOX_ENABLED", True))


def _get_probe_lock() -> asyncio.Lock:
    global _probe_lock
    if _probe_lock is None:
        _probe_lock = asyncio.Lock()
    return _probe_lock


async def is_sandboxing_available() -> bool:
    """Whether bwrap exists *and* can create namespaces in this environment.

    Cached after the first successful/failed probe (mirrors claude-code's memoized
    ``checkDependencies``). A failed probe degrades the executor to a plain spawn.
    """
    global _bwrap_available
    if not _sandbox_setting_enabled():
        return False
    if _bwrap_available is not None:
        return _bwrap_available
    async with _get_probe_lock():
        if _bwrap_available is not None:
            return _bwrap_available
        _bwrap_available = await _probe_bwrap()
    return _bwrap_available


async def _probe_bwrap() -> bool:
    path = _bwrap_path()
    if not path:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            path,
            "--ro-bind", "/", "/",
            "--proc", "/proc",
            "--dev", "/dev",
            "--unshare-pid",
            "--die-with-parent",
            "/bin/true",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=_PROBE_TIMEOUT_SECONDS)
        return proc.returncode == 0
    except Exception:
        return False


def is_sandboxing_configured() -> bool:
    """Sync gate for the permission layer: sandbox enabled and a bwrap binary is present.

    This is intentionally cheaper than ``is_sandboxing_available`` (no namespace probe) so
    it can be called from synchronous permission checks. It answers "would commands run
    under an OS sandbox here?" — the basis for auto-allowing 'ask' verdicts.
    """
    return _sandbox_setting_enabled() and _bwrap_path() is not None


def is_auto_allow_enabled() -> bool:
    """Whether 'ask' verdicts auto-allow under sandbox (mirrors autoAllowBashIfSandboxed)."""
    return bool(getattr(settings, "HARNESS_SANDBOX_AUTO_ALLOW", True))


def auto_allow_if_sandboxed() -> bool:
    """True when an 'ask' command should be allowed because the OS sandbox contains it."""
    return is_sandboxing_configured() and is_auto_allow_enabled()


def reset_sandbox_probe_cache() -> None:
    """Test hook: forget the cached bwrap probe result."""
    global _bwrap_available
    _bwrap_available = None


def build_bwrap_argv(request: SandboxRequest, *, bwrap: str) -> list[str]:
    """Translate the sandbox policy into a bubblewrap invocation.

    Read-only whole-root base + writable workspace bind on top. Network namespace is
    shared (no ``--unshare-net``) because shell commands are allowed to reach the
    network (npm/pip install).
    """
    argv: list[str] = [
        bwrap,
        "--ro-bind", "/", "/",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ]
    for root in request.policy.writable_roots:
        resolved = str(root.resolve())
        argv += ["--bind", resolved, resolved]
    argv += [
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--die-with-parent",
        "--chdir", str(request.cwd),
        "--clearenv",
    ]
    for key, value in request.env.items():
        argv += ["--setenv", key, str(value)]
    argv += ["/bin/sh", "-lc", request.command]
    return argv


def cleanup_after_command() -> None:
    """Post-command cleanup hook (mirrors ``cleanupAfterCommand``).

    bwrap on Linux can leave 0-byte mount-point ghost files for denied paths; the
    whole-root recipe used here does not create such files, so this is currently a
    no-op kept for parity and future bare-git-repo scrubbing.
    """
    return None


class SandboxExecutor:
    """Runs commands wrapped in bubblewrap when available, else degrades to plain spawn.

    Replaces the previous local/docker executor split: the decision is now a runtime
    *capability* (is bwrap usable here?) rather than a static config switch.
    """

    async def run(self, request: SandboxRequest) -> SandboxResult:
        started_at = time.monotonic()
        denied_reason = validate_cwd(
            request.cwd,
            request.policy.writable_roots + request.policy.readonly_roots,
        )
        if denied_reason:
            return SandboxResult(
                denied=True,
                denied_reason=denied_reason,
                elapsed_ms=_elapsed_ms(started_at),
            )

        program, argv, popen_kwargs, sandboxed = await self._spawn_plan(request)
        timeout = min(request.timeout_seconds, request.policy.max_timeout_seconds)
        try:
            proc = await _create_subprocess(program, argv, **popen_kwargs)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                _kill_process_tree(proc)
                return SandboxResult(
                    exit_code=None,
                    elapsed_ms=_elapsed_ms(started_at),
                    timed_out=True,
                )
            except asyncio.CancelledError:
                _kill_process_tree(proc)
                raise
        except Exception as exc:
            return SandboxResult(
                stderr=f"Failed to execute: {exc}",
                exit_code=None,
                elapsed_ms=_elapsed_ms(started_at),
                metadata={"exception_type": type(exc).__name__, "sandboxed": sandboxed},
            )
        finally:
            if sandboxed:
                cleanup_after_command()

        max_bytes = request.policy.max_output_bytes
        stdout_text, stdout_truncated = truncate_stream_output(stdout, max_bytes)
        stderr_text, stderr_truncated = truncate_stream_output(stderr, max_bytes)
        return SandboxResult(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=proc.returncode or 0,
            elapsed_ms=_elapsed_ms(started_at),
            timed_out=False,
            truncated=stdout_truncated or stderr_truncated,
            metadata={
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "max_output_bytes": max_bytes,
                "sandboxed": sandboxed,
            },
        )

    async def spawn(self, request: SandboxRequest) -> asyncio.subprocess.Process:
        """Start a long-running process (for terminal sessions), wrapped in the sandbox.

        Fixes the previous gap where ``start()`` bypassed the sandbox entirely. The
        returned process handle is used by the session manager for read/stop/write;
        ``--die-with-parent`` ensures sandboxed children exit when the bwrap process is
        killed.
        """
        program, argv, popen_kwargs, _sandboxed = await self._spawn_plan(
            request, extra_kwargs={"stdin": asyncio.subprocess.PIPE}
        )
        return await _create_subprocess(program, argv, **popen_kwargs)

    async def _spawn_plan(
        self,
        request: SandboxRequest,
        *,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> tuple[str, list[str], dict[str, Any], bool]:
        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        if hasattr(os, "setsid"):
            kwargs["preexec_fn"] = os.setsid

        bwrap = _bwrap_path()
        if bwrap and await is_sandboxing_available():
            argv = build_bwrap_argv(request, bwrap=bwrap)
            # bwrap drives env via --clearenv/--setenv; the wrapper process itself can
            # inherit the host environment.
            return argv[0], argv[1:], kwargs, True

        # Degraded path: no OS sandbox available (e.g. Windows/macOS dev). Run the shell
        # directly with the workspace cwd + env, matching the prior local executor.
        kwargs["cwd"] = str(request.cwd)
        kwargs["env"] = request.env
        return request.command, [], {**kwargs, "_shell": True}, False


async def _create_subprocess(program: str, argv: list[str], **kwargs: Any) -> asyncio.subprocess.Process:
    shell_mode = kwargs.pop("_shell", False)
    if shell_mode:
        return await asyncio.create_subprocess_shell(program, **kwargs)
    return await asyncio.create_subprocess_exec(program, *argv, **kwargs)


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except Exception:
        pass
