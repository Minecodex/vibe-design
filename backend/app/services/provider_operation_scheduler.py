from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.config import (
    PROVIDER_OPERATION_GENERATION_QUERY_POLL_SECONDS,
    PROVIDER_OPERATION_RETRY_DELAY_SECONDS,
    PROVIDER_OPERATION_RETRYABLE_MAX_ATTEMPTS,
    PROVIDER_OPERATION_SCHEDULER_IDLE_WAIT_SECONDS,
    TASK_POLL_CLAIM_LEASE_SECONDS,
    settings,
)
from app.core.datetime_utils import normalize_app_datetime
from app.db.session import AsyncSessionLocal
from app.models.provider_operation import ProviderOperation
from app.repositories.generation_repository import GenerationTaskRepository
from app.repositories.provider_operation_repository import ProviderOperationRepository
from app.services.billing_service import BillingService
from app.services.generation_terminalization import (
    GenerationTerminalizationService,
    build_generation_terminal_update,
)
from app.services.provider_operation_service import wait_provider_operation_wakeup
from app.services.provider_request_gate import ProviderRequestGate
from app.services.provider_request_policy import classify_provider_error

logger = logging.getLogger(__name__)


class ProviderOperationScheduler:
    def __init__(self) -> None:
        self._scheduler_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._scheduler_task is not None and not self._scheduler_task.done()

    def start(self) -> None:
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._shutdown_event = asyncio.Event()
        self._scheduler_task = asyncio.create_task(self._run_loop(), name="provider-operation-scheduler")

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._scheduler_task is None:
            return
        try:
            await asyncio.wait_for(self._scheduler_task, timeout=10)
        except TimeoutError:
            self._scheduler_task.cancel()
            await asyncio.gather(self._scheduler_task, return_exceptions=True)
        finally:
            self._scheduler_task = None

    async def run_once(self, *, limit: int = 10) -> int:
        claim_token = uuid4().hex
        async with AsyncSessionLocal() as db:
            repo = ProviderOperationRepository(db)
            claims = await repo.claim_due(
                now=datetime.now(UTC),
                worker_id=self._worker_id(),
                claim_token=claim_token,
                lease_seconds=self._lease_seconds(),
                limit=limit,
            )

        for operation in claims:
            await self._execute_claim(operation.id, claim_token=claim_token)
        return len(claims)

    async def _run_loop(self) -> None:
        interval = _provider_operation_idle_wait_seconds()
        while not self._shutdown_event.is_set():
            try:
                processed = await self.run_once()
                if processed > 0:
                    continue
                await wait_provider_operation_wakeup(timeout_seconds=interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Provider operation scheduler tick failed")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue

    async def _execute_claim(self, operation_id: int, *, claim_token: str) -> None:
        async with AsyncSessionLocal() as db:
            repo = ProviderOperationRepository(db)
            operation = await repo.get(operation_id)
            if (
                operation is None
                or operation.status != "running"
                or operation.lease_token != claim_token
            ):
                return
            renewed = await repo.renew_claim(
                operation,
                lease_seconds=self._lease_seconds(),
            )
            if renewed is None:
                return
            executor = ProviderOperationExecutor(db)
            await executor.execute(renewed)

    @staticmethod
    def _lease_seconds() -> int:
        return max(int(TASK_POLL_CLAIM_LEASE_SECONDS or 0), 5)

    @staticmethod
    def _worker_id() -> str:
        return f"provider-operation:{socket.gethostname()}:{os.getpid()}"


def _provider_operation_idle_wait_seconds() -> float:
    return max(float(PROVIDER_OPERATION_SCHEDULER_IDLE_WAIT_SECONDS), 0.1)


def _provider_operation_retry_delay_seconds() -> float:
    return max(float(PROVIDER_OPERATION_RETRY_DELAY_SECONDS), 0.1)


def _provider_operation_generation_query_poll_seconds() -> float:
    return max(float(PROVIDER_OPERATION_GENERATION_QUERY_POLL_SECONDS), 0.1)


def _provider_operation_retryable_max_attempts() -> int:
    return max(int(PROVIDER_OPERATION_RETRYABLE_MAX_ATTEMPTS or 0), 1)


def _provider_operation_retryable_attempts_exhausted(operation: ProviderOperation) -> bool:
    return int(getattr(operation, "attempt_count", 0) or 0) >= _provider_operation_retryable_max_attempts()


def _generation_task_timeout_seconds(task: Any) -> int:
    task_type = str(getattr(task, "task_type", "") or "").strip()
    if task_type in {"text2video", "image2video"}:
        return int(settings.TASK_TIMEOUT_VIDEO_SECONDS)
    return int(settings.TASK_TIMEOUT_IMAGE_SECONDS)


def _generation_task_timed_out(task: Any, *, now: datetime | None = None) -> bool:
    created_at = normalize_app_datetime(getattr(task, "created_at", None))
    if created_at is None:
        return False
    current = now or datetime.now(UTC)
    timeout_seconds = max(_generation_task_timeout_seconds(task), 1)
    return (current - created_at).total_seconds() > timeout_seconds


def _provider_operation_terminal_error_type(exc: Exception) -> str:
    classified = classify_provider_error(exc)
    if classified.startswith("retryable_"):
        return classified
    return type(exc).__name__


def _provider_operation_terminal_error_message(
    operation: ProviderOperation,
    exc: Exception,
    *,
    error_type: str,
) -> str:
    detail = str(exc).strip() or type(exc).__name__
    if error_type.startswith("retryable_"):
        attempts = int(getattr(operation, "attempt_count", 0) or 0)
        max_attempts = _provider_operation_retryable_max_attempts()
        return (
            "供应商请求连续失败，已停止重试："
            f"provider={operation.provider_code} operation={operation.operation} "
            f"attempts={attempts}/{max_attempts} error={detail}"
        )
    return detail


class ProviderOperationExecutor:
    def __init__(self, db) -> None:
        self.db = db
        self.operation_repo = ProviderOperationRepository(db)
        self.task_repo = GenerationTaskRepository(db)
        self.gate = ProviderRequestGate(namespace="provider-operations")

    async def execute(self, operation: ProviderOperation) -> None:
        task = await self.task_repo.get_by_id_and_user(operation.generation_task_id, operation.user_id)
        if task is None or task.status in {"completed", "failed"}:
            await self.operation_repo.mark_failed(
                operation,
                error_type="generation_task_not_active",
                error_message="generation task is missing or terminal",
            )
            return

        if operation.operation == "generation_query" and await self._terminalize_generation_query_if_timed_out(
            operation,
            task,
        ):
            return

        decision = await self.gate.allow(
            provider=operation.provider_code,
            operation=operation.operation,
            priority=operation.priority,
        )
        if not decision.allowed:
            await self.operation_repo.defer_rate_limited(
                operation,
                retry_after_seconds=decision.retry_after_seconds,
            )
            return

        try:
            await self._run_with_lease_renewal(
                operation,
                lambda: self._execute_operation(operation, task),
            )
            return
        except Exception as exc:
            if await self._requeue_retryable_error(operation, exc, task=task):
                return
            error_type = _provider_operation_terminal_error_type(exc)
            error_message = _provider_operation_terminal_error_message(
                operation,
                exc,
                error_type=error_type,
            )
            logger.exception(
                "Provider operation failed: id=%s operation=%s error_type=%s",
                operation.id,
                operation.operation,
                error_type,
            )
            failed_operation = await self.operation_repo.mark_failed(
                operation,
                error_type=error_type,
                error_message=error_message,
            )
            if failed_operation.status != "failed":
                logger.info(
                    "Skipped generation task terminalization because provider operation lease was lost: id=%s",
                    operation.id,
                )
                return
            refreshed = await self.task_repo.get_by_id_and_user(task.id, task.user_id)
            if refreshed is not None and refreshed.status not in {"completed", "failed"}:
                failed_task = await self.task_repo.update(
                    refreshed,
                    build_generation_terminal_update({
                        "status": "failed",
                        "error_message": error_message,
                        "last_error_type": error_type,
                    }),
                )
                finalized = await GenerationTerminalizationService(
                    self.db,
                    billing_service_factory=BillingService,
                ).finalize_terminal_task(failed_task, user_id=failed_task.user_id)
                if finalized:
                    await self.task_repo.mark_terminal_side_effects_finalized(failed_task.id)

    async def _terminalize_generation_query_if_timed_out(self, operation: ProviderOperation, task: Any) -> bool:
        if operation.operation != "generation_query":
            return False
        if not _generation_task_timed_out(task):
            return False

        error_type = "generation_task_timeout"
        error_message = "任务超时"
        logger.warning(
            "Provider generation query timed out: task_id=%s provider=%s task_type=%s",
            getattr(task, "id", None),
            operation.provider_code,
            getattr(task, "task_type", None),
        )
        failed_operation = await self.operation_repo.mark_failed(
            operation,
            error_type=error_type,
            error_message=error_message,
        )
        if failed_operation.status != "failed":
            logger.info(
                "Skipped generation task timeout terminalization because provider operation lease was lost: id=%s",
                operation.id,
            )
            return True

        refreshed = await self.task_repo.get_by_id_and_user(task.id, task.user_id)
        if refreshed is not None and refreshed.status not in {"completed", "failed"}:
            failed_task = await self.task_repo.update(
                refreshed,
                build_generation_terminal_update({
                    "status": "failed",
                    "error_message": error_message,
                    "last_error_type": error_type,
                }),
            )
            finalized = await GenerationTerminalizationService(
                self.db,
                billing_service_factory=BillingService,
            ).finalize_terminal_task(failed_task, user_id=failed_task.user_id)
            if finalized:
                await self.task_repo.mark_terminal_side_effects_finalized(failed_task.id)
        return True

    async def _requeue_retryable_error(
        self,
        operation: ProviderOperation,
        exc: Exception,
        *,
        task: Any | None = None,
    ) -> bool:
        error_type = classify_provider_error(exc)
        if not error_type.startswith("retryable_"):
            return False

        if operation.operation == "generation_query":
            if task is not None and await self._terminalize_generation_query_if_timed_out(operation, task):
                return True
        elif _provider_operation_retryable_attempts_exhausted(operation):
            return False

        logger.info(
            "Provider operation retryable error: id=%s operation=%s error_type=%s",
            operation.id,
            operation.operation,
            error_type,
        )
        delay_seconds = (
            _provider_operation_generation_query_poll_seconds()
            if operation.operation == "generation_query"
            else _provider_operation_retry_delay_seconds()
        )
        await self.operation_repo.requeue(
            operation,
            due_at=datetime.now(UTC) + timedelta(seconds=delay_seconds),
            error_type=error_type,
            error_message=str(exc),
        )
        return True

    async def _execute_operation(self, operation: ProviderOperation, task) -> None:
        if operation.operation == "generation_submit":
            await self._execute_generation_submit(operation, task)
            return
        if operation.operation == "generation_query":
            await self._execute_generation_query(operation, task)
            return
        if operation.operation == "result_download":
            await self._execute_result_download(operation, task)
            return
        await self.operation_repo.mark_failed(
            operation,
            error_type="unsupported_provider_operation",
            error_message=operation.operation,
        )

    async def _run_with_lease_renewal(self, operation: ProviderOperation, action) -> None:
        if not getattr(operation, "lease_token", None):
            await action()
            return
        stop_event = asyncio.Event()
        renew_task = asyncio.create_task(
            self._renew_claim_until_stopped(operation, stop_event),
            name=f"provider-operation-renew-{operation.id}",
        )
        try:
            await action()
        finally:
            stop_event.set()
            await asyncio.gather(renew_task, return_exceptions=True)

    async def _renew_claim_until_stopped(self, operation: ProviderOperation, stop_event: asyncio.Event) -> None:
        lease_seconds = max(int(TASK_POLL_CLAIM_LEASE_SECONDS or 0), 5)
        interval = max(min(float(lease_seconds) / 3.0, 5.0), 0.5)
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            try:
                async with AsyncSessionLocal() as db:
                    renewed = await ProviderOperationRepository(db).renew_claim(
                        operation,
                        lease_seconds=lease_seconds,
                    )
                if renewed is None:
                    logger.info("Provider operation lease renewal skipped: id=%s", operation.id)
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.info("Provider operation lease renewal failed: id=%s", operation.id, exc_info=True)

    async def _execute_generation_submit(self, operation: ProviderOperation, task) -> None:
        from app.services.generation_service import GenerationService

        generation_service = GenerationService(self.db)
        task_kind = str((operation.payload or {}).get("task_kind") or "")
        if task_kind == "video" or task.task_type in {"text2video", "image2video"}:
            await generation_service.complete_builtin_video_submit_operation(task, operation)
        else:
            await generation_service.complete_builtin_image_submit_operation(task, operation)

    async def _execute_generation_query(self, operation: ProviderOperation, task) -> None:
        from app.services.generation_service import GenerationService

        if await self._terminalize_generation_query_if_timed_out(operation, task):
            return

        generation_service = GenerationService(self.db)
        result = await generation_service.query_builtin_task_for_operation(task)
        if result is None:
            if await self._terminalize_generation_query_if_timed_out(operation, task):
                return
            await self.operation_repo.requeue(
                operation,
                due_at=datetime.now(UTC) + timedelta(seconds=_provider_operation_generation_query_poll_seconds()),
            )
            return
        if result.get("status") == "completed" and result.get("pending_result_download"):
            await self.operation_repo.mark_succeeded(operation, result_payload=result)
            return
        if result.get("status") in {"completed", "failed"}:
            await self.operation_repo.mark_succeeded(operation, result_payload=result)
            return
        if await self._terminalize_generation_query_if_timed_out(operation, task):
            return
        await self.operation_repo.requeue(
            operation,
            due_at=datetime.now(UTC) + timedelta(seconds=_provider_operation_generation_query_poll_seconds()),
        )

    async def _execute_result_download(self, operation: ProviderOperation, task) -> None:
        from app.services.generation_service import GenerationService

        generation_service = GenerationService(self.db)
        await generation_service.complete_result_download_operation(task, operation)


provider_operation_scheduler = ProviderOperationScheduler()
