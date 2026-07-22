from __future__ import annotations

import time

import pytest

from app.core.redis_coordination import RedisKeyBuilder
from app.services.background_scheduler_owner import BackgroundSchedulerOwner


@pytest.mark.asyncio
async def test_scheduler_owner_allows_only_one_manager_to_start_schedulers():
    coordinator = _FakeLeaseCoordinator()
    first_generation = _FakeGenerationScheduler()
    first_operation = _FakeOperationScheduler()
    second_generation = _FakeGenerationScheduler()
    second_operation = _FakeOperationScheduler()
    first = BackgroundSchedulerOwner(
        owner_id="worker-a",
        generation_scheduler=first_generation,
        operation_scheduler=first_operation,
        coordinator_factory=lambda: coordinator,
    )
    second = BackgroundSchedulerOwner(
        owner_id="worker-b",
        generation_scheduler=second_generation,
        operation_scheduler=second_operation,
        coordinator_factory=lambda: coordinator,
    )

    await first._try_acquire_ownership()
    await second._try_acquire_ownership()

    assert first.status()["is_owner"] is True
    assert second.status()["is_owner"] is False
    assert first_generation.calls == ["recover", "start"]
    assert first_operation.calls == ["start"]
    assert second_generation.calls == []
    assert second_operation.calls == []


@pytest.mark.asyncio
async def test_scheduler_owner_renew_failure_stops_owned_schedulers():
    coordinator = _FakeLeaseCoordinator()
    generation = _FakeGenerationScheduler()
    operation = _FakeOperationScheduler()
    owner = BackgroundSchedulerOwner(
        owner_id="worker-a",
        generation_scheduler=generation,
        operation_scheduler=operation,
        coordinator_factory=lambda: coordinator,
    )
    await owner._try_acquire_ownership()
    coordinator.owner = "worker-b"

    await owner._renew_ownership()

    assert owner.status()["is_owner"] is False
    assert generation.calls == ["recover", "start", "shutdown"]
    assert operation.calls == ["start", "shutdown"]


@pytest.mark.asyncio
async def test_scheduler_owner_can_take_over_after_lease_expiry():
    coordinator = _FakeLeaseCoordinator()
    first = BackgroundSchedulerOwner(
        owner_id="worker-a",
        lease_ttl_seconds=1,
        generation_scheduler=_FakeGenerationScheduler(),
        operation_scheduler=_FakeOperationScheduler(),
        coordinator_factory=lambda: coordinator,
    )
    second_generation = _FakeGenerationScheduler()
    second_operation = _FakeOperationScheduler()
    second = BackgroundSchedulerOwner(
        owner_id="worker-b",
        lease_ttl_seconds=1,
        generation_scheduler=second_generation,
        operation_scheduler=second_operation,
        coordinator_factory=lambda: coordinator,
    )

    await first._try_acquire_ownership()
    coordinator.expires_at = time.monotonic() - 1
    await second._try_acquire_ownership()

    assert second.status()["is_owner"] is True
    assert second_generation.calls == ["recover", "start"]
    assert second_operation.calls == ["start"]


@pytest.mark.asyncio
async def test_scheduler_owner_does_not_start_on_degraded_redis_fallback():
    coordinator = _FakeLeaseCoordinator(reason="redis_unavailable")
    generation = _FakeGenerationScheduler()
    operation = _FakeOperationScheduler()
    owner = BackgroundSchedulerOwner(
        owner_id="worker-a",
        generation_scheduler=generation,
        operation_scheduler=operation,
        coordinator_factory=lambda: coordinator,
    )

    await owner._try_acquire_ownership()

    assert owner.status()["is_owner"] is False
    assert generation.calls == []
    assert operation.calls == []


class _FakeLeaseCoordinator:
    def __init__(self, *, reason: str | None = None) -> None:
        self.keys = RedisKeyBuilder(namespace="test")
        self.owner: str | None = None
        self.expires_at = 0.0
        self.reason = reason

    async def try_acquire_lease(self, _key: str, *, owner: str, ttl_seconds: float):
        now = time.monotonic()
        if self.owner is not None and self.expires_at > now:
            return {"acquired": self.owner == owner, "owner": self.owner, "reason": self.reason}
        self.owner = owner
        self.expires_at = now + ttl_seconds
        return {"acquired": True, "owner": owner, "reason": self.reason}

    async def renew_lease(self, _key: str, *, owner: str, ttl_seconds: float):
        if self.owner != owner:
            return {"renewed": False, "owner": self.owner, "reason": self.reason}
        self.expires_at = time.monotonic() + ttl_seconds
        return {"renewed": True, "owner": owner, "reason": self.reason}

    async def release_lease(self, _key: str, *, owner: str):
        if self.owner != owner:
            return False
        self.owner = None
        return True


class _FakeGenerationScheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def recover_on_startup(self):
        self.calls.append("recover")

    def start_scheduler_loop(self):
        self.calls.append("start")

    async def shutdown(self):
        self.calls.append("shutdown")


class _FakeOperationScheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self):
        self.calls.append("start")

    async def shutdown(self):
        self.calls.append("shutdown")
