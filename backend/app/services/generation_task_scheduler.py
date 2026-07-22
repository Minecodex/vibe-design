from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_coordination import get_redis_coordinator
from app.models.generation import GenerationTask
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.realtime_bus import RealtimeBus, RealtimeScope, wait_realtime_wakeup, wakeup_realtime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationTaskClaim:
    task: GenerationTask
    claim_token: str


class GenerationTaskScheduler:
    def __init__(self, db: AsyncSession, *, worker_id: str) -> None:
        self.db = db
        self.worker_id = str(worker_id or "generation-scheduler-worker")
        self.repo = GenerationTaskRepository(db)

    async def enqueue(
        self,
        task_id: int,
        *,
        next_run_at: datetime | None = None,
        workflow_stage: str | None = None,
    ) -> GenerationTask | None:
        task = await self.repo.get(int(task_id))
        if task is None or task.status in {"completed", "failed"}:
            return task
        payload: dict[str, Any] = {
            "scheduler_next_run_at": next_run_at or datetime.now(UTC),
        }
        if workflow_stage is not None:
            payload["workflow_stage"] = str(workflow_stage)
        updated = await self.repo.update(task, payload)
        await self.wake()
        return updated

    async def wake(self) -> dict[str, Any]:
        return await wakeup_realtime(
            "generation.scheduler.wakeup",
            scope=RealtimeScope(),
            reason="task_enqueued",
            worker="generation-scheduler",
            bus=RealtimeBus(get_redis_coordinator()),
        )

    async def claim_due_tasks(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 60,
    ) -> list[GenerationTaskClaim]:
        now = datetime.now(UTC)
        due_task_ids = await self.repo.list_due_scheduler_task_ids(now=now, limit=limit)
        claims: list[GenerationTaskClaim] = []
        for task_id in due_task_ids:
            claim_token = uuid4().hex
            claimed = await self.repo.claim_scheduler_task(
                task_id=task_id,
                now=now,
                lease_expires_at=now + timedelta(seconds=max(1, int(lease_seconds or 60))),
                claim_token=claim_token,
            )
            if claimed is not None:
                claims.append(GenerationTaskClaim(task=claimed, claim_token=claim_token))
        return claims

    async def renew_claim(self, task_id: int, *, claim_token: str, lease_seconds: int = 60) -> GenerationTask | None:
        now = datetime.now(UTC)
        return await self.repo.renew_scheduler_task_claim(
            task_id=task_id,
            now=now,
            lease_expires_at=now + timedelta(seconds=max(1, int(lease_seconds or 60))),
            claim_token=claim_token,
        )

    async def release_claim(self, task_id: int, *, claim_token: str) -> None:
        await self.repo.release_scheduler_task_claim(task_id=task_id, claim_token=claim_token)

    async def recover_incomplete_tasks(self) -> list[GenerationTask]:
        return await self.repo.get_incomplete_tasks()

    async def complete(
        self,
        task_id: int,
        *,
        user_id: int,
        claim_token: str,
        data: dict[str, Any] | None = None,
    ) -> GenerationTask | None:
        return await self._terminalize(
            task_id,
            user_id=user_id,
            claim_token=claim_token,
            status="completed",
            data=data or {},
        )

    async def fail(
        self,
        task_id: int,
        *,
        user_id: int,
        claim_token: str,
        error_message: str,
        error_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> GenerationTask | None:
        payload = {"error_message": error_message, "last_error_type": error_type or "GenerationTaskError", **(data or {})}
        return await self._terminalize(
            task_id,
            user_id=user_id,
            claim_token=claim_token,
            status="failed",
            data=payload,
        )

    async def _terminalize(
        self,
        task_id: int,
        *,
        user_id: int,
        claim_token: str,
        status: str,
        data: dict[str, Any],
    ) -> GenerationTask | None:
        existing = await self.repo.get_by_id_and_user(task_id, user_id)
        if existing is None:
            return None
        if existing.status in {"completed", "failed"}:
            return existing
        payload = {
            **data,
            "status": status,
            "terminalized_at": datetime.now(UTC),
            "scheduler_next_run_at": None,
            "scheduler_claim_token": None,
            "scheduler_claimed_at": None,
            "scheduler_lease_expires_at": None,
        }
        return await self.repo.update_for_scheduler_claim(
            task_id=task_id,
            user_id=user_id,
            claim_token=claim_token,
            data=payload,
        )


def _scheduler_wakeup_key() -> str:
    return RealtimeBus(get_redis_coordinator()).wakeup_key(
        name="generation.scheduler.wakeup",
        scope=RealtimeScope(),
    )


async def wait_generation_scheduler_wakeup(*, timeout_seconds: float) -> dict[str, Any]:
    return await wait_realtime_wakeup(
        "generation.scheduler.wakeup",
        scope=RealtimeScope(),
        timeout_seconds=max(float(timeout_seconds), 0.0),
        bus=RealtimeBus(get_redis_coordinator()),
    )


def wake_generation_scheduler_sync() -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(
                wakeup_realtime(
                    "generation.scheduler.wakeup",
                    scope=RealtimeScope(),
                    reason="task_enqueued",
                    worker="generation-scheduler",
                    bus=RealtimeBus(get_redis_coordinator()),
                )
            )
        except Exception:
            logger.info("Generation scheduler Redis wakeup failed", exc_info=True)
        return None

    task = loop.create_task(
        wakeup_realtime(
            "generation.scheduler.wakeup",
            scope=RealtimeScope(),
            reason="task_enqueued",
            worker="generation-scheduler",
            bus=RealtimeBus(get_redis_coordinator()),
        )
    )

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Generation scheduler Redis wakeup failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task
