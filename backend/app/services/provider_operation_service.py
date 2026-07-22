from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_coordination import get_redis_coordinator
from app.models.generation import GenerationTask
from app.models.provider_operation import ProviderOperation
from app.repositories.provider_operation_repository import ProviderOperationRepository

logger = logging.getLogger(__name__)


def _wakeup_key() -> str:
    coordinator = get_redis_coordinator()
    return coordinator.keys.build(
        domain="provider-operation",
        purpose="scheduler-wakeup",
        resource_parts=["global"],
    )


async def wake_provider_operation_scheduler() -> dict[str, Any]:
    return await get_redis_coordinator().wakeup(_wakeup_key())


def wake_provider_operation_scheduler_sync() -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(wake_provider_operation_scheduler())
        except Exception:
            logger.info("Provider operation scheduler Redis wakeup failed", exc_info=True)
        return None

    task = loop.create_task(wake_provider_operation_scheduler())

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Provider operation scheduler Redis wakeup failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


async def wait_provider_operation_wakeup(*, timeout_seconds: float) -> dict[str, Any]:
    return await get_redis_coordinator().wait_wakeup(
        _wakeup_key(),
        timeout_seconds=max(float(timeout_seconds), 0.0),
    )


class ProviderOperationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ProviderOperationRepository(db)

    async def enqueue_generation_submit(
        self,
        task: GenerationTask,
        *,
        task_kind: str,
        provider_code: str,
        priority: str = "foreground",
        due_at: datetime | None = None,
    ) -> ProviderOperation:
        operation = await self.repo.enqueue_once(
            generation_task_id=int(task.id),
            user_id=int(task.user_id),
            provider_code=str(provider_code),
            operation="generation_submit",
            operation_key=str(task_kind or getattr(task, "task_type", None) or "default"),
            priority=priority,
            due_at=due_at or datetime.now(UTC),
            payload={"task_kind": str(task_kind or ""), "task_type": getattr(task, "task_type", None)},
        )
        wake_provider_operation_scheduler_sync()
        return operation

    async def enqueue_generation_query(
        self,
        task: GenerationTask,
        *,
        provider_code: str,
        due_at: datetime | None = None,
    ) -> ProviderOperation:
        operation = await self.repo.enqueue_once(
            generation_task_id=int(task.id),
            user_id=int(task.user_id),
            provider_code=str(provider_code),
            operation="generation_query",
            operation_key="default",
            priority="background",
            due_at=due_at or datetime.now(UTC),
            payload={"external_task_id": getattr(task, "external_task_id", None)},
        )
        wake_provider_operation_scheduler_sync()
        return operation

    async def enqueue_result_download(
        self,
        task: GenerationTask,
        *,
        provider_code: str,
        result_urls: list[str],
        due_at: datetime | None = None,
    ) -> ProviderOperation:
        operation = await self.repo.enqueue_once(
            generation_task_id=int(task.id),
            user_id=int(task.user_id),
            provider_code=str(provider_code),
            operation="result_download",
            operation_key="default",
            priority="background",
            due_at=due_at or datetime.now(UTC),
            payload={"result_urls": list(result_urls or [])},
        )
        wake_provider_operation_scheduler_sync()
        return operation
