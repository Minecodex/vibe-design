from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.harness_session import harness_sync_session_scope, run_harness_db
from app.models.harness_session import HarnessResourceLease

from .labels import RESOURCE_GPU
from .scheduler import get_agent_resource_scheduler

T = TypeVar("T")

OWNER_AGENT = "agent"
OWNER_MEDIA = "media"
OWNER_BACKGROUND = "background"
GPU_LEASE_SECONDS = 120
GPU_ACQUIRE_POLL_SECONDS = 0.25
GPU_ACQUIRE_TIMEOUT_SECONDS = 0.0
GPU_SLOT_COUNT = 1

_OWNER_PRIORITIES = {
    OWNER_AGENT: 100,
    OWNER_MEDIA: 10,
    OWNER_BACKGROUND: 1,
}


@dataclass(frozen=True)
class GpuLeaseHandle:
    holder_id: str
    owner_domain: str
    slot_index: int
    lease_seconds: int


class GpuLeaseLostError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _gpu_slot_count() -> int:
    return GPU_SLOT_COUNT


def _lease_seconds() -> int:
    return GPU_LEASE_SECONDS


def _owner_priority(owner_domain: str) -> int:
    return _OWNER_PRIORITIES.get(str(owner_domain or ""), 0)


def _try_acquire_gpu_lease(
    *,
    holder_id: str,
    owner_domain: str,
    slot_count: int,
    lease_seconds: int,
) -> GpuLeaseHandle | None:
    now = _utcnow()
    expires_at = now + timedelta(seconds=lease_seconds)
    priority = _owner_priority(owner_domain)
    with harness_sync_session_scope() as session:
        for slot_index in range(slot_count):
            row = session.scalars(
                select(HarnessResourceLease)
                .where(
                    HarnessResourceLease.resource_type == RESOURCE_GPU,
                    HarnessResourceLease.slot_index == slot_index,
                )
                .with_for_update()
            ).first()
            if row is None:
                row = HarnessResourceLease(
                    resource_type=RESOURCE_GPU,
                    slot_index=slot_index,
                    holder_id=holder_id,
                    owner_domain=owner_domain,
                    owner_priority=priority,
                    expires_at=expires_at,
                    acquired_at=now,
                    last_renewed_at=now,
                )
                session.add(row)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    return None
                return GpuLeaseHandle(
                    holder_id=holder_id,
                    owner_domain=owner_domain,
                    slot_index=slot_index,
                    lease_seconds=lease_seconds,
                )
            if row.holder_id == holder_id or row.expires_at <= now:
                row.holder_id = holder_id
                row.owner_domain = owner_domain
                row.owner_priority = priority
                row.expires_at = expires_at
                row.acquired_at = now
                row.last_renewed_at = now
                row.updated_at = now
                session.flush()
                return GpuLeaseHandle(
                    holder_id=holder_id,
                    owner_domain=owner_domain,
                    slot_index=slot_index,
                    lease_seconds=lease_seconds,
                )
    return None


def _renew_gpu_lease(handle: GpuLeaseHandle) -> bool:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        row = session.scalars(
            select(HarnessResourceLease)
            .where(
                HarnessResourceLease.resource_type == RESOURCE_GPU,
                HarnessResourceLease.slot_index == handle.slot_index,
            )
            .with_for_update()
        ).first()
        if row is None or row.holder_id != handle.holder_id:
            return False
        row.expires_at = now + timedelta(seconds=handle.lease_seconds)
        row.last_renewed_at = now
        row.updated_at = now
        session.flush()
        return True


def _release_gpu_lease(handle: GpuLeaseHandle) -> None:
    with harness_sync_session_scope() as session:
        session.execute(
            delete(HarnessResourceLease).where(
                HarnessResourceLease.resource_type == RESOURCE_GPU,
                HarnessResourceLease.slot_index == handle.slot_index,
                HarnessResourceLease.holder_id == handle.holder_id,
            )
        )


async def _renew_until_released(
    handle: GpuLeaseHandle,
    stop_event: asyncio.Event,
    *,
    owner_task: asyncio.Task | None = None,
) -> None:
    interval = max(float(handle.lease_seconds) / 3.0, 1.0)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            renewed = await run_harness_db(_renew_gpu_lease, handle)
            if not renewed:
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
                raise GpuLeaseLostError(f"Lost {RESOURCE_GPU} lease for slot {handle.slot_index}")


async def _await_renew_task_loss(renew_task: asyncio.Task) -> GpuLeaseLostError | None:
    if not renew_task.done():
        return None
    try:
        await renew_task
    except GpuLeaseLostError as exc:
        return exc
    except asyncio.CancelledError:
        return None
    return None


@asynccontextmanager
async def acquire_gpu_guard(
    *,
    owner_domain: str = OWNER_AGENT,
    holder_id: str | None = None,
    tool_name: str | None = None,
) -> AsyncIterator[GpuLeaseHandle | None]:
    del tool_name
    holder_id = holder_id or f"{owner_domain}-{uuid.uuid4().hex}"
    lease_seconds = _lease_seconds()
    poll_seconds = max(GPU_ACQUIRE_POLL_SECONDS, 0.05)
    timeout_seconds = max(GPU_ACQUIRE_TIMEOUT_SECONDS, 0.0)
    started = time.monotonic()
    handle: GpuLeaseHandle | None = None
    while handle is None:
        handle = await run_harness_db(
            _try_acquire_gpu_lease,
            holder_id=holder_id,
            owner_domain=str(owner_domain or OWNER_BACKGROUND),
            slot_count=_gpu_slot_count(),
            lease_seconds=lease_seconds,
        )
        if handle is not None:
            break
        if timeout_seconds > 0 and time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(f"Timed out waiting for {RESOURCE_GPU} resource")
        await asyncio.sleep(poll_seconds)

    stop_event = asyncio.Event()
    owner_task = asyncio.current_task()
    renew_task = asyncio.create_task(_renew_until_released(handle, stop_event, owner_task=owner_task))
    lease_lost: GpuLeaseLostError | None = None
    body_failed = False
    try:
        try:
            yield handle
        except asyncio.CancelledError:
            body_failed = True
            lease_lost = await _await_renew_task_loss(renew_task)
            if lease_lost is not None:
                raise lease_lost from None
            raise
        except BaseException:
            body_failed = True
            raise
    finally:
        stop_event.set()
        if not renew_task.done():
            renew_task.cancel()
        lease_lost = lease_lost or await _await_renew_task_loss(renew_task)
        await run_harness_db(_release_gpu_lease, handle)
        if lease_lost is not None and not body_failed:
            raise lease_lost


async def run_gpu_task(
    fn: Callable[..., Awaitable[T]],
    *args,
    owner_domain: str = OWNER_AGENT,
    **kwargs,
) -> T:
    async with get_agent_resource_scheduler().acquire(RESOURCE_GPU, owner_domain=owner_domain):
        return await fn(*args, **kwargs)
