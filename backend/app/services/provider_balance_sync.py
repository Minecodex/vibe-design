from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apimart_key_fingerprint import get_apimart_key_fingerprint
from app.core.config import REDIS_NAMESPACE, settings
from app.core.redis_coordination import RedisCoordinationDegradedError, get_redis_coordinator
from app.db.session import LoopSafeAsyncSessionLocal
from app.repositories.user_apimart_credential_repository import UserApimartCredentialRepository
from app.services.apimart_client import ApimartClient
from app.services.provider_request_policy import ProviderRequestPolicy

logger = logging.getLogger(__name__)

UNLIMITED_PROVIDER_BALANCE_CENTS = 2_147_483_647
APIMART_BALANCE_YUAN_MULTIPLIER = Decimal("10")


def _money_cents(value: Decimal) -> int:
    return max(int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), 0)


def calculate_apimart_balance_cents(payload: dict) -> int:
    if not payload.get("success", True):
        raise ValueError("apimart balance response was not successful")
    if payload.get("unlimited_quota"):
        return UNLIMITED_PROVIDER_BALANCE_CENTS
    remain_balance = Decimal(str(payload["remain_balance"]))
    return _money_cents(remain_balance * APIMART_BALANCE_YUAN_MULTIPLIER * Decimal("100"))


@dataclass(slots=True)
class ProviderBalanceSnapshot:
    balance_cents: int
    synced_at: datetime
    status: str = "ok"


@dataclass(slots=True)
class _CredentialGroup:
    fingerprint: str
    api_key: str
    credential_ids: list[int]


@dataclass(slots=True)
class _KeySyncResult:
    fingerprint: str
    status: str
    credential_ids: list[int]


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
ClientFactory = Callable[[str], ApimartClient]


def _redis_snapshot_key(fingerprint: str) -> str:
    # The HMAC is already a safe, fixed-width identifier. Do not pass the raw key
    # through the generic key builder, because that would make accidental key
    # exposure possible at the call site.
    return f"{REDIS_NAMESPACE}:provider-balance:apimart:v1:{fingerprint}"


def _redis_leader_key() -> str:
    return f"{REDIS_NAMESPACE}:provider-balance:apimart:v1:leader"


def _redis_cycle_status_key() -> str:
    return f"{REDIS_NAMESPACE}:provider-balance:apimart:v1:cycle-status"


def _http_status(payload: dict[str, Any]) -> int | None:
    for value in (payload.get("_status_code"), payload.get("code")):
        if isinstance(value, bool):
            continue
        try:
            status_code = int(value)
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599:
            return status_code
    return None


class ProviderBalanceSyncService:
    """Synchronize and read APIMart balance snapshots keyed by API-key HMAC."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._session_factory = session_factory or LoopSafeAsyncSessionLocal
        self._client_factory = client_factory or ApimartClient
        self._cycle_status: dict[str, object] = {
            "worker_running": False,
            "last_cycle_started_at": None,
            "last_cycle_completed_at": None,
            "credentials_scanned": 0,
            "unique_keys": 0,
            "synced": 0,
            "invalid": 0,
            "failed": 0,
        }

    async def get_balance_cents(self, api_key: str | None = None) -> int:
        if not str(api_key or "").strip():
            return 0
        fingerprint = get_apimart_key_fingerprint(str(api_key))
        snapshot = await self._read_redis_snapshot(fingerprint)
        if snapshot is None or snapshot.status != "ok":
            return 0
        return max(int(snapshot.balance_cents), 0)

    async def get_sync_status(self) -> dict[str, object]:
        try:
            if await self._redis_is_available():
                payload = await get_redis_coordinator().get_snapshot(
                    _redis_cycle_status_key()
                )
                if isinstance(payload, dict):
                    return dict(payload)
        except Exception:
            pass
        return dict(self._cycle_status)

    async def set_worker_running(self, running: bool) -> None:
        status = await self.get_sync_status()
        status["worker_running"] = bool(running)
        self._cycle_status = dict(status)
        await self._write_cycle_status()

    def apply_snapshot(self, snapshot: ProviderBalanceSnapshot) -> None:
        # Retained for compatibility with realtime listener construction. Per-key
        # snapshots are always read from Redis and never cached in-process.
        del snapshot

    def invalidate_local_snapshot(self) -> None:
        return None

    async def sync_once(self, *, now: datetime | None = None) -> bool:
        started_at = now or datetime.now(UTC)
        self._cycle_status = {
            "worker_running": True,
            "last_cycle_started_at": started_at.isoformat(),
            "last_cycle_completed_at": None,
            "credentials_scanned": 0,
            "unique_keys": 0,
            "synced": 0,
            "invalid": 0,
            "failed": 0,
        }
        await self._write_cycle_status()
        try:
            groups, scanned = await self._load_credential_groups()
            self._cycle_status["credentials_scanned"] = scanned
            self._cycle_status["unique_keys"] = len(groups)
            semaphore = asyncio.Semaphore(
                max(int(settings.PROVIDER_BALANCE_SYNC_MAX_CONCURRENCY), 1)
            )
            results = await asyncio.gather(
                *(self._sync_group(group, semaphore, started_at) for group in groups),
                return_exceptions=True,
            )
            invalid_ids: list[int] = []
            for result in results:
                if isinstance(result, BaseException):
                    self._cycle_status["failed"] = int(self._cycle_status["failed"]) + 1
                    logger.warning(
                        "APIMart balance sync failed: error_type=%s",
                        type(result).__name__,
                    )
                    continue
                self._cycle_status[result.status] = int(self._cycle_status[result.status]) + 1
                if result.status == "invalid":
                    invalid_ids.extend(result.credential_ids)
            if invalid_ids:
                await self._mark_credentials_invalid(invalid_ids)
            return True
        except Exception as exc:
            self._cycle_status["failed"] = int(self._cycle_status["failed"]) + 1
            logger.warning(
                "APIMart balance sync cycle failed: error_type=%s",
                type(exc).__name__,
            )
            return False
        finally:
            self._cycle_status["last_cycle_completed_at"] = datetime.now(UTC).isoformat()
            await self._write_cycle_status()

    async def _load_credential_groups(self) -> tuple[list[_CredentialGroup], int]:
        grouped: dict[str, _CredentialGroup] = {}
        scanned = 0
        after_id = 0
        page_size = max(int(settings.PROVIDER_BALANCE_SYNC_BATCH_SIZE), 1)
        async with self._session_factory() as db:
            repo = UserApimartCredentialRepository(db)
            while True:
                page = await repo.list_current_active_after_id(after_id, page_size)
                if not page:
                    break
                scanned += len(page)
                for credential in page:
                    fingerprint = get_apimart_key_fingerprint(credential.api_key)
                    group = grouped.get(fingerprint)
                    if group is None:
                        grouped[fingerprint] = _CredentialGroup(
                            fingerprint=fingerprint,
                            api_key=credential.api_key,
                            credential_ids=[credential.id],
                        )
                    else:
                        group.credential_ids.append(credential.id)
                after_id = int(page[-1].id)
                if len(page) < page_size:
                    break
        return list(grouped.values()), scanned

    async def _sync_group(
        self,
        group: _CredentialGroup,
        semaphore: asyncio.Semaphore,
        synced_at: datetime,
    ) -> _KeySyncResult:
        fingerprint_prefix = group.fingerprint[:12]
        async with semaphore:
            try:
                decision = await ProviderRequestPolicy(namespace="provider-balance").allow(
                    provider=f"apimart:{group.fingerprint}",
                    operation="balance_fetch",
                    priority="background",
                    limit=max(int(settings.PROVIDER_RATE_LIMIT_BALANCE_FETCH_LIMIT), 1),
                    window_seconds=max(
                        float(settings.PROVIDER_RATE_LIMIT_BALANCE_FETCH_WINDOW_SECONDS),
                        0.001,
                    ),
                )
            except RedisCoordinationDegradedError:
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)
            if not decision.allowed:
                logger.info(
                    "APIMart balance fetch rate limited: fingerprint=%s credentials=%s",
                    fingerprint_prefix,
                    len(group.credential_ids),
                )
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)

            try:
                payload = await self._client_factory(group.api_key).get_balance()
            except Exception as exc:
                logger.warning(
                    "APIMart balance fetch failed: fingerprint=%s credentials=%s error_type=%s",
                    fingerprint_prefix,
                    len(group.credential_ids),
                    type(exc).__name__,
                )
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)

            status_code = _http_status(payload)
            if status_code in {401, 403}:
                await self._write_redis_snapshot(
                    group.fingerprint,
                    ProviderBalanceSnapshot(
                        balance_cents=0,
                        synced_at=synced_at,
                        status="invalid",
                    ),
                )
                logger.warning(
                    "APIMart key rejected: fingerprint=%s credentials=%s status=%s",
                    fingerprint_prefix,
                    len(group.credential_ids),
                    status_code,
                )
                return _KeySyncResult(group.fingerprint, "invalid", group.credential_ids)
            if status_code is not None and status_code != 200:
                logger.warning(
                    "APIMart balance fetch transient failure: fingerprint=%s credentials=%s status=%s",
                    fingerprint_prefix,
                    len(group.credential_ids),
                    status_code,
                )
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)

            try:
                balance_cents = calculate_apimart_balance_cents(payload)
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                logger.warning(
                    "APIMart balance response invalid: fingerprint=%s credentials=%s error_type=%s",
                    fingerprint_prefix,
                    len(group.credential_ids),
                    type(exc).__name__,
                )
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)

            written = await self._write_redis_snapshot(
                group.fingerprint,
                ProviderBalanceSnapshot(
                    balance_cents=balance_cents,
                    synced_at=synced_at,
                    status="ok",
                ),
            )
            if not written:
                return _KeySyncResult(group.fingerprint, "failed", group.credential_ids)
            logger.info(
                "APIMart balance synced: fingerprint=%s credentials=%s",
                fingerprint_prefix,
                len(group.credential_ids),
            )
            return _KeySyncResult(group.fingerprint, "synced", group.credential_ids)

    async def _mark_credentials_invalid(self, credential_ids: list[int]) -> None:
        async with self._session_factory() as db:
            await UserApimartCredentialRepository(db).mark_credentials_invalid(credential_ids)

    async def _redis_is_available(self) -> bool:
        coordinator = get_redis_coordinator()
        health = getattr(coordinator, "health", None)
        if not callable(health):
            return True
        try:
            payload = await health()
        except Exception:
            return False
        return bool(payload.get("enabled", True)) and not bool(payload.get("degraded", False))

    async def _read_redis_snapshot(self, fingerprint: str) -> ProviderBalanceSnapshot | None:
        try:
            if not await self._redis_is_available():
                return None
            payload = await get_redis_coordinator().get_snapshot(
                _redis_snapshot_key(fingerprint)
            )
            if not isinstance(payload, dict) or payload.get("provider") != "apimart":
                return None
            synced_at = datetime.fromisoformat(str(payload["synced_at"]))
            if synced_at.tzinfo is None:
                synced_at = synced_at.replace(tzinfo=UTC)
            return ProviderBalanceSnapshot(
                balance_cents=max(int(payload["balance_cents"]), 0),
                synced_at=synced_at,
                status=str(payload.get("status") or "ok"),
            )
        except Exception:
            return None

    async def _write_redis_snapshot(
        self,
        fingerprint: str,
        snapshot: ProviderBalanceSnapshot,
    ) -> bool:
        try:
            if not await self._redis_is_available():
                return False
            await get_redis_coordinator().set_snapshot(
                _redis_snapshot_key(fingerprint),
                {
                    "balance_cents": int(snapshot.balance_cents),
                    "status": snapshot.status,
                    "synced_at": snapshot.synced_at.isoformat(),
                    "provider": "apimart",
                },
                ttl_seconds=max(
                    int(settings.PROVIDER_BALANCE_SYNC_SNAPSHOT_TTL_SECONDS),
                    1,
                ),
            )
            return True
        except Exception:
            return False

    async def _write_cycle_status(self) -> None:
        try:
            if not await self._redis_is_available():
                return
            await get_redis_coordinator().set_snapshot(
                _redis_cycle_status_key(),
                dict(self._cycle_status),
                ttl_seconds=max(
                    float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS) * 3,
                    30.0,
                ),
            )
        except Exception:
            return


provider_balance_sync_service = ProviderBalanceSyncService()


class ProviderBalanceSyncWorker:
    def __init__(
        self,
        *,
        service: ProviderBalanceSyncService | None = None,
    ) -> None:
        self.service = service or provider_balance_sync_service
        self._redis_leader_owner: str | None = None
        self._leader_lease_lost = False
        self._task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._shutdown_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._start_and_run_loop(),
            name="provider-balance-sync",
        )

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            finally:
                self._task = None
        if self._redis_leader_owner is not None:
            await self.service.set_worker_running(False)
        self._release_leader_lock()

    async def run_once(self) -> bool:
        acquired_here = self._redis_leader_owner is None
        if acquired_here and not await self._try_acquire_leader_lock_async():
            return False
        try:
            return await self.service.sync_once()
        finally:
            if acquired_here:
                self._release_leader_lock()

    async def _run_loop(self) -> None:
        interval = max(float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS), 0.1)
        owner_task = asyncio.current_task()
        self._leader_lease_lost = False
        heartbeat = asyncio.create_task(
            self._renew_leader_lease_loop(owner_task),
            name="provider-balance-sync-leader-heartbeat",
        )
        try:
            while not self._shutdown_event.is_set():
                try:
                    await self.service.sync_once()
                except Exception:
                    logger.exception("APIMart balance sync tick failed")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            if self._leader_lease_lost:
                logger.info("Stopping APIMart balance sync worker after leader lease loss")
                return
            raise
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _renew_leader_lease_loop(
        self,
        owner_task: asyncio.Task | None,
    ) -> None:
        renew_interval = min(
            max(float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS) / 3, 1.0),
            60.0,
        )
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=renew_interval,
                )
                return
            except TimeoutError:
                pass
            if await self._renew_redis_leader_lock_async():
                continue
            self._leader_lease_lost = True
            if owner_task is not None:
                owner_task.cancel()
            return

    async def _start_and_run_loop(self) -> None:
        interval = max(float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS), 0.1)
        while not self._shutdown_event.is_set():
            if not await self._try_acquire_leader_lock_async():
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue
                continue
            logger.info("Started APIMart balance sync worker")
            try:
                await self._run_loop()
            finally:
                await self.service.set_worker_running(False)
                self._release_leader_lock()
            if not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue

    async def _try_acquire_leader_lock_async(self) -> bool:
        return await self._try_acquire_redis_leader_lock_async()

    def _release_leader_lock(self) -> None:
        self._release_redis_leader_lock()

    async def _try_acquire_redis_leader_lock_async(self) -> bool:
        owner = f"provider-balance-sync:{os.getpid()}"
        try:
            result = await get_redis_coordinator().try_acquire_lease(
                _redis_leader_key(),
                owner=owner,
                ttl_seconds=max(
                    float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS) * 2,
                    5.0,
                ),
            )
        except Exception:
            return False
        if result.get("reason") == "redis_disabled" or result.get("degraded"):
            return False
        if result.get("acquired"):
            self._redis_leader_owner = owner
            return True
        return False

    async def _renew_redis_leader_lock_async(self) -> bool:
        owner = self._redis_leader_owner
        if not owner:
            return True
        try:
            result = await get_redis_coordinator().renew_lease(
                _redis_leader_key(),
                owner=owner,
                ttl_seconds=max(
                    float(settings.PROVIDER_BALANCE_SYNC_INTERVAL_SECONDS) * 2,
                    5.0,
                ),
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
                asyncio.run(
                    get_redis_coordinator().release_lease(
                        _redis_leader_key(), owner=owner
                    )
                )
            except Exception:
                return
            return
        try:
            asyncio.create_task(
                get_redis_coordinator().release_lease(
                    _redis_leader_key(), owner=owner
                )
            )
        except Exception:
            return


provider_balance_sync_worker = ProviderBalanceSyncWorker()
