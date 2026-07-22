"""Background task poller — autonomously polls external providers for generation task status."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import (
    GENERATION_SCHEDULER_IDLE_WAIT_SECONDS,
    GENERATION_TASK_ACTIVE_POLL_SECONDS,
    TASK_POLL_CLAIM_LEASE_SECONDS,
    settings,
)
from app.core.datetime_utils import normalize_app_datetime
from app.db.session import AsyncSessionLocal, LoopSafeAsyncSessionLocal
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.billing_service import BillingService
from app.services.generation_task_scheduler import (
    GenerationTaskScheduler,
    wait_generation_scheduler_wakeup,
)
from app.services.generation_task_executor import GenerationTaskExecutor
from app.services.generation_terminalization import GenerationTerminalizationService

logger = logging.getLogger(__name__)


class TaskPoller:
    """Manages background asyncio tasks that poll external providers for generation task status."""

    def __init__(self):
        self._active_tasks: dict[int, asyncio.Task] = {}
        self._scheduler_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def active_count(self) -> int:
        return len(self._active_tasks)

    def start_polling(
        self,
        task_id: int,
        user_id: int,
        provider_code: str,
        task_type: str,
        created_at: datetime,
        *,
        claim_token: str | None = None,
    ):
        """Start a background polling coroutine for the given task."""
        if task_id in self._active_tasks:
            logger.debug(f"Polling already active for task {task_id}, skipping")
            return

        coro = self._poll_loop(task_id, user_id, provider_code, task_type, created_at, claim_token=claim_token)
        asyncio_task = asyncio.create_task(coro, name=f"poll-task-{task_id}")
        asyncio_task.add_done_callback(lambda t: self._on_task_done(task_id, t))
        self._active_tasks[task_id] = asyncio_task
        logger.info(f"Started polling for task {task_id} (provider={provider_code}, type={task_type})")

    async def enqueue_task(
        self,
        task_id: int,
        *,
        workflow_stage: str | None = None,
        next_run_at: datetime | None = None,
    ):
        # enqueue_task is reachable from harness intake running on a worker event
        # loop (submit_image/submit_video -> _resume_processing). Use the loop-safe
        # (NullPool) factory so a pooled connection is never shared across loops.
        # This is a single independent enqueue insert, so dropping pooling here is
        # negligible on the main-loop API path as well.
        async with LoopSafeAsyncSessionLocal() as db:
            scheduler = GenerationTaskScheduler(db, worker_id=self._worker_id())
            return await scheduler.enqueue(
                task_id,
                workflow_stage=workflow_stage,
                next_run_at=next_run_at,
            )

    def start_scheduler_loop(self) -> None:
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._shutdown_event = asyncio.Event()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(), name="generation-task-scheduler")

    async def run_scheduler_once(self, *, limit: int = 10) -> int:
        async with AsyncSessionLocal() as db:
            scheduler = GenerationTaskScheduler(db, worker_id=self._worker_id())
            claims = await scheduler.claim_due_tasks(limit=limit, lease_seconds=self._claim_lease_seconds())

        for claim in claims:
            task = claim.task
            self.start_polling(
                task_id=task.id,
                user_id=task.user_id,
                provider_code=task.provider_code,
                task_type=task.task_type,
                created_at=task.created_at,
                claim_token=claim.claim_token,
            )
        return len(claims)

    async def _scheduler_loop(self) -> None:
        interval = max(float(GENERATION_SCHEDULER_IDLE_WAIT_SECONDS), 0.1)
        while not self._shutdown_event.is_set():
            try:
                processed = await self.run_scheduler_once()
                if processed > 0:
                    continue
                await wait_generation_scheduler_wakeup(timeout_seconds=interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Generation task scheduler tick failed")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                except TimeoutError:
                    continue

    @staticmethod
    def _worker_id() -> str:
        import os
        import socket

        return f"generation-scheduler:{socket.gethostname()}:{os.getpid()}"

    def _on_task_done(self, task_id: int, asyncio_task: asyncio.Task):
        """Callback when an asyncio task finishes."""
        self._active_tasks.pop(task_id, None)
        if asyncio_task.cancelled():
            logger.info(f"Polling for task {task_id} was cancelled")
        elif asyncio_task.exception():
            logger.error(
                f"Polling for task {task_id} failed with exception",
                exc_info=asyncio_task.exception(),
            )

    def _get_timeout(self, task_type: str) -> int:
        """Return timeout in seconds based on task type."""
        if task_type == "text2image":
            return settings.TASK_TIMEOUT_IMAGE_SECONDS
        return settings.TASK_TIMEOUT_VIDEO_SECONDS

    def _claim_lease_seconds(self) -> int:
        return max(int(TASK_POLL_CLAIM_LEASE_SECONDS or 0), 5)

    def _claim_renewal_interval_seconds(self) -> float:
        return max(float(self._claim_lease_seconds()) / 3.0, 1.0)

    async def _claim_scheduler_task(self, task_id: int, claim_token: str) -> bool:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=self._claim_lease_seconds())
        async with AsyncSessionLocal() as db:
            repo = GenerationTaskRepository(db)
            claimed = await repo.claim_scheduler_task(
                task_id=task_id,
                now=now,
                lease_expires_at=lease_expires_at,
                claim_token=claim_token,
            )
        return claimed is not None

    async def _renew_scheduler_task_claim(self, task_id: int, claim_token: str) -> bool:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=self._claim_lease_seconds())
        async with AsyncSessionLocal() as db:
            repo = GenerationTaskRepository(db)
            claimed = await repo.renew_scheduler_task_claim(
                task_id=task_id,
                now=now,
                lease_expires_at=lease_expires_at,
                claim_token=claim_token,
            )
        return claimed is not None

    async def _release_scheduler_task_claim(self, task_id: int, claim_token: str) -> None:
        async with AsyncSessionLocal() as db:
            repo = GenerationTaskRepository(db)
            await repo.release_scheduler_task_claim(task_id=task_id, claim_token=claim_token)

    async def _poll_loop(
        self,
        task_id: int,
        user_id: int,
        provider_code: str,
        task_type: str,
        created_at: datetime,
        *,
        claim_token: str | None = None,
    ):
        """The main polling coroutine for a single task."""
        timeout_seconds = self._get_timeout(task_type)
        interval = max(float(GENERATION_TASK_ACTIVE_POLL_SECONDS), 0.1)
        lease_token = str(claim_token or uuid4().hex)

        if claim_token is None:
            if not await self._claim_scheduler_task(task_id, lease_token):
                logger.info("Skipping polling for task %s because another worker holds the scheduler claim", task_id)
                return

        try:
            while not self._shutdown_event.is_set():
                if not await self._renew_scheduler_task_claim(task_id, lease_token):
                    logger.info("Stopping polling for task %s because the scheduler claim could not be renewed", task_id)
                    return

                # Check timeout — handle both naive and aware datetimes
                now = datetime.now(UTC)
                created = normalize_app_datetime(created_at)
                elapsed = (now - created).total_seconds()
                if elapsed > timeout_seconds:
                    logger.warning(
                        f"Task {task_id} timed out after {elapsed:.0f}s (limit={timeout_seconds}s)"
                    )
                    await self._handle_timeout(task_id, user_id)
                    return

                # Poll the external provider
                try:
                    terminal = await self._poll_once(task_id, user_id, lease_token)
                    if terminal:
                        return
                except Exception:
                    logger.exception(f"Error polling task {task_id}, will retry")

                await asyncio.sleep(interval)
        finally:
            await self._release_scheduler_task_claim(task_id, lease_token)

    async def _poll_once(self, task_id: int, user_id: int, claim_token: str) -> bool:
        """Query the external provider once. Returns True if task reached terminal state."""
        async with AsyncSessionLocal() as db:
            executor = GenerationTaskExecutor(db)
            task = await self._run_with_claim_heartbeat(
                task_id=task_id,
                claim_token=claim_token,
                operation=lambda: executor.execute_once(
                    task_id=task_id,
                    user_id=user_id,
                    scheduler_claim_token=claim_token,
                ),
            )

            if task is None:
                return True
            if task.status == "completed":
                await self._handle_completion(db, task)
                return True
            elif task.status == "failed":
                await self._handle_failure(db, task, user_id)
                return True
            else:
                from app.services.generation_artifact_events import publish_generation_task_artifact_progress_update

                await publish_generation_task_artifact_progress_update(task)

        return False

    async def _run_with_claim_heartbeat(self, *, task_id: int, claim_token: str, operation):
        stop = asyncio.Event()

        async def _heartbeat() -> None:
            interval = self._claim_renewal_interval_seconds()
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                    return
                except TimeoutError:
                    pass
                try:
                    renewed = await self._renew_scheduler_task_claim(task_id, claim_token)
                except Exception:
                    logger.exception("Failed to renew scheduler claim heartbeat for task %s", task_id)
                    continue
                if not renewed:
                    logger.info("Scheduler claim heartbeat lost for task %s", task_id)
                    return

        heartbeat = asyncio.create_task(_heartbeat(), name=f"poll-task-{task_id}-claim-heartbeat")
        try:
            return await operation()
        finally:
            stop.set()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _handle_timeout(self, task_id: int, user_id: int):
        """Mark a task as failed due to timeout and handle billing."""
        async with AsyncSessionLocal() as db:
            repo = GenerationTaskRepository(db)
            task = await repo.get(task_id)
            if task and task.status not in ("completed", "failed"):
                task = await repo.update(
                    task,
                    {"status": "failed", "error_message": "任务超时"},
                )
                await self._handle_failure(db, task, user_id)

    async def _handle_completion(self, db, task):
        """Update usage log on successful completion."""
        await self._finalize_terminal_side_effects(db, task)
        logger.info(f"Task {task.id} completed successfully")

    async def _handle_failure(self, db, task, user_id: int):
        """Refund amount and update usage log on failure."""
        await self._finalize_terminal_side_effects(db, task, user_id=user_id)
        logger.info(f"Task {task.id} failed, billing handled")

    async def _finalize_terminal_side_effects(self, db, task, *, user_id: int | None = None) -> None:
        if getattr(task, "terminal_side_effects_finalized_at", None) is not None:
            return

        finalized = await GenerationTerminalizationService(
            db,
            billing_service_factory=BillingService,
            agent_usage_log_updater=self._update_agent_usage_log,
        ).finalize_terminal_task(task, user_id=user_id)
        if not finalized:
            return

        if not all(hasattr(db, attr) for attr in ("execute", "commit")):
            return
        await GenerationTaskRepository(db).mark_terminal_side_effects_finalized(task.id)

    @staticmethod
    def _is_terminal_generation_status(status: str | None) -> bool:
        return status in {"completed", "failed"}

    @staticmethod
    def _resolve_agent_generation_refund_amount(
        generation_task: dict | None,
        usage_params: dict,
        task_id: int,
    ) -> int:
        if isinstance(generation_task, dict):
            amount = generation_task.get("amount_cents")
            if amount is not None:
                return max(int(amount or 0), 0)

        items = usage_params.get("items")
        if not isinstance(items, dict):
            return 0

        refund_amount = 0
        for details in items.values():
            if not isinstance(details, list):
                continue
            for detail in details:
                if not isinstance(detail, dict) or detail.get("task_id") != task_id:
                    continue
                amount = detail.get("amount_cents")
                if amount is None:
                    amount = detail.get("amount")
                refund_amount += max(int(amount or 0), 0)
        return refund_amount

    async def _update_agent_usage_log(self, db, task) -> None:
        task_params = task.params or {}
        if not isinstance(task_params, dict):
            return

        parent_usage_log_id = task_params.get("parent_usage_log_id")
        child_usage_log_id = task_params.get("agent_usage_log_id")
        if parent_usage_log_id and child_usage_log_id:
            billing_svc = BillingService(db)
            child_log = await billing_svc.usage_repo.get(child_usage_log_id)
            if not child_log:
                return

            finished_at = normalize_app_datetime(task.updated_at) or datetime.now(UTC)

            elapsed_ms = child_log.elapsed_ms or 0
            if getattr(child_log, "created_at", None) is not None:
                created_at = normalize_app_datetime(child_log.created_at)
                elapsed_ms = max(
                    elapsed_ms,
                    int((finished_at - created_at).total_seconds() * 1000),
                )

            child_params = dict(child_log.params or {})
            child_params.update({
                "agent_run_id": task_params.get("agent_run_id"),
                "conversation_id": task_params.get("agent_conversation_id"),
                "result_url": task.result_url,
                "error_message": task.error_message,
            })

            if task.status == "failed" and child_log.status != "refunded":
                refund_amount = max(int(child_log.amount_cents_original or child_log.amount_cents or 0), 0)
                await billing_svc.refund_usage_log_by_id_once(
                    log_id=child_log.id,
                    user_id=getattr(task, "user_id", 0),
                    refund_amount=refund_amount,
                    params=child_params,
                    elapsed_ms=elapsed_ms,
                )
                return
            else:
                await billing_svc.update_usage_log(
                    child_log.id,
                    {
                        "status": "success" if task.status == "completed" else child_log.status,
                        "elapsed_ms": elapsed_ms,
                        "params": child_params,
                    },
                )

            actual_parent_id = getattr(child_log, "parent_id", None) or parent_usage_log_id
            await billing_svc.refresh_parent_usage_log(
                actual_parent_id,
                finished_at=finished_at,
            )
            return

        agent_run_id = task_params.get("agent_run_id")
        if not agent_run_id:
            return

        billing_svc = BillingService(db)
        usage_log = await billing_svc.usage_repo.get_latest_agent_log_by_run_id(agent_run_id)
        if not usage_log:
            return

        usage_params = dict(usage_log.params or {})
        started_at_raw = usage_params.get("agent_started_at")
        if not started_at_raw:
            return

        try:
            started_at = datetime.fromisoformat(started_at_raw)
        except ValueError:
            logger.warning("Invalid agent_started_at for usage log %s", usage_log.id)
            return

        started_at = normalize_app_datetime(started_at)

        finished_at = normalize_app_datetime(task.updated_at) or datetime.now(UTC)

        elapsed_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
        timing_breakdown = usage_params.get("timing_breakdown_ms")
        if not isinstance(timing_breakdown, dict):
            timing_breakdown = {}
        timing_breakdown["async_generation"] = max(
            int(timing_breakdown.get("async_generation", 0) or 0),
            elapsed_ms,
        )
        usage_params["timing_breakdown_ms"] = timing_breakdown

        generation_tasks = usage_params.get("generation_tasks")
        updated_generation_task: dict | None = None
        if isinstance(generation_tasks, list):
            for item in generation_tasks:
                if not isinstance(item, dict) or item.get("task_id") != task.id:
                    continue
                item["status"] = task.status
                item["completed_at"] = finished_at.isoformat()
                item["result_url"] = task.result_url
                item["error_message"] = task.error_message
                item["reference_diagnostics"] = task_params.get("reference_diagnostics")
                updated_generation_task = item
                break

        generation_artifacts = usage_params.get("generation_artifacts")
        artifact_ref = (task.params or {}).get("artifact_ref") if isinstance(task.params, dict) else None
        if artifact_ref and isinstance(generation_artifacts, list):
            for item in generation_artifacts:
                if not isinstance(item, dict) or item.get("artifact_ref") != artifact_ref:
                    continue
                item["task_id"] = task.id
                item["status"] = task.status
                item["completed_at"] = finished_at.isoformat()
                item["result_url"] = task.result_url
                item["error_message"] = task.error_message
                item["reference_diagnostics"] = task_params.get("reference_diagnostics")
                if task.status == "failed":
                    item["retry_count"] = min(
                        int(item.get("retry_count") or 0) + 1,
                        int(item.get("max_retry") or 3),
                    )
                break

        all_terminal = True
        if isinstance(generation_tasks, list):
            for item in generation_tasks:
                if not isinstance(item, dict):
                    continue
                if not self._is_terminal_generation_status(item.get("status")):
                    all_terminal = False
                    break

        update_data = {
            "elapsed_ms": max(usage_log.elapsed_ms or 0, elapsed_ms),
            "params": usage_params,
            "status": "success" if all_terminal else "pending",
        }

        if (
            task.status == "failed"
            and not (updated_generation_task or {}).get("refund_recorded_at")
        ):
            claim_usage_log_lock = getattr(billing_svc, "_claim_usage_log_lock", None)
            if callable(claim_usage_log_lock):
                claimed_usage_log, _lock_token = await claim_usage_log_lock(
                    usage_log.id,
                    statuses=["pending", "success"],
                )
                if not claimed_usage_log:
                    return
                usage_log = claimed_usage_log
                usage_params = dict(usage_log.params or {})
                generation_tasks = usage_params.get("generation_tasks")
                updated_generation_task = None
                if isinstance(generation_tasks, list):
                    for item in generation_tasks:
                        if not isinstance(item, dict) or item.get("task_id") != task.id:
                            continue
                        item["status"] = task.status
                        item["completed_at"] = finished_at.isoformat()
                        item["result_url"] = task.result_url
                        item["error_message"] = task.error_message
                        item["reference_diagnostics"] = task_params.get("reference_diagnostics")
                        updated_generation_task = item
                        break
            refund_amount = self._resolve_agent_generation_refund_amount(
                updated_generation_task,
                usage_params,
                task.id,
            )
            if refund_amount > 0:
                user_id = getattr(task, "user_id", 0)
                await billing_svc.refund_balance(user_id, refund_amount)
                update_data["amount_cents"] = max(
                    int(usage_log.amount_cents or 0) - refund_amount,
                    0,
                )
                usage_params["total_amount_cents"] = max(
                    int(usage_params.get("total_amount_cents") or usage_log.amount_cents or 0)
                    - refund_amount,
                    0,
                )
                if updated_generation_task is not None:
                    updated_generation_task["refund_amount_cents"] = refund_amount
                    updated_generation_task["refund_recorded_at"] = (
                        finished_at.isoformat()
                    )
            update_data = {
                **update_data,
                "elapsed_ms": max(usage_log.elapsed_ms or 0, elapsed_ms),
                "params": usage_params,
                "status": "success" if all_terminal else "pending",
            }
            if callable(claim_usage_log_lock):
                update_data["billing_locked_until"] = None
                update_data["billing_lock_token"] = None

        await billing_svc.update_usage_log(usage_log.id, update_data)

    async def recover_on_startup(self):
        """Load all pending/processing tasks from DB and resume polling."""
        try:
            async with AsyncSessionLocal() as db:
                repo = GenerationTaskRepository(db)
                incomplete_tasks = await repo.get_incomplete_tasks()

            logger.info(f"Startup recovery: found {len(incomplete_tasks)} incomplete tasks")

            for task in incomplete_tasks:
                if str(getattr(task, "workflow_stage", "") or "") == "provider_operation":
                    continue
                # Pending tasks without external_task_id were never submitted — mark as failed
                if not task.external_task_id:
                    async with AsyncSessionLocal() as db:
                        repo = GenerationTaskRepository(db)
                        t = await repo.get(task.id)
                        if t and t.status not in ("completed", "failed"):
                            t = await repo.update(
                                t,
                                {
                                    "status": "failed",
                                    "error_message": "服务重启，任务未完成提交",
                                },
                            )
                            await self._handle_failure(db, t, task.user_id)
                    continue

                claim_token = uuid4().hex
                if not await self._claim_scheduler_task(task.id, claim_token):
                    logger.info("Startup recovery skipped task %s because another worker already claimed it", task.id)
                    continue
                self.start_polling(
                    task_id=task.id,
                    user_id=task.user_id,
                    provider_code=task.provider_code,
                    task_type=task.task_type,
                    created_at=task.created_at,
                    claim_token=claim_token,
                )
            await self.recover_terminal_side_effects_on_startup()
        except Exception as e:
            logger.error(f"Failed to recover tasks on startup (database might not be ready): {e}")

    async def recover_terminal_side_effects_on_startup(self, *, batch_size: int = 100) -> int:
        recovered = 0
        after_id = 0
        while True:
            async with AsyncSessionLocal() as db:
                repo = GenerationTaskRepository(db)
                tasks = await repo.list_terminal_tasks_pending_side_effects(
                    after_id=after_id,
                    limit=batch_size,
                )
            if not tasks:
                return recovered

            for task_snapshot in tasks:
                after_id = max(after_id, int(task_snapshot.id))
                try:
                    async with AsyncSessionLocal() as db:
                        repo = GenerationTaskRepository(db)
                        task = await repo.get(task_snapshot.id)
                        if (
                            task is None
                            or task.status not in {"completed", "failed"}
                            or task.terminal_side_effects_finalized_at is not None
                        ):
                            continue
                        if task.status == "completed":
                            await self._handle_completion(db, task)
                        else:
                            await self._handle_failure(db, task, task.user_id)
                        recovered += 1
                except Exception:
                    logger.exception(
                        "Failed to recover terminal generation side effects for task %s",
                        getattr(task_snapshot, "id", None),
                    )

    async def shutdown(self):
        """Signal all polling loops to stop and wait for them to finish."""
        logger.info(f"Shutting down TaskPoller, {len(self._active_tasks)} active tasks")
        self._shutdown_event.set()

        if self._scheduler_task is not None:
            try:
                await asyncio.wait_for(self._scheduler_task, timeout=10)
            except TimeoutError:
                self._scheduler_task.cancel()
                await asyncio.gather(self._scheduler_task, return_exceptions=True)
            finally:
                self._scheduler_task = None

        if self._active_tasks:
            tasks = list(self._active_tasks.values())
            done, pending = await asyncio.wait(tasks, timeout=10)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.wait(pending, timeout=5)

        logger.info("TaskPoller shutdown complete")


# Module-level singleton
task_poller = TaskPoller()
