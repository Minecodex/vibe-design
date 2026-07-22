from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.models.provider_operation import ProviderOperation
from app.repositories.base_repository import BaseRepository


ACTIVE_PROVIDER_OPERATION_STATUSES = {"queued", "running", "rate_limited"}
CLAIMABLE_PROVIDER_OPERATION_STATUSES = {"queued", "running", "rate_limited"}


class ProviderOperationRepository(BaseRepository[ProviderOperation]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(ProviderOperation, db)

    async def enqueue_once(
        self,
        *,
        generation_task_id: int,
        user_id: int,
        provider_code: str,
        operation: str,
        operation_key: str = "default",
        priority: str = "background",
        due_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ProviderOperation:
        existing = await self.get_by_task_operation_key(
            generation_task_id=generation_task_id,
            operation=operation,
            operation_key=operation_key,
        )
        if existing is not None:
            if existing.status in ACTIVE_PROVIDER_OPERATION_STATUSES:
                return existing
            return await self.update(
                existing,
                {
                    "status": "queued",
                    "provider_code": str(provider_code),
                    "priority": str(priority or "background"),
                    "due_at": due_at or datetime.now(UTC),
                    "payload": sanitize_persistent_payload(payload or {}),
                    "result_payload": None,
                    "retry_after_seconds": None,
                    "rate_limited_at": None,
                    "last_error_type": None,
                    "last_error_message": None,
                    "lease_token": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                },
            )

        operation_obj = ProviderOperation(
            generation_task_id=int(generation_task_id),
            user_id=int(user_id),
            provider_code=str(provider_code),
            operation=str(operation),
            operation_key=str(operation_key or "default"),
            priority=str(priority or "background"),
            status="queued",
            due_at=due_at or datetime.now(UTC),
            payload=sanitize_persistent_payload(payload or {}),
        )
        try:
            return await self.create(operation_obj)
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_by_task_operation_key(
                generation_task_id=generation_task_id,
                operation=operation,
                operation_key=operation_key,
            )
            if existing is None:
                raise
            return existing

    async def get_by_task_operation_key(
        self,
        *,
        generation_task_id: int,
        operation: str,
        operation_key: str = "default",
    ) -> ProviderOperation | None:
        result = await self.db.execute(
            select(ProviderOperation).where(
                and_(
                    ProviderOperation.generation_task_id == int(generation_task_id),
                    ProviderOperation.operation == str(operation),
                    ProviderOperation.operation_key == str(operation_key or "default"),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_due_operation_ids(self, *, now: datetime, limit: int = 10) -> list[int]:
        normalized_limit = max(1, int(limit or 1))
        result = await self.db.execute(
            select(ProviderOperation.id)
            .where(
                ProviderOperation.status.in_(CLAIMABLE_PROVIDER_OPERATION_STATUSES),
                or_(ProviderOperation.due_at.is_(None), ProviderOperation.due_at <= now),
                or_(
                    ProviderOperation.lease_expires_at.is_(None),
                    ProviderOperation.lease_expires_at <= now,
                ),
            )
            .order_by(
                ProviderOperation.due_at.asc(),
                ProviderOperation.created_at.asc(),
                ProviderOperation.id.asc(),
            )
            .limit(normalized_limit)
        )
        return [int(item) for item in result.scalars().all()]

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        claim_token: str,
        lease_seconds: int,
        limit: int = 10,
    ) -> list[ProviderOperation]:
        operation_ids = await self.list_due_operation_ids(now=now, limit=limit)
        claimed: list[ProviderOperation] = []
        for operation_id in operation_ids:
            result = await self.db.execute(
                update(ProviderOperation)
                .where(
                    ProviderOperation.id == int(operation_id),
                    ProviderOperation.status.in_(CLAIMABLE_PROVIDER_OPERATION_STATUSES),
                    or_(
                        ProviderOperation.lease_expires_at.is_(None),
                        ProviderOperation.lease_expires_at <= now,
                    ),
                )
                .values(
                    status="running",
                    lease_token=claim_token,
                    lease_owner=str(worker_id),
                    lease_expires_at=now + timedelta(seconds=max(int(lease_seconds or 60), 1)),
                    attempt_count=ProviderOperation.attempt_count + 1,
                )
                .execution_options(synchronize_session=False)
            )
            await self.db.commit()
            rowcount = int(result.rowcount or 0)
            if rowcount not in {1, -1}:
                continue
            refreshed = await self.get(operation_id)
            if refreshed is not None:
                await self.db.refresh(refreshed)
            if refreshed is not None and refreshed.lease_token == claim_token:
                claimed.append(refreshed)
        return claimed

    async def defer_rate_limited(
        self,
        operation: ProviderOperation,
        *,
        retry_after_seconds: float,
        now: datetime | None = None,
    ) -> ProviderOperation:
        now = now or datetime.now(UTC)
        retry_after = max(int(retry_after_seconds or 0), 1)
        return await self._update_claimed_operation(
            operation,
            {
                "status": "rate_limited",
                "due_at": now + timedelta(seconds=retry_after),
                "retry_after_seconds": retry_after,
                "rate_limited_at": now,
                "last_error_type": "provider_rate_limited",
                "last_error_message": None,
                "lease_token": None,
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )

    async def requeue(
        self,
        operation: ProviderOperation,
        *,
        due_at: datetime,
        payload: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> ProviderOperation:
        data: dict[str, Any] = {
            "status": "queued",
            "due_at": due_at,
            "retry_after_seconds": None,
            "lease_token": None,
            "lease_owner": None,
            "lease_expires_at": None,
        }
        if payload is not None:
            data["payload"] = sanitize_persistent_payload(payload)
        if error_type is not None:
            data["last_error_type"] = str(error_type or "")[:120] or None
            data["last_error_message"] = str(error_message or "")[:1000] or None
        return await self._update_claimed_operation(operation, data)

    async def mark_succeeded(
        self,
        operation: ProviderOperation,
        *,
        result_payload: dict[str, Any] | None = None,
    ) -> ProviderOperation:
        return await self._update_claimed_operation(
            operation,
            {
                "status": "succeeded",
                "result_payload": sanitize_persistent_payload(result_payload or {}),
                "lease_token": None,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error_type": None,
                "last_error_message": None,
            },
        )

    async def mark_failed(
        self,
        operation: ProviderOperation,
        *,
        error_type: str,
        error_message: str | None = None,
    ) -> ProviderOperation:
        return await self._update_claimed_operation(
            operation,
            {
                "status": "failed",
                "last_error_type": str(error_type or "provider_operation_failed")[:120],
                "last_error_message": str(error_message or "")[:1000] or None,
                "lease_token": None,
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )

    async def release_claim(self, operation: ProviderOperation) -> ProviderOperation:
        return await self.update(
            operation,
            {
                "lease_token": None,
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )

    async def renew_claim(
        self,
        operation: ProviderOperation,
        *,
        now: datetime | None = None,
        lease_seconds: int,
    ) -> ProviderOperation | None:
        lease_token = str(getattr(operation, "lease_token", "") or "")
        if not lease_token:
            return None
        now = now or datetime.now(UTC)
        result = await self.db.execute(
            update(ProviderOperation)
            .where(
                ProviderOperation.id == int(operation.id),
                ProviderOperation.lease_token == lease_token,
                ProviderOperation.status == "running",
            )
            .values(
                lease_expires_at=now + timedelta(seconds=max(int(lease_seconds or 60), 1)),
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        if int(result.rowcount or 0) not in {1, -1}:
            return None
        refreshed = await self.get(operation.id)
        if refreshed is not None:
            await self.db.refresh(refreshed)
        return refreshed

    async def _update_claimed_operation(
        self,
        operation: ProviderOperation,
        data: dict[str, Any],
    ) -> ProviderOperation:
        lease_token = str(getattr(operation, "lease_token", "") or "")
        if not lease_token:
            return await self.update(operation, data)
        result = await self.db.execute(
            update(ProviderOperation)
            .where(
                ProviderOperation.id == int(operation.id),
                ProviderOperation.lease_token == lease_token,
            )
            .values(**data)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        refreshed = await self.get(operation.id)
        if refreshed is not None:
            await self.db.refresh(refreshed)
        rowcount = int(result.rowcount or 0)
        if rowcount in {1, -1} and refreshed is not None:
            return refreshed
        return refreshed or operation
