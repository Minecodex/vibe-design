from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.redis_coordination import RedisCoordinationDegradedError, get_redis_coordinator
from app.services.provider_operation_scheduler import provider_operation_scheduler
from app.services.task_poller import task_poller

logger = logging.getLogger(__name__)

_LEASE_TTL_SECONDS = 30.0
_LEASE_RENEW_INTERVAL_SECONDS = 10.0


class BackgroundSchedulerOwner:
    """Single-process owner for duplicated background scheduler loops.

    DB task claims remain the correctness boundary. This Redis lease only
    prevents every gunicorn/uvicorn worker from running the idle scheduler
    loops and holding duplicate wakeup subscriptions.
    """

    def __init__(
        self,
        *,
        owner_id: str | None = None,
        lease_ttl_seconds: float = _LEASE_TTL_SECONDS,
        renew_interval_seconds: float = _LEASE_RENEW_INTERVAL_SECONDS,
        generation_scheduler: Any = task_poller,
        operation_scheduler: Any = provider_operation_scheduler,
        coordinator_factory=get_redis_coordinator,
    ) -> None:
        self.owner_id = owner_id or _default_owner_id()
        self.lease_ttl_seconds = max(float(lease_ttl_seconds), 1.0)
        self.renew_interval_seconds = max(float(renew_interval_seconds), 0.5)
        self._generation_scheduler = generation_scheduler
        self._operation_scheduler = operation_scheduler
        self._coordinator_factory = coordinator_factory
        self._task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._owns_lease = False
        self._schedulers_running = False
        self._lease_owner: str | None = None
        self._lease_expires_at: datetime | None = None
        self._last_lease_reason: str | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._shutdown_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="background-scheduler-owner")

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            finally:
                self._task = None
        await self._stop_owned_schedulers()
        await self._release_lease()

    def status(self) -> dict[str, Any]:
        return {
            "is_owner": bool(self._owns_lease),
            "owner_id": self.owner_id if self._owns_lease else self._lease_owner,
            "lease_expires_at": self._lease_expires_at.isoformat() if self._lease_expires_at else None,
            "lease_reason": self._last_lease_reason,
            "manager_running": self._task is not None and not self._task.done(),
        }

    async def _run_loop(self) -> None:
        try:
            while not self._shutdown_event.is_set():
                try:
                    if self._owns_lease:
                        await self._renew_ownership()
                    else:
                        await self._try_acquire_ownership()
                except asyncio.CancelledError:
                    raise
                except RedisCoordinationDegradedError as exc:
                    logger.info("Scheduler owner lease unavailable: reason=%s", exc.reason)
                    self._last_lease_reason = exc.reason
                    await self._lose_ownership(owner=None)
                except Exception:
                    logger.info("Scheduler owner tick failed", exc_info=True)
                    await self._lose_ownership(owner=None)

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.renew_interval_seconds,
                    )
                except TimeoutError:
                    continue
        finally:
            await self._stop_owned_schedulers()
            await self._release_lease()

    async def _try_acquire_ownership(self) -> None:
        coordinator = self._coordinator_factory()
        result = await coordinator.try_acquire_lease(
            self._lease_key(coordinator),
            owner=self.owner_id,
            ttl_seconds=self.lease_ttl_seconds,
        )
        self._record_lease_result(result)
        if _lease_acquired_for_this_worker(result, self.owner_id):
            await self._start_owned_schedulers()
            self._owns_lease = True
            return
        await self._lose_ownership(owner=result.get("owner"))

    async def _renew_ownership(self) -> None:
        coordinator = self._coordinator_factory()
        result = await coordinator.renew_lease(
            self._lease_key(coordinator),
            owner=self.owner_id,
            ttl_seconds=self.lease_ttl_seconds,
        )
        self._record_lease_result(result)
        if bool(result.get("renewed")) and str(result.get("owner") or "") == self.owner_id:
            return
        await self._lose_ownership(owner=result.get("owner"))

    async def _start_owned_schedulers(self) -> None:
        if self._schedulers_running:
            return
        await self._generation_scheduler.recover_on_startup()
        self._generation_scheduler.start_scheduler_loop()
        self._operation_scheduler.start()
        self._schedulers_running = True
        logger.info("Background scheduler owner acquired: owner=%s", self.owner_id)

    async def _stop_owned_schedulers(self) -> None:
        if not self._schedulers_running:
            return
        await self._operation_scheduler.shutdown()
        await self._generation_scheduler.shutdown()
        self._schedulers_running = False
        logger.info("Background scheduler owner stopped schedulers: owner=%s", self.owner_id)

    async def _lose_ownership(self, *, owner: Any) -> None:
        self._owns_lease = False
        self._lease_owner = str(owner) if owner else None
        self._lease_expires_at = None
        await self._stop_owned_schedulers()

    async def _release_lease(self) -> None:
        if not self._owns_lease:
            return
        self._owns_lease = False
        try:
            coordinator = self._coordinator_factory()
            await coordinator.release_lease(self._lease_key(coordinator), owner=self.owner_id)
        except Exception:
            logger.info("Scheduler owner lease release failed", exc_info=True)
        finally:
            self._lease_expires_at = None

    def _record_lease_result(self, result: dict[str, Any]) -> None:
        self._last_lease_reason = str(result.get("reason") or "") or None
        owner = result.get("owner")
        self._lease_owner = str(owner) if owner else None
        if _lease_acquired_for_this_worker(result, self.owner_id) or bool(result.get("renewed")):
            self._lease_expires_at = datetime.now(UTC) + timedelta(seconds=self.lease_ttl_seconds)

    @staticmethod
    def _lease_key(coordinator: Any) -> str:
        return coordinator.keys.build(
            domain="backend-schedulers",
            purpose="owner",
            resource_parts=("global",),
        )


def _default_owner_id() -> str:
    return f"backend-scheduler:{socket.gethostname()}:{os.getpid()}"


def _lease_acquired_for_this_worker(result: dict[str, Any], owner_id: str) -> bool:
    reason = str(result.get("reason") or "")
    if reason and reason != "redis_disabled":
        return False
    return bool(result.get("acquired")) and str(result.get("owner") or "") == owner_id


background_scheduler_owner = BackgroundSchedulerOwner()
