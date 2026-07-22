from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey, EphemeralTaskLease

RETRY_GUARD_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class RetryGuardHandle:
    acquired: bool
    key: str
    status_key: str
    owner: str
    version: str = "default"
    status: dict[str, Any] | None = None


class GenerationArtifactRetryCoordinator:
    """Redis-backed duplicate guard for generation artifact retry attempts."""

    def __init__(self, *, ttl_seconds: float = RETRY_GUARD_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self.coordinator = EphemeralTaskCoordinator(ttl_seconds=ttl_seconds)

    def _task(
        self,
        *,
        conversation_id: str,
        artifact_ref: str,
        current_task_id: str | None,
    ) -> EphemeralTaskKey:
        return EphemeralTaskKey.build(
            domain="generation-artifact",
            kind="retry",
            resource_parts=[
                str(conversation_id or ""),
                str(artifact_ref or ""),
            ],
            version=str(current_task_id or "none"),
        )

    async def start(
        self,
        *,
        conversation_id: str,
        artifact_ref: str,
        current_task_id: str | None,
        source: str,
    ) -> RetryGuardHandle:
        task = self._task(
            conversation_id=conversation_id,
            artifact_ref=artifact_ref,
            current_task_id=current_task_id,
        )
        lease = await self.coordinator.start(
            task,
            ttl_seconds=self.ttl_seconds,
            owner_prefix="retry",
            status_payload={
                "source": str(source or ""),
                "artifact_ref": str(artifact_ref or ""),
                "task_id": str(current_task_id or ""),
            },
        )
        return RetryGuardHandle(
            acquired=lease.acquired,
            key=lease.key,
            status_key=lease.status_key,
            owner=lease.owner,
            version=task.version,
            status=lease.status,
        )

    async def finish(
        self,
        handle: RetryGuardHandle,
        *,
        artifact_ref: str,
        task_id: str | None,
        status: str,
    ) -> None:
        await self.coordinator.finish(
            _lease_from_handle(handle),
            status=str(status or "processing"),
            result={"artifact_ref": str(artifact_ref or ""), "task_id": str(task_id or "")},
            ttl_seconds=self.ttl_seconds,
        )

    async def fail(
        self,
        handle: RetryGuardHandle,
        *,
        artifact_ref: str,
        error_type: str,
    ) -> None:
        del artifact_ref
        await self.coordinator.fail(
            _lease_from_handle(handle),
            error_type=str(error_type or "retry_failed"),
            ttl_seconds=self.ttl_seconds,
        )


def _lease_from_handle(handle: RetryGuardHandle) -> EphemeralTaskLease:
    return EphemeralTaskLease(
        acquired=True,
        task=EphemeralTaskKey.build(
            domain="generation-artifact",
            kind="retry",
            version=handle.version,
        ),
        key=handle.key,
        status_key=handle.status_key,
        owner=handle.owner,
    )
