from __future__ import annotations

from .sandbox_manager import SandboxExecutor

_EXECUTOR: SandboxExecutor | None = None


def get_sandbox_executor() -> SandboxExecutor:
    """Return the single sandbox executor.

    There is no longer a local/docker switch: the executor wraps commands in
    bubblewrap when the runtime supports it and degrades to a plain spawn otherwise
    (see ``sandbox_manager.is_sandboxing_available``).
    """
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = SandboxExecutor()
    return _EXECUTOR


def set_sandbox_executor_for_tests(executor: SandboxExecutor | None) -> None:
    global _EXECUTOR
    _EXECUTOR = executor
