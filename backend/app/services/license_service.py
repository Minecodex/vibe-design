from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.license import LicenseStatus, compute_license_token_hash, verify_license_code
from app.core.license_policy import LicenseCapability, license_capability_enabled
from app.core.provider_balance_mode import is_provider_balance_sync_enabled
from app.core.redis_coordination import get_redis_coordinator
from app.models.license import LicenseRecord
from app.repositories.license_repository import LicenseRepository
from app.services.agent_harness.catalog import agent_catalog_health


class LicenseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = LicenseRepository(db)

    async def get_status(self) -> LicenseStatus:
        # The application no longer gates access through license records.
        return LicenseStatus(
            expired=False,
            expires_at=None,
            status="active",
            edition="flagship",
            builtin_provider_code="apimart",
        )

    async def activate(self, code: str) -> dict:
        normalized_code = code.strip()
        try:
            data = verify_license_code(normalized_code)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        expires_at = data["expires_at"]
        if expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="license code has expired",
            )

        token_hash = compute_license_token_hash(normalized_code)
        existing = await self.repo.get_by_token_hash(token_hash)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="license code has already been used",
            )

        record = LicenseRecord(
            token_hash=token_hash,
            license_token=normalized_code,
        )
        await self.repo.create(record)
        return {
            "expires_at": expires_at,
            "expired": False,
        }

    async def ensure_capability(self, capability: LicenseCapability) -> None:
        if settings.DEPLOY_TYPE != "private":
            return

        current_status = await self.get_status()
        if current_status.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="license is not active",
            )
        if not license_capability_enabled(current_status.edition, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="current license edition does not include this feature",
            )

    async def build_health_payload(self, *, app_name: str, app_env: str, deploy_type: str) -> dict:
        redis_health = await get_redis_coordinator().health()
        catalog_health = await agent_catalog_health()
        background_health = await _background_health_payload()
        service_status = (
            "unhealthy"
            if redis_health.get("status") == "required-unavailable"
            or catalog_health.get("status") != "ready"
            else "healthy"
        )
        current_status = await self.get_status()
        return {
            "status": service_status,
            "env": app_env,
            "app": app_name,
            "deploy_type": deploy_type,
            "license_status": current_status.status,
            "license_edition": current_status.edition,
            "license_expired": current_status.status != "active",
            "license_expires_at": current_status.expires_at.isoformat() if current_status.expires_at else None,
            "provider_balance_sync_enabled": is_provider_balance_sync_enabled(),
            "redis": redis_health,
            "agent_catalog": catalog_health,
            "background": background_health,
        }


async def _background_health_payload() -> dict:
    from app.services.agent_harness.runtime.eventing import notification_coalescer
    from app.services.agent_harness.runtime.eventing.conversation_event_subscription_pool import (
        get_conversation_event_subscription_pool,
        get_conversation_runtime_subscription_pool,
    )
    from app.services.agent_harness.runtime.eventing.conversation_stream_session import (
        active_conversation_sse_count,
    )
    from app.services.background_scheduler_owner import background_scheduler_owner
    from app.services.provider_balance_sync import provider_balance_sync_service
    from app.services.provider_operation_scheduler import provider_operation_scheduler
    from app.services.task_poller import task_poller

    provider_balance_status = await provider_balance_sync_service.get_sync_status()
    return {
        "scheduler_owner": background_scheduler_owner.status(),
        "generation_scheduler_active_polling_count": task_poller.active_count,
        "provider_operation_scheduler_running": provider_operation_scheduler.is_running,
        "provider_balance_sync_worker_running": bool(
            provider_balance_status.get("worker_running")
        ),
        "provider_balance_sync": provider_balance_status,
        "active_conversation_sse_count": active_conversation_sse_count(),
        "conversation_event_subscription_pool_active_conversation_count": (
            get_conversation_event_subscription_pool().active_conversation_count()
        ),
        "conversation_runtime_subscription_pool_active_conversation_count": (
            get_conversation_runtime_subscription_pool().active_conversation_count()
        ),
        "conversation_event_notification_coalescer": notification_coalescer.metrics_snapshot(),
    }
