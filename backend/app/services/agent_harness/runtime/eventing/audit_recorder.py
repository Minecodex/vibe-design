from __future__ import annotations

from typing import Any


class NoopAgentAuditRecorder:
    async def append_event(self, **_kwargs: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def close(self) -> None:
        return None


def create_agent_audit_recorder(*_args: Any, **_kwargs: Any) -> NoopAgentAuditRecorder:
    return NoopAgentAuditRecorder()
