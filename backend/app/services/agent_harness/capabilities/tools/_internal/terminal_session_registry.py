from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.redis_coordination import get_redis_coordinator

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

# Hint-only registry: when Redis is unavailable the in-process fallback only
# sees writes from the current worker, so cross-worker ownership lookups
# silently return "not_found". Callers must treat the registry as advisory.

TERMINAL_SESSION_TTL_SECONDS = 60.0
# Owners must heartbeat within TTL_SECONDS to stay "running"; the Redis key is
# retained for RETENTION_MULTIPLIER * TTL_SECONDS so describe() can still report
# "expired" (with the previous owner) before the entry is garbage-collected.
TERMINAL_SESSION_RETENTION_MULTIPLIER = 3
TERMINAL_SESSION_OWNER_ID = f"terminal-worker:{os.getpid()}:{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class TerminalOwnershipStatus:
    status: str
    session_id: str
    owner_id: str | None = None
    capabilities: tuple[str, ...] = ()
    expires_at: float | None = None


class TerminalSessionOwnershipRegistry:
    def __init__(
        self,
        *,
        owner_id: str = TERMINAL_SESSION_OWNER_ID,
        ttl_seconds: float = TERMINAL_SESSION_TTL_SECONDS,
    ) -> None:
        self.owner_id = owner_id
        self.ttl_seconds = ttl_seconds

    def _key(self, *, ctx: HarnessContext, session_id: str) -> str:
        coordinator = get_redis_coordinator()
        return coordinator.keys.build(
            domain="terminal-session",
            purpose="ownership",
            resource_parts=[
                str(ctx.user_id),
                str(ctx.conversation_id),
                str(session_id or ""),
            ],
        )

    async def register(self, *, ctx: HarnessContext, session_id: str) -> None:
        await self._write(
            ctx=ctx,
            session_id=session_id,
            status="running",
            ttl_seconds=self.ttl_seconds * TERMINAL_SESSION_RETENTION_MULTIPLIER,
        )

    async def renew(self, *, ctx: HarnessContext, session_id: str) -> None:
        await self.register(ctx=ctx, session_id=session_id)

    async def complete(self, *, ctx: HarnessContext, session_id: str) -> None:
        await self._write(
            ctx=ctx,
            session_id=session_id,
            status="completed",
            ttl_seconds=10.0,
        )

    async def describe(self, *, ctx: HarnessContext, session_id: str) -> TerminalOwnershipStatus:
        payload = await get_redis_coordinator().get_snapshot(self._key(ctx=ctx, session_id=session_id))
        if not isinstance(payload, dict):
            return TerminalOwnershipStatus(status="not_found", session_id=session_id)

        status = str(payload.get("status") or "running")
        owner_id = str(payload.get("owner_id") or "")
        expires_at = _float_or_none(payload.get("expires_at"))
        capabilities = tuple(
            str(item)
            for item in (payload.get("capabilities") or [])
            if str(item or "").strip()
        )
        if status == "completed":
            return TerminalOwnershipStatus(
                status="completed",
                session_id=session_id,
                owner_id=owner_id or None,
                capabilities=capabilities,
                expires_at=expires_at,
            )
        if expires_at is not None and expires_at <= time.time():
            return TerminalOwnershipStatus(
                status="expired",
                session_id=session_id,
                owner_id=owner_id or None,
                capabilities=capabilities,
                expires_at=expires_at,
            )
        if owner_id == self.owner_id:
            return TerminalOwnershipStatus(
                status="local_owner",
                session_id=session_id,
                owner_id=owner_id,
                capabilities=capabilities,
                expires_at=expires_at,
            )
        return TerminalOwnershipStatus(
            status="owned_elsewhere",
            session_id=session_id,
            owner_id=owner_id or None,
            capabilities=capabilities,
            expires_at=expires_at,
        )

    async def _write(
        self,
        *,
        ctx: HarnessContext,
        session_id: str,
        status: str,
        ttl_seconds: float,
    ) -> None:
        now = time.time()
        # `expires_at` marks the end of the active-ownership window used by
        # describe() to distinguish running vs. expired owners. The Redis key
        # itself is retained longer (see TERMINAL_SESSION_RETENTION_MULTIPLIER)
        # so callers can still see "expired" with the previous owner attached.
        await get_redis_coordinator().set_snapshot(
            self._key(ctx=ctx, session_id=session_id),
            {
                "status": status,
                "session_id": str(session_id or ""),
                "owner_id": self.owner_id,
                "started_at": now,
                "expires_at": now + self.ttl_seconds,
                "capabilities": ["read", "stop", "write"],
            },
            ttl_seconds=max(float(ttl_seconds), 1.0),
        )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
