from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.services.billing_service import BillingService

logger = logging.getLogger(__name__)

TERMINAL_GENERATION_STATUSES = {"completed", "failed"}

BillingServiceFactory = Callable[[Any], BillingService]
ArtifactPublisher = Callable[[Any], Awaitable[None]]
AgentUsageLogUpdater = Callable[[Any, Any], Awaitable[None]]


@dataclass(frozen=True)
class GenerationTerminalResult:
    task_id: int
    user_id: int
    status: str
    provider_code: str
    builtin_provider_code: str | None

    @classmethod
    def from_task(cls, task: Any) -> GenerationTerminalResult:
        return cls(
            task_id=int(getattr(task, "id")),
            user_id=int(getattr(task, "user_id", 0) or 0),
            status=str(getattr(task, "status", "") or "").strip().lower(),
            provider_code=str(getattr(task, "provider_code", "") or "").strip(),
            builtin_provider_code=str(getattr(task, "builtin_provider_code", "") or "").strip() or None,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_GENERATION_STATUSES


class GenerationTerminalizationService:
    def __init__(
        self,
        db: Any,
        *,
        billing_service_factory: BillingServiceFactory = BillingService,
        artifact_publisher: ArtifactPublisher | None = None,
        agent_usage_log_updater: AgentUsageLogUpdater | None = None,
    ) -> None:
        self.db = db
        self._billing_service_factory = billing_service_factory
        self._artifact_publisher = artifact_publisher or self._publish_artifact_update
        self._agent_usage_log_updater = agent_usage_log_updater

    async def finalize_terminal_task(self, task: Any, *, user_id: int | None = None) -> bool:
        terminal = GenerationTerminalResult.from_task(task)
        if not terminal.is_terminal:
            return False

        # The user-visible terminal event (canvas item -> completed/failed) MUST land even
        # when billing/refund raises. Otherwise a billing error leaves the canvas item stuck
        # at "generating" and the whole run stays "running" forever. So publish the artifact
        # event FIRST, then settle billing, isolating each so one failure never suppresses
        # the other. Only report full success — which lets the caller set the
        # `terminal_side_effects_finalized_at` idempotency flag — when every side effect
        # succeeds; otherwise leave it pending so `recover_terminal_side_effects_on_startup`
        # retries the unfinished parts.
        artifact_ok = await self._run_side_effect(
            "artifact_publish", task, self._artifact_publisher(task)
        )
        billing_ok = await self._run_side_effect(
            "billing", task, self._finalize_billing(terminal, task, user_id=user_id)
        )
        usage_ok = True
        if self._agent_usage_log_updater is not None:
            usage_ok = await self._run_side_effect(
                "agent_usage_log", task, self._agent_usage_log_updater(self.db, task)
            )
        return artifact_ok and billing_ok and usage_ok

    @staticmethod
    async def _run_side_effect(label: str, task: Any, awaitable: Awaitable[None]) -> bool:
        try:
            await awaitable
            return True
        except Exception:
            logger.exception(
                "Generation terminal side effect failed: side_effect=%s task_id=%s",
                label,
                getattr(task, "id", None),
            )
            return False

    async def _finalize_billing(
        self,
        terminal: GenerationTerminalResult,
        task: Any,
        *,
        user_id: int | None,
    ) -> None:
        if terminal.provider_code != "builtin":
            return

        billing_svc = self._billing_service_factory(self.db)
        if terminal.status == "completed":
            if terminal.builtin_provider_code == "lingyaai":
                await billing_svc.finalize_lingyaai_generation_billing(task)
            else:
                await billing_svc.finalize_apimart_generation_billing(task)
            return

        await billing_svc.refund_generation_usage_log_if_pending(
            terminal.task_id,
            int(user_id if user_id is not None else terminal.user_id),
        )

    @staticmethod
    async def _publish_artifact_update(task: Any) -> None:
        from app.services.generation_artifact_events import publish_generation_task_artifact_update

        await publish_generation_task_artifact_update(task)


def build_generation_terminal_update(
    result: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    update = dict(result or {})
    status = str(update.get("status") or "").strip().lower()
    if status not in TERMINAL_GENERATION_STATUSES:
        return update

    terminalized_at = now or datetime.now(UTC)
    update.setdefault("terminalized_at", terminalized_at)
    update.setdefault("scheduler_next_run_at", None)
    update.setdefault("scheduler_claim_token", None)
    update.setdefault("scheduler_claimed_at", None)
    update.setdefault("scheduler_lease_expires_at", None)
    if status == "completed":
        update.setdefault("workflow_stage", "terminal_completed")
    else:
        update.setdefault("workflow_stage", "terminal_failed")
        update.setdefault("last_error_type", _classify_error_type(update.get("error_message")))
    return update


def _classify_error_type(error_message: Any) -> str:
    message = str(error_message or "").strip().lower()
    if "download" in message or "result_url_download_failed" in message:
        return "result_materialization_failed"
    return "provider_failed"
