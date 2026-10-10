"""Background reconciler for LingyaAI provider-side billing rows."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from tempfile import gettempdir

try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows
    fcntl = None

from app.core.config import settings
from app.core.datetime_utils import normalize_app_datetime
from app.core.provider_balance_mode import is_provider_balance_sync_enabled
from app.core.providers import get_active_builtin_provider_code
from app.core.redis_coordination import RedisCoordinationDegradedError, get_redis_coordinator
from app.db.session import AsyncSessionLocal
from app.repositories.billing_repository import UsageLogRepository
from app.services.billing_service import BillingService
from app.services.builtin_provider import get_active_builtin_provider
from app.services.provider_request_policy import ProviderRequestPolicy

logger = logging.getLogger(__name__)
_LOCK_PATH = os.path.join(gettempdir(), "lingyaai_billing_reconciler.lock")


def _redis_leader_key() -> str:
    coordinator = get_redis_coordinator()
    return coordinator.keys.build(
        domain="lingyaai-billing",
        purpose="leader",
        resource_parts=["active"],
    )


@dataclass(slots=True)
class SettleDecision:
    log_id: int
    bill: object


@dataclass(slots=True)
class RetryDecision:
    log_id: int
    next_run_at: datetime


@dataclass(slots=True)
class BlockDecision:
    log_id: int
    reason: str


@dataclass(slots=True)
class ReconcilePlan:
    settles: list[SettleDecision]
    retries: list[RetryDecision]
    blocks: list[BlockDecision]


class LingyaAiBillingReconciler:
    _METRIC_KEYS = (
        "leader_acquired",
        "leader_denied",
        "bill_fetch_allowed",
        "bill_fetch_denied",
        "claimed_logs",
        "settled_logs",
        "retried_logs",
        "blocked_logs",
        "failures",
    )

    def __init__(self, *, lock_path: str | None = None) -> None:
        self._task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._lock_path = lock_path or _LOCK_PATH
        self._lock_fd = None
        self._redis_leader_owner: str | None = None
        self._last_bill_rows_fetch_at: datetime | None = None
        self._metrics: dict[str, int] = {key: 0 for key in self._METRIC_KEYS}

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_leader(self) -> bool:
        return self._lock_fd is not None or self._redis_leader_owner is not None

    def metrics_snapshot(self) -> dict[str, int]:
        return {key: int(self._metrics.get(key, 0)) for key in self._METRIC_KEYS}

    def _record_metric(self, key: str, amount: int = 1) -> None:
        if key not in self._metrics:
            return
        self._metrics[key] += int(amount)

    def start(self) -> None:
        if self.is_running:
            return
        self._shutdown_event = asyncio.Event()
        self._task = asyncio.create_task(self._start_and_run_loop(), name="lingyaai-billing-reconciler")

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._task is None:
            self._release_leader_lock()
            return
        try:
            await asyncio.wait_for(self._task, timeout=10)
        except TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        finally:
            self._task = None
            self._release_leader_lock()
        logger.info("LingyaAI billing reconciler stopped")

    async def _try_acquire_leader_lock_async(self) -> bool:
        redis_acquired = await self._try_acquire_redis_leader_lock_async()
        if redis_acquired is not None:
            return redis_acquired
        return self._try_acquire_file_leader_lock()

    def _try_acquire_file_leader_lock(self) -> bool:
        if self._lock_fd is not None:
            self._record_metric("leader_acquired")
            return True
        if fcntl is None:
            logger.warning("fcntl unavailable; starting LingyaAI billing reconciler without leader lock")
            self._record_metric("leader_acquired")
            return True
        lock_fd = open(self._lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_fd.close()
            self._record_metric("leader_denied")
            return False
        self._lock_fd = lock_fd
        self._record_metric("leader_acquired")
        return True

    def _release_leader_lock(self) -> None:
        self._release_redis_leader_lock()
        if self._lock_fd is None:
            return
        if fcntl is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        self._lock_fd.close()
        self._lock_fd = None

    async def _try_acquire_redis_leader_lock_async(self) -> bool | None:
        owner = f"lingyaai-billing-reconciler:{os.getpid()}"
        try:
            result = await get_redis_coordinator().try_acquire_lease(
                _redis_leader_key(),
                owner=owner,
                ttl_seconds=max(float(settings.LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS) * 2, 5.0),
            )
        except Exception:
            return None
        if result.get("reason") == "redis_disabled" or result.get("degraded"):
            return None
        if result.get("acquired"):
            self._redis_leader_owner = owner
            self._record_metric("leader_acquired")
            return True
        self._record_metric("leader_denied")
        return False

    async def _renew_redis_leader_lock_async(self) -> bool:
        owner = self._redis_leader_owner
        if not owner:
            return True
        try:
            result = await get_redis_coordinator().renew_lease(
                _redis_leader_key(),
                owner=owner,
                ttl_seconds=max(float(settings.LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS) * 2, 5.0),
            )
        except Exception:
            return False
        if result.get("reason") == "redis_disabled" or result.get("degraded"):
            return False
        return bool(result.get("renewed"))

    def _release_redis_leader_lock(self) -> None:
        owner = self._redis_leader_owner
        if not owner:
            return
        self._redis_leader_owner = None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(get_redis_coordinator().release_lease(_redis_leader_key(), owner=owner))
            except Exception:
                return
            return
        try:
            asyncio.create_task(get_redis_coordinator().release_lease(_redis_leader_key(), owner=owner))
        except Exception:
            return

    async def _run_loop(self) -> None:
        interval = max(float(settings.LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS), 0.1)
        while not self._shutdown_event.is_set():
            if not await self._renew_redis_leader_lock_async():
                logger.info("Stopping LingyaAI billing reconciler because Redis leader lease could not be renewed")
                return
            try:
                await self.run_once()
            except Exception:
                logger.exception("LingyaAI billing reconciler tick failed")
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _start_and_run_loop(self) -> None:
        interval = max(float(settings.LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS), 0.1)
        while not self._shutdown_event.is_set():
            if not await self._try_acquire_leader_lock_async():
                logger.info("LingyaAI billing reconciler is follower; retrying leader acquisition later")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue
                continue
            logger.info("Started LingyaAI billing reconciler")
            try:
                await self._run_loop()
            finally:
                self._release_leader_lock()
            if not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue

    async def run_once(self) -> int:
        # LingyaAI reconciliation is retired with the global provider key.
        return 0

    def _can_fetch_bill_rows(self, now: datetime) -> bool:
        min_interval_seconds = self._min_fetch_interval_seconds()
        if min_interval_seconds <= 0:
            return True
        if self._last_bill_rows_fetch_at is None:
            return True
        return (now - self._last_bill_rows_fetch_at).total_seconds() >= min_interval_seconds

    @staticmethod
    def _min_fetch_interval_seconds() -> float:
        window_seconds = max(float(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS), 0.0)
        max_fetches = max(int(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT), 0)
        if window_seconds <= 0 or max_fetches <= 0:
            return 0.0
        return window_seconds / max_fetches

    async def _allow_distributed_bill_rows_fetch(self) -> bool:
        try:
            decision = await ProviderRequestPolicy(namespace="lingyaai-billing").allow(
                provider="lingyaai",
                operation="billing_fetch",
                priority="background",
                limit=max(int(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT), 0),
                window_seconds=max(float(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS), 0.001),
            )
        except RedisCoordinationDegradedError:
            # REDIS_REQUIRED=True but Redis is unavailable: deny rather than
            # silently fall back to single-worker rate-limit semantics.
            self._record_metric("bill_fetch_denied")
            return False
        self._record_metric("bill_fetch_allowed" if decision.allowed else "bill_fetch_denied")
        return decision.allowed

    def _build_reconcile_plan(self, *, claimed: list[object], rows: list[dict], provider, now: datetime) -> ReconcilePlan:
        settles: list[SettleDecision] = []
        retries: list[RetryDecision] = []
        blocks: list[BlockDecision] = []
        for log in claimed:
            if not log.provider_request_id:
                blocks.append(BlockDecision(log_id=log.id, reason="lingyaai_missing_oneapi_request_id"))
                continue

            bill = provider.match_bill_from_rows(
                rows,
                provider_request_id=log.provider_request_id,
                provider_trace_id=log.provider_trace_id,
                provider_task_id=log.provider_task_id,
            )
            if bill is not None:
                settles.append(SettleDecision(log_id=log.id, bill=bill))
                continue

            if self._should_manual_review(log, now):
                blocks.append(BlockDecision(log_id=log.id, reason="lingyaai_bill_not_found"))
                continue

            retries.append(
                RetryDecision(
                    log_id=log.id,
                    next_run_at=now + timedelta(seconds=self._retry_delay_seconds(log, now)),
                )
            )
        return ReconcilePlan(settles=settles, retries=retries, blocks=blocks)

    @staticmethod
    def _age_seconds(log, now: datetime) -> float:
        created = normalize_app_datetime(getattr(log, "created_at", None)) or now
        return max((now - created).total_seconds(), 0)

    def _should_manual_review(self, log, now: datetime) -> bool:
        return self._age_seconds(log, now) >= max(
            int(settings.LINGYAAI_BILLING_MANUAL_REVIEW_AFTER_SECONDS),
            1,
        )

    def _retry_delay_seconds(self, log, now: datetime) -> int:
        age = self._age_seconds(log, now)
        if age < max(int(settings.LINGYAAI_BILLING_FAST_RETRY_SECONDS), 1):
            return max(int(settings.LINGYAAI_BILLING_FAST_RETRY_DELAY_SECONDS), 1)
        if age < 300:
            return max(int(settings.LINGYAAI_BILLING_NORMAL_RETRY_DELAY_SECONDS), 1)
        return max(int(settings.LINGYAAI_BILLING_SLOW_RETRY_DELAY_SECONDS), 1)


lingyaai_billing_reconciler = LingyaAiBillingReconciler()
