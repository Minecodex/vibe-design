from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey

DERIVED_ARTIFACT_GUARD_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class DerivedArtifactGuardHandle:
    acquired: bool
    key: str
    status_key: str
    owner: str
    status: dict[str, Any] | None = None


class DerivedArtifactGuard:
    def __init__(self, *, ttl_seconds: float = DERIVED_ARTIFACT_GUARD_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self.coordinator = EphemeralTaskCoordinator(ttl_seconds=ttl_seconds)

    def _task(
        self,
        *,
        artifact_identity: str,
        transform_type: str,
        version: str,
    ) -> EphemeralTaskKey:
        return EphemeralTaskKey.build(
            domain="derived-artifact",
            kind="build",
            resource_parts=[
                str(artifact_identity or ""),
                str(transform_type or ""),
            ],
            version=version,
        )

    async def start(
        self,
        *,
        artifact_identity: str,
        transform_type: str,
        version: str,
    ) -> DerivedArtifactGuardHandle:
        task = self._task(
            artifact_identity=artifact_identity,
            transform_type=transform_type,
            version=version,
        )
        lease = await self.coordinator.start(
            task,
            ttl_seconds=self.ttl_seconds,
            owner_prefix="derived",
            status_payload={"transform_type": str(transform_type or "")},
        )
        if not lease.acquired:
            return DerivedArtifactGuardHandle(
                acquired=False,
                key=lease.key,
                status_key=lease.status_key,
                owner=lease.owner,
                status=lease.status,
            )

        return DerivedArtifactGuardHandle(
            acquired=True,
            key=lease.key,
            status_key=lease.status_key,
            owner=lease.owner,
        )

    async def finish(self, handle: DerivedArtifactGuardHandle, *, status: str) -> None:
        await self.coordinator.finish(_lease_from_handle(handle), status=status, ttl_seconds=self.ttl_seconds)

    async def fail(self, handle: DerivedArtifactGuardHandle, *, error_type: str) -> None:
        await self.coordinator.fail(_lease_from_handle(handle), error_type=error_type, ttl_seconds=self.ttl_seconds)


def _lease_from_handle(handle: DerivedArtifactGuardHandle):
    from app.services.ephemeral_task_coordinator import EphemeralTaskLease

    return EphemeralTaskLease(
        acquired=True,
        task=EphemeralTaskKey.build(domain="derived-artifact", kind="build"),
        key=handle.key,
        status_key=handle.status_key,
        owner=handle.owner,
    )
