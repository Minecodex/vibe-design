import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apimart_key_fingerprint import get_apimart_key_fingerprint
from app.models.user import User
from app.models.user_apimart_credential import UserApimartCredential
from app.services.provider_balance_sync import (
    UNLIMITED_PROVIDER_BALANCE_CENTS,
    ProviderBalanceSyncService,
    ProviderBalanceSyncWorker,
    _redis_snapshot_key,
    calculate_apimart_balance_cents,
)


class _SessionContext:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Keys:
    def build(self, *, domain, purpose, resource_parts=()):
        return ":".join([domain, purpose, *resource_parts])


class _Coordinator:
    keys = _Keys()

    def __init__(self):
        self.snapshots: dict[str, dict] = {}
        self.ttls: dict[str, float] = {}
        self.rate_limit_buckets: list[str] = []
        self.lease_acquired = True

    async def health(self):
        return {"enabled": True, "degraded": False}

    async def get_snapshot(self, key):
        return self.snapshots.get(key)

    async def set_snapshot(self, key, value, *, ttl_seconds):
        self.snapshots[key] = dict(value)
        self.ttls[key] = ttl_seconds

    async def rate_limit(self, bucket, *, limit, window_seconds):
        self.rate_limit_buckets.append(bucket)
        return {"allowed": True, "retry_after_seconds": 0}

    async def try_acquire_lease(self, key, *, owner, ttl_seconds):
        return {"acquired": self.lease_acquired}

    async def renew_lease(self, key, *, owner, ttl_seconds):
        return {"renewed": True}

    async def release_lease(self, key, *, owner):
        return True


class _ClientFactory:
    def __init__(self, responses):
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, api_key):
        factory = self

        class Client:
            async def get_balance(self):
                factory.calls.append(api_key)
                response = factory.responses[api_key]
                if isinstance(response, BaseException):
                    raise response
                return dict(response)

        return Client()


async def _create_user(db: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"balance-{suffix}@example.com",
        username=f"balance-{suffix}",
        hashed_password="x",
    )
    db.add(user)
    await db.flush()
    return user


async def _add_credential(
    db: AsyncSession,
    user: User,
    api_key: str,
    *,
    status: str = "active",
    is_current: bool = True,
) -> UserApimartCredential:
    credential = UserApimartCredential(
        user_id=user.id,
        api_key=api_key,
        status=status,
        is_current=is_current,
        created_by_user_id=user.id,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


@pytest.fixture
def coordinator(monkeypatch):
    value = _Coordinator()
    monkeypatch.setattr(
        "app.services.provider_balance_sync.get_redis_coordinator",
        lambda: value,
    )
    monkeypatch.setattr(
        "app.services.provider_request_policy.get_redis_coordinator",
        lambda: value,
    )
    monkeypatch.setattr(
        "app.services.provider_balance_sync.settings.PROVIDER_BALANCE_SYNC_SNAPSHOT_TTL_SECONDS",
        900,
    )
    return value


@pytest.fixture(autouse=True)
async def clear_apimart_credentials(db_session: AsyncSession):
    await db_session.execute(delete(UserApimartCredential))
    await db_session.commit()


def test_apimart_balance_conversion_and_fingerprint_are_stable(monkeypatch):
    monkeypatch.setattr("app.core.apimart_key_fingerprint.settings.SECRET_KEY", "test-secret")
    assert calculate_apimart_balance_cents({"remain_balance": 12.5}) == 12500
    assert (
        calculate_apimart_balance_cents(
            {"remain_balance": -1, "unlimited_quota": True}
        )
        == UNLIMITED_PROVIDER_BALANCE_CENTS
    )
    first = get_apimart_key_fingerprint("sk-test-one")
    assert first == get_apimart_key_fingerprint("sk-test-one")
    assert first != get_apimart_key_fingerprint("sk-test-two")
    assert "sk-test-one" not in first


@pytest.mark.asyncio
async def test_distinct_keys_sync_separate_snapshots_and_shared_key_fetches_once(
    db_session: AsyncSession,
    coordinator,
):
    first_user = await _create_user(db_session, "distinct-1")
    second_user = await _create_user(db_session, "distinct-2")
    third_user = await _create_user(db_session, "shared")
    await _add_credential(db_session, first_user, "sk-distinct-a")
    await _add_credential(db_session, second_user, "sk-distinct-b")
    await _add_credential(db_session, third_user, "sk-distinct-a")
    clients = _ClientFactory(
        {
            "sk-distinct-a": {"success": True, "remain_balance": 2},
            "sk-distinct-b": {"success": True, "remain_balance": 7},
        }
    )
    service = ProviderBalanceSyncService(
        session_factory=lambda: _SessionContext(db_session),
        client_factory=clients,
    )

    assert await service.sync_once(now=datetime(2026, 7, 21, tzinfo=UTC)) is True

    assert sorted(clients.calls) == ["sk-distinct-a", "sk-distinct-b"]
    assert await service.get_balance_cents("sk-distinct-a") == 2000
    assert await service.get_balance_cents("sk-distinct-b") == 7000
    balance_snapshots = {
        key: value
        for key, value in coordinator.snapshots.items()
        if ":apimart:v1:cycle-status" not in key
    }
    assert len(balance_snapshots) == 2
    assert {coordinator.ttls[key] for key in balance_snapshots} == {900}
    serialized = repr(coordinator.snapshots) + repr(list(coordinator.snapshots))
    assert "sk-distinct-a" not in serialized
    assert "sk-distinct-b" not in serialized
    assert len(set(coordinator.rate_limit_buckets)) == 2


@pytest.mark.asyncio
async def test_sync_paginates_and_skips_non_active_credentials(
    db_session: AsyncSession,
    coordinator,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.provider_balance_sync.settings.PROVIDER_BALANCE_SYNC_BATCH_SIZE",
        100,
    )
    for index in range(105):
        user = await _create_user(db_session, f"page-{index}")
        await _add_credential(db_session, user, "sk-one-shared-page")
    for index, status in enumerate(("invalid", "replaced", "revoked")):
        user = await _create_user(db_session, f"skip-{index}")
        await _add_credential(
            db_session,
            user,
            f"sk-skip-{index}",
            status=status,
            is_current=status == "invalid",
        )
    clients = _ClientFactory(
        {"sk-one-shared-page": {"success": True, "remain_balance": 1}}
    )
    service = ProviderBalanceSyncService(
        session_factory=lambda: _SessionContext(db_session),
        client_factory=clients,
    )

    await service.sync_once()
    status = await service.get_sync_status()

    assert clients.calls == ["sk-one-shared-page"]
    assert status["credentials_scanned"] == 105
    assert status["unique_keys"] == 1
    assert status["synced"] == 1


@pytest.mark.asyncio
async def test_auth_failure_invalidates_every_current_credential_for_shared_key(
    db_session: AsyncSession,
    coordinator,
):
    first = await _create_user(db_session, "invalid-1")
    second = await _create_user(db_session, "invalid-2")
    first_credential = await _add_credential(db_session, first, "sk-invalid-shared")
    second_credential = await _add_credential(db_session, second, "sk-invalid-shared")
    clients = _ClientFactory(
        {"sk-invalid-shared": {"_status_code": 401, "message": "unauthorized"}}
    )
    service = ProviderBalanceSyncService(
        session_factory=lambda: _SessionContext(db_session),
        client_factory=clients,
    )

    await service.sync_once()
    await db_session.refresh(first_credential)
    await db_session.refresh(second_credential)

    assert first_credential.status == "invalid"
    assert second_credential.status == "invalid"
    assert await service.get_balance_cents("sk-invalid-shared") == 0
    status = await service.get_sync_status()
    assert status["invalid"] == 1


@pytest.mark.asyncio
async def test_transient_failure_does_not_overwrite_successful_snapshot(
    db_session: AsyncSession,
    coordinator,
):
    user = await _create_user(db_session, "transient")
    await _add_credential(db_session, user, "sk-transient")
    clients = _ClientFactory(
        {"sk-transient": {"success": True, "remain_balance": 9}}
    )
    service = ProviderBalanceSyncService(
        session_factory=lambda: _SessionContext(db_session),
        client_factory=clients,
    )
    await service.sync_once()
    clients.responses["sk-transient"] = {"_status_code": 503}

    await service.sync_once()

    assert await service.get_balance_cents("sk-transient") == 9000
    assert (await service.get_sync_status())["failed"] == 1


@pytest.mark.asyncio
async def test_missing_or_unavailable_redis_returns_zero(coordinator, monkeypatch):
    service = ProviderBalanceSyncService()
    assert await service.get_balance_cents("sk-missing") == 0

    async def degraded_health():
        return {"enabled": True, "degraded": True}

    coordinator.health = degraded_health
    fingerprint = get_apimart_key_fingerprint("sk-unavailable")
    coordinator.snapshots[_redis_snapshot_key(fingerprint)] = {
        "balance_cents": 9999,
        "status": "ok",
        "synced_at": datetime.now(UTC).isoformat(),
        "provider": "apimart",
    }
    assert await service.get_balance_cents("sk-unavailable") == 0


@pytest.mark.asyncio
async def test_worker_leader_lock_allows_only_the_leader(coordinator):
    calls = 0

    class Service:
        async def sync_once(self):
            nonlocal calls
            calls += 1
            return True

    leader = ProviderBalanceSyncWorker(service=Service())
    assert await leader.run_once() is True
    await asyncio.sleep(0)
    assert calls == 1

    coordinator.lease_acquired = False
    follower = ProviderBalanceSyncWorker(service=Service())
    assert await follower.run_once() is False
    assert calls == 1
