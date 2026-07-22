"""Balance management service for billing, refunds, and usage logging."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_pricing import PRICING_RULES, calculate_amount_cents, get_model_label
from app.core.config import settings
from app.core.datetime_utils import normalize_app_datetime
from app.core.media_capabilities import get_model_label as get_provider_model_label
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.core.provider_balance_mode import is_provider_balance_sync_enabled
from app.models.billing import UsageLog
from app.models.user import User
from app.repositories.billing_repository import UsageLogRepository
from app.services.provider_balance_sync import provider_balance_sync_service
from app.services.user_apimart_key_service import UserApimartKeyService

logger = logging.getLogger(__name__)


def _bucket_for_task_type(task_type: str | None) -> str:
    normalized = str(task_type or "").strip()
    if normalized in {"text2video", "image2video"}:
        return "text2video"
    if normalized in {"multimodal", "image_analysis", "context_compression"}:
        return "multimodal"
    return "text2image"


def _resolve_default_model_label(
    explicit: str | None,
    provider_code: str | None,
    task_type: str | None,
    model_name: str,
) -> str:
    explicit_label = str(explicit or "").strip()
    if explicit_label:
        return explicit_label
    provider_label = get_provider_model_label(provider_code, _bucket_for_task_type(task_type), model_name)
    if provider_label and provider_label != model_name:
        return provider_label
    return get_model_label(model_name)


class BillingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usage_repo = UsageLogRepository(db)
        self._admin_id: int | None = None

    _SUMMARY_COUNT_KEYS = {
        "multimodal": "multimodal_calls",
        "image_analysis": "image_analysis_calls",
        "image_generation": "image_generation_calls",
        "video_generation": "video_generation_calls",
        "context_compression": "context_compression_calls",
    }
    _SUMMARY_MODELS_KEYS = {
        "multimodal": "multimodal_models",
        "image_analysis": "image_analysis_models",
        "image_generation": "image_models",
        "video_generation": "video_models",
        "context_compression": "context_compression_models",
    }
    _SUMMARY_STATS_KEYS = {
        "multimodal": "multimodal_model_stats",
        "image_analysis": "image_analysis_model_stats",
        "image_generation": "image_model_stats",
        "video_generation": "video_model_stats",
        "context_compression": "context_compression_model_stats",
    }
    _IMAGE_GENERATION_TASK_TYPES = {"text2image", "image_edit", "image_erase"}
    _VIDEO_GENERATION_TASK_TYPES = {"text2video", "image2video"}

    async def _get_admin_id(self) -> int:
        if self._admin_id is not None:
            return self._admin_id

        from sqlalchemy import select
        result = await self.db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="系统错误：未找到 admin 账号",
            )
        self._admin_id = admin.id
        return self._admin_id

    async def _effective_balance_user_id(self, user_id: int) -> int:
        """Resolve the account that actually holds the balance for a charge/refund.

        Mirrors the remap that ``deduct_balance`` / ``refund_balance`` apply: in a private
        deployment every charge is pooled on the admin account. Refund/finalize paths that
        mutate balances inline must use this so a refund lands on the same account the
        original debit came from instead of crediting the requesting user.
        """
        if settings.DEPLOY_TYPE == "private":
            return await self._get_admin_id()
        return int(user_id)

    @classmethod
    def _usage_log_summary_category(cls, log: UsageLog) -> str | None:
        task_type = str(getattr(log, "task_type", "") or "").strip()
        if task_type in {"multimodal", "image_analysis", "context_compression"}:
            return task_type
        if task_type in cls._IMAGE_GENERATION_TASK_TYPES:
            return "image_generation"
        if task_type in cls._VIDEO_GENERATION_TASK_TYPES:
            return "video_generation"

        billing_label = str(getattr(log, "billing_label", "") or "")
        if "image_" in billing_label or "image_generate" in billing_label:
            return "image_generation"
        if "video_" in billing_label or "video_generate" in billing_label:
            return "video_generation"
        return None

    @classmethod
    def _empty_agent_billing_summary(cls, base_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        base = base_summary if isinstance(base_summary, dict) else {}
        summary: dict[str, Any] = {
            "mode": base.get("mode"),
            "mode_label": base.get("mode_label"),
            "total_elapsed_ms": 0,
        }
        for category, key in cls._SUMMARY_COUNT_KEYS.items():
            del category
            summary[key] = 0
        for category, key in cls._SUMMARY_MODELS_KEYS.items():
            del category
            summary[key] = []
        for category, key in cls._SUMMARY_STATS_KEYS.items():
            del category
            summary[key] = []
        return summary

    @staticmethod
    def _merge_model_stats(
        existing: list[dict[str, Any]] | None,
        derived: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for stats_entries in (existing or [], derived or []):
            for stats in stats_entries:
                if not isinstance(stats, dict):
                    continue
                model_name = str(stats.get("model_name") or "").strip()
                if not model_name:
                    continue
                current = merged.setdefault(
                    model_name,
                    {
                        "model_name": model_name,
                        "model_label": stats.get("model_label") or get_model_label(model_name),
                        "calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                    },
                )
                current["model_label"] = current.get("model_label") or stats.get("model_label") or get_model_label(model_name)
                for key in ("calls", "success_calls", "failed_calls"):
                    try:
                        value = int(stats.get(key) or 0)
                    except (TypeError, ValueError):
                        value = 0
                    current[key] = max(int(current.get(key) or 0), value)
        return sorted(merged.values(), key=lambda item: str(item.get("model_label") or item.get("model_name") or ""))

    @classmethod
    def _agent_billing_summary_from_children(
        cls,
        children: list[UsageLog],
        *,
        base_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summary = cls._empty_agent_billing_summary(base_summary)
        model_sets: dict[str, set[str]] = {category: set() for category in cls._SUMMARY_COUNT_KEYS}
        model_stats: dict[str, dict[str, dict[str, Any]]] = {category: {} for category in cls._SUMMARY_COUNT_KEYS}
        total_elapsed_ms = 0

        for child in children:
            category = cls._usage_log_summary_category(child)
            if category is None:
                continue

            count_key = cls._SUMMARY_COUNT_KEYS[category]
            summary[count_key] = int(summary.get(count_key) or 0) + 1

            try:
                total_elapsed_ms += max(int(getattr(child, "elapsed_ms", 0) or 0), 0)
            except (TypeError, ValueError):
                pass

            model_name = str(getattr(child, "model_name", "") or "").strip()
            if not model_name:
                continue

            model_sets[category].add(model_name)
            model_label = str(getattr(child, "model_label", "") or "").strip() or get_model_label(model_name)
            stats = model_stats[category].setdefault(
                model_name,
                {
                    "model_name": model_name,
                    "model_label": model_label,
                    "calls": 0,
                    "success_calls": 0,
                    "failed_calls": 0,
                },
            )
            stats["calls"] += 1
            status = str(getattr(child, "status", "") or "").strip().lower()
            if status == "success":
                stats["success_calls"] += 1
            elif status in {"failed", "blocked", "refunded", "cancelled"}:
                stats["failed_calls"] += 1

        for category, models in model_sets.items():
            summary[cls._SUMMARY_MODELS_KEYS[category]] = sorted(models)
            summary[cls._SUMMARY_STATS_KEYS[category]] = sorted(
                model_stats[category].values(),
                key=lambda item: str(item.get("model_label") or item.get("model_name") or ""),
            )
        summary["total_elapsed_ms"] = total_elapsed_ms
        return summary

    @classmethod
    def _merge_agent_billing_summary(
        cls,
        existing_summary: dict[str, Any] | None,
        child_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(existing_summary, dict):
            existing_summary = {}
        merged = cls._empty_agent_billing_summary(existing_summary or child_summary)
        merged["mode"] = existing_summary.get("mode") or child_summary.get("mode")
        merged["mode_label"] = existing_summary.get("mode_label") or child_summary.get("mode_label")

        for category, count_key in cls._SUMMARY_COUNT_KEYS.items():
            try:
                existing_count = int(existing_summary.get(count_key) or 0)
            except (TypeError, ValueError):
                existing_count = 0
            try:
                child_count = int(child_summary.get(count_key) or 0)
            except (TypeError, ValueError):
                child_count = 0
            merged[count_key] = max(existing_count, child_count)

            models_key = cls._SUMMARY_MODELS_KEYS[category]
            existing_models = existing_summary.get(models_key) if isinstance(existing_summary.get(models_key), list) else []
            child_models = child_summary.get(models_key) if isinstance(child_summary.get(models_key), list) else []
            merged[models_key] = sorted({
                str(model).strip()
                for model in [*existing_models, *child_models]
                if str(model or "").strip()
            })

            stats_key = cls._SUMMARY_STATS_KEYS[category]
            merged[stats_key] = cls._merge_model_stats(
                existing_summary.get(stats_key) if isinstance(existing_summary.get(stats_key), list) else [],
                child_summary.get(stats_key) if isinstance(child_summary.get(stats_key), list) else [],
            )

        try:
            existing_elapsed = int(existing_summary.get("total_elapsed_ms") or 0)
        except (TypeError, ValueError):
            existing_elapsed = 0
        try:
            child_elapsed = int(child_summary.get("total_elapsed_ms") or 0)
        except (TypeError, ValueError):
            child_elapsed = 0
        merged["total_elapsed_ms"] = max(existing_elapsed, child_elapsed)
        return merged

    @classmethod
    def _refresh_agent_billing_summary_from_children(
        cls,
        params: dict[str, Any],
        children: list[UsageLog],
    ) -> dict[str, Any]:
        if not children:
            return params
        if params.get("engine") != "agent_harness" and not isinstance(params.get("billing_summary"), dict):
            return params

        existing_summary = params.get("billing_summary") if isinstance(params.get("billing_summary"), dict) else {}
        child_summary = cls._agent_billing_summary_from_children(children, base_summary=existing_summary)
        params["billing_summary"] = cls._merge_agent_billing_summary(existing_summary, child_summary)
        return params

    @classmethod
    def _agent_parent_elapsed_ms(cls, params: dict[str, Any]) -> int | None:
        if params.get("engine") != "agent_harness":
            return None
        summary = params.get("billing_summary")
        if not isinstance(summary, dict):
            return None
        try:
            return max(int(summary.get("total_elapsed_ms") or 0), 0)
        except (TypeError, ValueError):
            return None

    async def get_balance(self, user_id: int) -> int:
        if is_provider_balance_sync_enabled():
            user = await self.db.get(User, user_id)
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")
            api_key, _credential_id = await UserApimartKeyService(self.db).resolve_key(
                user_id,
                user_role=user.role,
            )
            return await provider_balance_sync_service.get_balance_cents(api_key)

        target_user_id = user_id
        if settings.DEPLOY_TYPE == "private":
            target_user_id = await self._get_admin_id()

        user = await self.db.get(User, target_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return int(user.balance_cents or 0)

    async def get_display_balance(self, user_id: int) -> int:
        """Return a UI-safe balance without weakening model-call key validation."""
        if not is_provider_balance_sync_enabled():
            return await self.get_balance(user_id)

        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        credential = await UserApimartKeyService(self.db).get_current_credential(user_id)
        if credential is None or credential.status != "active":
            return 0
        return await provider_balance_sync_service.get_balance_cents(credential.api_key)

    async def deduct_balance(self, user_id: int, amount_cents: int) -> bool:
        if amount_cents <= 0:
            return True
        if is_provider_balance_sync_enabled():
            return (await self.get_balance(user_id)) > 0

        target_user_id = user_id
        if settings.DEPLOY_TYPE == "private":
            target_user_id = await self._get_admin_id()

        result = await self.db.execute(
            update(User)
            .where(User.id == target_user_id, User.balance_cents >= amount_cents)
            .values(balance_cents=User.balance_cents - amount_cents)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def refund_balance(self, user_id: int, amount_cents: int) -> None:
        if amount_cents <= 0:
            return
        if is_provider_balance_sync_enabled():
            return

        target_user_id = user_id
        if settings.DEPLOY_TYPE == "private":
            target_user_id = await self._get_admin_id()

        await self.db.execute(
            update(User)
            .where(User.id == target_user_id)
            .values(balance_cents=User.balance_cents + amount_cents)
        )
        await self.db.commit()

    async def create_usage_log(
        self,
        user_id: int,
        task_id: int | None,
        model_name: str,
        task_type: str,
        amount_cents: int,
        model_label: str | None = None,
        parent_id: int | None = None,
        billing_key: str | None = None,
        params: dict | None = None,
        task_status: str = "pending",
        billing_label: str | None = None,
        elapsed_ms: int | None = None,
        provider_code: str | None = None,
        provider_request_id: str | None = None,
        provider_trace_id: str | None = None,
        provider_task_id: str | None = None,
        billing_mode: str | None = None,
        billing_attempt_count: int = 0,
        billing_next_run_at: datetime | None = None,
        billing_locked_until: datetime | None = None,
        billing_lock_token: str | None = None,
        billing_finalized_at: datetime | None = None,
        provider_quota: int | None = None,
        provider_prompt_tokens: int | None = None,
        provider_completion_tokens: int | None = None,
        return_created: bool = False,
    ) -> UsageLog | tuple[UsageLog, bool]:
        if is_provider_balance_sync_enabled():
            amount_cents = 0
            billing_mode = "provider_balance_sync"
        log = UsageLog(
            user_id=user_id,
            parent_id=parent_id,
            task_id=task_id,
            model_name=model_name,
            model_label=_resolve_default_model_label(model_label, provider_code, task_type, model_name),
            task_type=task_type,
            billing_key=str(billing_key or "").strip() or None,
            amount_cents=amount_cents,
            amount_cents_original=amount_cents,
            billing_label=billing_label,
            elapsed_ms=elapsed_ms,
            status=task_status,
            provider_code=provider_code,
            provider_request_id=provider_request_id,
            provider_trace_id=provider_trace_id,
            provider_task_id=provider_task_id,
            billing_mode=billing_mode,
            billing_attempt_count=billing_attempt_count,
            billing_next_run_at=billing_next_run_at,
            billing_locked_until=billing_locked_until,
            billing_lock_token=billing_lock_token,
            billing_finalized_at=billing_finalized_at,
            provider_quota=provider_quota,
            provider_prompt_tokens=provider_prompt_tokens,
            provider_completion_tokens=provider_completion_tokens,
            params=sanitize_persistent_payload(params),
        )
        if log.billing_key:
            create_or_get_by_billing_key_with_created = getattr(
                self.usage_repo,
                "create_or_get_by_billing_key_with_created",
                None,
            )
            if callable(create_or_get_by_billing_key_with_created):
                existing, created = await create_or_get_by_billing_key_with_created(log)
                return (existing, created) if return_created else existing
            create_or_get_by_billing_key = getattr(self.usage_repo, "create_or_get_by_billing_key", None)
            if callable(create_or_get_by_billing_key):
                existing = await create_or_get_by_billing_key(log)
                return (existing, True) if return_created else existing
        create_or_get = getattr(self.usage_repo, "create_or_get_by_task_id", None)
        if callable(create_or_get):
            existing = await create_or_get(log)
            return (existing, True) if return_created else existing
        created_log = await self.usage_repo.create(log)
        return (created_log, True) if return_created else created_log

    async def update_usage_log_status(self, task_id: int, new_status: str) -> UsageLog | None:
        log = await self.usage_repo.get_by_task_id(task_id)
        if not log:
            return None
        update_data = {"status": new_status}
        if new_status == "refunded":
            update_data["amount_cents"] = 0
        return await self.usage_repo.update(log, update_data)

    async def update_usage_log(self, log_id: int, data: dict) -> UsageLog | None:
        log = await self.usage_repo.get(log_id)
        if not log:
            return None
        if "params" in data:
            data = {**data, "params": sanitize_persistent_payload(data.get("params"))}
        return await self.usage_repo.update(log, data)

    async def _claim_usage_log_lock(
        self,
        log_id: int,
        *,
        statuses: list[str] | None = None,
        lease_seconds: int = 30,
    ) -> tuple[UsageLog | None, str]:
        lock_token = uuid.uuid4().hex
        claim_log_lock = getattr(self.usage_repo, "claim_log_lock", None)
        if not callable(claim_log_lock):
            get_log = getattr(self.usage_repo, "get", None)
            if callable(get_log):
                return await get_log(log_id), lock_token
            return None, lock_token
        now = datetime.now(UTC)
        claimed = await claim_log_lock(
            log_id=int(log_id),
            now=now,
            locked_until=now + timedelta(seconds=max(1, int(lease_seconds))),
            lock_token=lock_token,
            statuses=statuses,
        )
        return claimed, lock_token

    async def refund_generation_usage_log_if_pending(self, task_id: int, user_id: int) -> UsageLog | None:
        log = await self.usage_repo.get_by_task_id(task_id)
        if not log or log.status != "pending":
            return log
        claimed, lock_token = await self._claim_usage_log_lock(log.id, statuses=["pending"])
        if not claimed:
            return await self.usage_repo.get_by_task_id(task_id)

        refund_amount = max(int(claimed.amount_cents_original or claimed.amount_cents or 0), 0)
        if refund_amount > 0 and not is_provider_balance_sync_enabled():
            target_user_id = await self._effective_balance_user_id(user_id)
            await self.db.execute(
                update(User)
                .where(User.id == target_user_id)
                .values(balance_cents=User.balance_cents + refund_amount)
            )
        claimed.amount_cents = 0
        claimed.status = "refunded"
        claimed.billing_locked_until = None
        claimed.billing_lock_token = None
        claimed.billing_finalized_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(claimed)
        if claimed.parent_id:
            await self.refresh_parent_usage_log(claimed.parent_id)
        return claimed

    async def refund_usage_log_by_id_once(
        self,
        *,
        log_id: int,
        user_id: int,
        refund_amount: int,
        params: dict,
        elapsed_ms: int,
    ) -> UsageLog | None:
        log = await self.usage_repo.get(log_id)
        if not log or log.status == "refunded":
            return log
        claimed, lock_token = await self._claim_usage_log_lock(log.id, statuses=["pending", "success"])
        if not claimed:
            return await self.usage_repo.get(log.id)

        if refund_amount > 0 and not is_provider_balance_sync_enabled():
            target_user_id = await self._effective_balance_user_id(user_id)
            await self.db.execute(
                update(User)
                .where(User.id == target_user_id)
                .values(balance_cents=User.balance_cents + int(refund_amount))
            )
        claimed.amount_cents = 0
        claimed.status = "refunded"
        claimed.elapsed_ms = elapsed_ms
        claimed.params = sanitize_persistent_payload(params)
        claimed.billing_locked_until = None
        claimed.billing_lock_token = None
        claimed.billing_finalized_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(claimed)
        if claimed.parent_id:
            await self.refresh_parent_usage_log(claimed.parent_id)
        return claimed

    async def create_provider_reconcile_usage_log(
        self,
        *,
        user_id: int,
        task_id: int | None,
        model_name: str,
        task_type: str,
        provider_code: str,
        provider_request_id: str | None,
        provider_trace_id: str | None = None,
        provider_task_id: str | None = None,
        parent_id: int | None = None,
        billing_key: str | None = None,
        params: dict[str, Any] | None = None,
        billing_label: str | None = None,
        elapsed_ms: int | None = None,
        return_created: bool = False,
        refresh_parent: bool = True,
    ) -> UsageLog | tuple[UsageLog, bool]:
        now = datetime.now(UTC)
        base_params = dict(params or {})
        base_params.update({
            "provider_code": provider_code,
            "manual_review_required": False,
        })
        if is_provider_balance_sync_enabled():
            log = await self.create_usage_log(
                user_id=user_id,
                task_id=task_id,
                model_name=model_name,
                task_type=task_type,
                amount_cents=0,
                parent_id=parent_id,
                billing_key=billing_key,
                params=base_params,
                task_status="success",
                billing_label=billing_label,
                elapsed_ms=elapsed_ms,
                provider_code=provider_code,
                provider_request_id=provider_request_id,
                provider_trace_id=provider_trace_id,
                provider_task_id=provider_task_id,
                billing_mode="provider_balance_sync",
                billing_finalized_at=now,
                return_created=return_created,
            )
            if parent_id and refresh_parent:
                await self.refresh_parent_usage_log(parent_id)
            return log
        if not provider_request_id:
            log = await self.create_usage_log(
                user_id=user_id,
                task_id=task_id,
                model_name=model_name,
                task_type=task_type,
                amount_cents=0,
                parent_id=parent_id,
                billing_key=billing_key,
                params=base_params | {
                    "manual_review_required": True,
                    "manual_review_reason": f"{provider_code}_missing_oneapi_request_id",
                },
                task_status="blocked",
                billing_label=billing_label,
                elapsed_ms=elapsed_ms,
                provider_code=provider_code,
                provider_request_id=provider_request_id,
                provider_trace_id=provider_trace_id,
                provider_task_id=provider_task_id,
                billing_mode="provider_reconcile",
                billing_finalized_at=now,
                return_created=return_created,
            )
            if parent_id and refresh_parent:
                await self.refresh_parent_usage_log(parent_id)
            return log

        log = await self.create_usage_log(
            user_id=user_id,
            task_id=task_id,
            model_name=model_name,
            task_type=task_type,
            amount_cents=0,
            parent_id=parent_id,
            billing_key=billing_key,
            params=base_params,
            task_status="pending",
            billing_label=billing_label,
            elapsed_ms=elapsed_ms,
            provider_code=provider_code,
            provider_request_id=provider_request_id,
            provider_trace_id=provider_trace_id,
            provider_task_id=provider_task_id,
            billing_mode="provider_reconcile",
            billing_attempt_count=0,
            billing_next_run_at=now,
            return_created=return_created,
        )
        if parent_id and refresh_parent:
            await self.refresh_parent_usage_log(parent_id)
        return log

    async def _finalize_provider_balance_sync_usage_log(
        self,
        log: UsageLog,
        *,
        task,
        provider_code: str,
        provider_request_id: str | None = None,
        provider_trace_id: str | None = None,
        provider_task_id: str | None = None,
    ) -> UsageLog:
        if log.status != "pending" or not is_provider_balance_sync_enabled():
            await self._refresh_generation_parent_log(log, task)
            return log

        params = dict(log.params or {})
        params.update({
            "provider_code": provider_code,
            "manual_review_required": False,
            "generation_task": self._generation_task_usage_params(task),
        })
        elapsed_ms = self._generation_elapsed_ms(task)
        update_data: dict[str, Any] = {
            "amount_cents": 0,
            "amount_cents_original": 0,
            "status": "success",
            "params": params,
            "elapsed_ms": elapsed_ms,
            "provider_code": provider_code,
            "provider_request_id": provider_request_id,
            "provider_trace_id": provider_trace_id,
            "provider_task_id": provider_task_id,
            "billing_mode": "provider_balance_sync",
            "billing_locked_until": None,
            "billing_lock_token": None,
            "billing_finalized_at": datetime.now(UTC),
        }
        updated = await self.usage_repo.update(log, update_data)
        await self._refresh_generation_parent_log(updated, task)
        return updated

    async def finalize_lingyaai_generation_billing(self, task, provider=None) -> UsageLog | None:
        """Finalize LingyaAI generation billing for completed tasks."""
        existing = await self.usage_repo.get_by_task_id(task.id)
        if existing:
            if getattr(task, "builtin_provider_code", None) != "lingyaai":
                await self._refresh_generation_parent_log(existing, task)
                return existing
            video_task_id = None
            if task.task_type in {"text2video", "image2video"}:
                video_task_id = getattr(task, "external_task_id", None)
            return await self._finalize_provider_balance_sync_usage_log(
                existing,
                task=task,
                provider_code="lingyaai",
                provider_request_id=getattr(task, "provider_request_id", None),
                provider_trace_id=getattr(task, "provider_trace_id", None),
                provider_task_id=video_task_id,
            )

        if getattr(task, "builtin_provider_code", None) != "lingyaai":
            return None

        oneapi_request_id = getattr(task, "provider_request_id", None)
        request_id = getattr(task, "provider_trace_id", None)
        parent_id = self._generation_parent_usage_log_id(task)
        video_task_id = None
        if task.task_type in {"text2video", "image2video"}:
            video_task_id = getattr(task, "external_task_id", None)
        elapsed_ms = self._generation_elapsed_ms(task)
        log = await self.create_provider_reconcile_usage_log(
            user_id=task.user_id,
            task_id=task.id,
            model_name=task.model_name,
            task_type=task.task_type,
            provider_code="lingyaai",
            provider_request_id=oneapi_request_id,
            provider_trace_id=request_id,
            provider_task_id=video_task_id,
            parent_id=parent_id,
            params={
                "generation_task": self._generation_task_usage_params(task),
            },
            billing_label=self._generation_billing_label(task),
            elapsed_ms=elapsed_ms,
        )
        return log

    async def settle_provider_reconcile_usage_log(
        self,
        log: UsageLog,
        bill,
        *,
        lock_token: str | None = None,
    ) -> UsageLog:
        current = await self.usage_repo.get(log.id)
        if not current or current.status != "pending":
            return current or log
        if lock_token and current.billing_lock_token != lock_token:
            return current

        now = datetime.now(UTC)
        params = dict(current.params or {})
        params.update({
            "provider_bill": {
                "oneapi_request_id": bill.oneapi_request_id,
                "request_id": bill.request_id,
                "quota": bill.quota,
                "prompt_tokens": bill.prompt_tokens,
                "completion_tokens": bill.completion_tokens,
                "billing_unit_per_yuan": bill.billing_unit_per_yuan,
                "amount_cents": bill.amount_cents,
                "raw": bill.raw,
            }
        })

        target_user_id = current.user_id
        if settings.DEPLOY_TYPE == "private":
            target_user_id = await self._get_admin_id()

        result = await self.db.execute(
            update(User)
            .where(User.id == target_user_id, User.balance_cents >= bill.amount_cents)
            .values(balance_cents=User.balance_cents - bill.amount_cents)
        )
        if result.rowcount <= 0:
            user = await self.db.get(User, target_user_id)
            balance_cents = int(getattr(user, "balance_cents", 0) or 0) if user else 0
            for key, value in {
                "amount_cents": 0,
                "amount_cents_original": 0,
                "status": "blocked",
                "params": sanitize_persistent_payload(params | {
                    "manual_review_required": True,
                    "manual_review_reason": "insufficient_balance_after_provider_success",
                    "insufficient_balance_after_provider_success": True,
                    "balance_cents_at_finalize": balance_cents,
                    "amount_cents_due": bill.amount_cents,
                }),
                "billing_locked_until": None,
                "billing_lock_token": None,
                "billing_finalized_at": now,
                "provider_quota": bill.quota,
                "provider_prompt_tokens": bill.prompt_tokens,
                "provider_completion_tokens": bill.completion_tokens,
            }.items():
                setattr(current, key, value)
            await self.db.commit()
            await self.db.refresh(current)
            await self._refresh_generation_parent_log(current, current)
            return current

        for key, value in {
            "amount_cents": bill.amount_cents,
            "amount_cents_original": bill.amount_cents,
            "status": "success",
            "params": sanitize_persistent_payload(params),
            "billing_locked_until": None,
            "billing_lock_token": None,
            "billing_finalized_at": now,
            "provider_quota": bill.quota,
            "provider_prompt_tokens": bill.prompt_tokens,
            "provider_completion_tokens": bill.completion_tokens,
        }.items():
            setattr(current, key, value)
        await self.db.commit()
        await self.db.refresh(current)
        await self._refresh_generation_parent_log(current, current)
        return current

    async def apply_provider_reconcile_plan(self, plan, *, lock_token: str | None = None) -> None:
        log_ids = [
            *(decision.log_id for decision in getattr(plan, "settles", [])),
            *(decision.log_id for decision in getattr(plan, "retries", [])),
            *(decision.log_id for decision in getattr(plan, "blocks", [])),
        ]
        if not log_ids:
            return

        result = await self.db.execute(
            select(UsageLog).where(UsageLog.id.in_(log_ids))
        )
        current_by_id = {log.id: log for log in result.scalars().all()}
        affected_parent_ids: set[int] = set()

        for decision in getattr(plan, "retries", []):
            current = current_by_id.get(decision.log_id)
            if not current or current.status != "pending":
                continue
            if lock_token and current.billing_lock_token != lock_token:
                continue
            current.billing_attempt_count = int(current.billing_attempt_count or 0) + 1
            current.billing_next_run_at = decision.next_run_at
            current.billing_locked_until = None
            current.billing_lock_token = None
            if current.parent_id:
                affected_parent_ids.add(current.parent_id)

        for decision in getattr(plan, "blocks", []):
            current = current_by_id.get(decision.log_id)
            if not current or current.status != "pending":
                continue
            if lock_token and current.billing_lock_token != lock_token:
                continue
            params = dict(current.params or {})
            params.update({
                "manual_review_required": True,
                "manual_review_reason": decision.reason,
            })
            current.amount_cents = 0
            current.amount_cents_original = 0
            current.status = "blocked"
            current.params = sanitize_persistent_payload(params)
            current.billing_locked_until = None
            current.billing_lock_token = None
            current.billing_finalized_at = datetime.now(UTC)
            if current.parent_id:
                affected_parent_ids.add(current.parent_id)

        for decision in getattr(plan, "settles", []):
            current = current_by_id.get(decision.log_id)
            if not current or current.status != "pending":
                continue
            if lock_token and current.billing_lock_token != lock_token:
                continue

            bill = decision.bill
            params = dict(current.params or {})
            params.update({
                "provider_bill": {
                    "oneapi_request_id": bill.oneapi_request_id,
                    "request_id": bill.request_id,
                    "quota": bill.quota,
                    "prompt_tokens": bill.prompt_tokens,
                    "completion_tokens": bill.completion_tokens,
                    "billing_unit_per_yuan": bill.billing_unit_per_yuan,
                    "amount_cents": bill.amount_cents,
                    "raw": bill.raw,
                }
            })

            target_user_id = current.user_id
            if settings.DEPLOY_TYPE == "private":
                target_user_id = await self._get_admin_id()

            settle_now = datetime.now(UTC)
            deduct_result = await self.db.execute(
                update(User)
                .where(User.id == target_user_id, User.balance_cents >= bill.amount_cents)
                .values(balance_cents=User.balance_cents - bill.amount_cents)
            )
            if deduct_result.rowcount <= 0:
                user = await self.db.get(User, target_user_id)
                balance_cents = int(getattr(user, "balance_cents", 0) or 0) if user else 0
                current.amount_cents = 0
                current.amount_cents_original = 0
                current.status = "blocked"
                current.params = sanitize_persistent_payload(params | {
                    "manual_review_required": True,
                    "manual_review_reason": "insufficient_balance_after_provider_success",
                    "insufficient_balance_after_provider_success": True,
                    "balance_cents_at_finalize": balance_cents,
                    "amount_cents_due": bill.amount_cents,
                })
            else:
                current.amount_cents = bill.amount_cents
                current.amount_cents_original = bill.amount_cents
                current.status = "success"
                current.params = sanitize_persistent_payload(params)

            current.billing_locked_until = None
            current.billing_lock_token = None
            current.billing_finalized_at = settle_now
            current.provider_quota = bill.quota
            current.provider_prompt_tokens = bill.prompt_tokens
            current.provider_completion_tokens = bill.completion_tokens
            if current.parent_id:
                affected_parent_ids.add(current.parent_id)

        await self.db.commit()

        for parent_id in sorted(affected_parent_ids):
            await self.refresh_parent_usage_log(parent_id)

    async def retry_provider_reconcile_usage_log(
        self,
        log: UsageLog,
        *,
        next_run_at: datetime,
        lock_token: str | None = None,
    ) -> UsageLog | None:
        current = await self.usage_repo.get(log.id)
        if not current or current.status != "pending":
            return current
        if lock_token and current.billing_lock_token != lock_token:
            return current
        return await self.usage_repo.update(
            current,
            {
                "billing_attempt_count": int(current.billing_attempt_count or 0) + 1,
                "billing_next_run_at": next_run_at,
                "billing_locked_until": None,
                "billing_lock_token": None,
            },
        )

    async def block_provider_reconcile_usage_log(
        self,
        log: UsageLog,
        *,
        reason: str,
        lock_token: str | None = None,
    ) -> UsageLog | None:
        current = await self.usage_repo.get(log.id)
        if not current or current.status != "pending":
            return current
        if lock_token and current.billing_lock_token != lock_token:
            return current
        params = dict(current.params or {})
        params.update({
            "manual_review_required": True,
            "manual_review_reason": reason,
        })
        updated = await self.usage_repo.update(
            current,
            {
                "amount_cents": 0,
                "amount_cents_original": 0,
                "status": "blocked",
                "params": sanitize_persistent_payload(params),
                "billing_locked_until": None,
                "billing_lock_token": None,
                "billing_finalized_at": datetime.now(UTC),
            },
        )
        await self._refresh_generation_parent_log(updated, updated)
        return updated

    async def finalize_apimart_generation_billing(self, task) -> UsageLog | None:
        """Finalize builtin Apimart generation billing.

        Project generation endpoints usually pre-deduct and create a pending
        usage log before the task reaches the poller. Harness generation is
        post-paid, so completed tasks may not have a usage log yet.
        """
        task_params = task.params if isinstance(getattr(task, "params", None), dict) else {}
        if getattr(task, "builtin_provider_code", None) == "lingyaai":
            return None

        existing = await self.usage_repo.get_by_task_id(task.id)
        amount_cents = self.calculate_amount(
            task.model_name,
            resolution=task_params.get("resolution") or task_params.get("quality"),
            duration=task_params.get("duration"),
            task_type=task.task_type,
            audio=bool(task_params.get("audio")),
        )
        parent_id = self._generation_parent_usage_log_id(task)
        base_params = {
            "provider_code": "apimart",
            "manual_review_required": False,
            "request_id": getattr(task, "external_task_id", None),
            "external_task_id": getattr(task, "external_task_id", None),
            "generation_task": self._generation_task_usage_params(task),
        }
        elapsed_ms = self._generation_elapsed_ms(task)
        if not existing:
            existing = await self.create_usage_log(
                user_id=task.user_id,
                task_id=task.id,
                model_name=task.model_name,
                task_type=task.task_type,
                amount_cents=0,
                parent_id=parent_id,
                params=base_params,
                task_status="pending",
                billing_label=self._generation_billing_label(task),
                elapsed_ms=elapsed_ms,
                provider_code="apimart",
                provider_task_id=getattr(task, "external_task_id", None),
                billing_mode="local_price",
            )
        if existing.status != "pending":
            await self._refresh_generation_parent_log(existing, task)
            return existing

        claimed, lock_token = await self._claim_usage_log_lock(existing.id, statuses=["pending"])
        if not claimed:
            if not callable(getattr(self.usage_repo, "claim_log_lock", None)):
                claimed = existing
            else:
                refreshed = await self.usage_repo.get_by_task_id(task.id)
                if refreshed:
                    await self._refresh_generation_parent_log(refreshed, task)
                return refreshed or existing

        if is_provider_balance_sync_enabled():
            claimed.amount_cents = 0
            claimed.amount_cents_original = 0
            claimed.status = "success"
            claimed.params = sanitize_persistent_payload(base_params)
            claimed.elapsed_ms = elapsed_ms
            claimed.billing_mode = "provider_balance_sync"
            claimed.billing_locked_until = None
            claimed.billing_lock_token = None
            claimed.billing_finalized_at = datetime.now(UTC)
            if self.db is not None and hasattr(self.db, "commit"):
                await self.db.commit()
            if self.db is not None and hasattr(self.db, "refresh"):
                await self.db.refresh(claimed)
            await self._refresh_generation_parent_log(claimed, task)
            return claimed

        reserved_amount_cents = max(int(claimed.amount_cents_original or claimed.amount_cents or 0), 0)
        if reserved_amount_cents > 0:
            claimed.amount_cents = reserved_amount_cents
            claimed.amount_cents_original = reserved_amount_cents
            claimed.status = "success"
            claimed.params = sanitize_persistent_payload(base_params)
            claimed.elapsed_ms = elapsed_ms
            claimed.billing_mode = getattr(claimed, "billing_mode", None) or "local_price"
            claimed.billing_locked_until = None
            claimed.billing_lock_token = None
            claimed.billing_finalized_at = datetime.now(UTC)
            if self.db is not None and hasattr(self.db, "commit"):
                await self.db.commit()
            if self.db is not None and hasattr(self.db, "refresh"):
                await self.db.refresh(claimed)
            await self._refresh_generation_parent_log(claimed, task)
            return claimed

        if amount_cents <= 0:
            claimed.amount_cents = 0
            claimed.amount_cents_original = 0
            claimed.status = "blocked"
            claimed.params = sanitize_persistent_payload(base_params | {
                "manual_review_required": True,
                "manual_review_reason": "apimart_missing_local_price",
            })
            claimed.elapsed_ms = elapsed_ms
            claimed.billing_locked_until = None
            claimed.billing_lock_token = None
            claimed.billing_finalized_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(claimed)
            await self._refresh_generation_parent_log(claimed, task)
            return claimed

        balance_cents = int((await self.get_balance(task.user_id)) or 0)
        if self.db is None or not hasattr(self.db, "execute"):
            deduct_ok = await self.deduct_balance(task.user_id, amount_cents)
        else:
            # Mirror deduct_balance's private-deploy remap: get_balance above already reads
            # the admin pool, so the inline debit must hit the same account or the balance
            # check and the deduction would target two different users.
            target_user_id = await self._effective_balance_user_id(task.user_id)
            deduct_result = await self.db.execute(
                update(User)
                .where(User.id == target_user_id, User.balance_cents >= amount_cents)
                .values(balance_cents=User.balance_cents - amount_cents)
            )
            deduct_ok = deduct_result.rowcount > 0
        if not deduct_ok:
            claimed.amount_cents = 0
            claimed.amount_cents_original = 0
            claimed.status = "blocked"
            claimed.params = sanitize_persistent_payload(base_params | {
                "manual_review_required": True,
                "manual_review_reason": "insufficient_balance_after_provider_success",
                "insufficient_balance_after_provider_success": True,
                "balance_cents_at_finalize": balance_cents,
                "amount_cents_due": amount_cents,
            })
        else:
            claimed.amount_cents = amount_cents
            claimed.amount_cents_original = amount_cents
            claimed.status = "success"
            claimed.params = sanitize_persistent_payload(base_params)
        claimed.elapsed_ms = elapsed_ms
        claimed.billing_locked_until = None
        claimed.billing_lock_token = None
        claimed.billing_finalized_at = datetime.now(UTC)
        if self.db is not None and hasattr(self.db, "commit"):
            await self.db.commit()
        if self.db is not None and hasattr(self.db, "refresh"):
            await self.db.refresh(claimed)
        await self._refresh_generation_parent_log(claimed, task)
        return claimed

    async def finalize_ollama_generation_billing(self, task) -> UsageLog | None:
        """Record a zero-cost usage log for local Ollama image generation."""
        if getattr(task, "provider_code", None) != "ollama":
            return None
        if getattr(task, "task_type", None) not in self._IMAGE_GENERATION_TASK_TYPES:
            return None
        if getattr(task, "status", None) not in {"completed", "failed"}:
            return None

        existing = await self.usage_repo.get_by_task_id(task.id)
        if existing:
            await self._refresh_generation_parent_log(existing, task)
            return existing

        task_status = "success" if getattr(task, "status", None) == "completed" else "failed"
        log = await self.create_usage_log(
            user_id=task.user_id,
            task_id=task.id,
            model_name=task.model_name,
            model_label=get_provider_model_label("ollama", "text2image", task.model_name),
            task_type=task.task_type,
            amount_cents=0,
            parent_id=self._generation_parent_usage_log_id(task),
            params={
                "provider_code": "ollama",
                "manual_review_required": False,
                "request_id": getattr(task, "external_task_id", None),
                "external_task_id": getattr(task, "external_task_id", None),
                "generation_task": self._generation_task_usage_params(task),
            },
            task_status=task_status,
            billing_label=self._generation_billing_label(task),
            elapsed_ms=self._generation_elapsed_ms(task),
            provider_code="ollama",
            provider_task_id=getattr(task, "external_task_id", None),
            billing_mode="local_price",
            billing_finalized_at=datetime.now(UTC),
        )
        await self._refresh_generation_parent_log(log, task)
        return log

    @staticmethod
    def _generation_billing_label(task) -> str:
        return (
            "billing.labels.video_generate"
            if task.task_type in {"text2video", "image2video"}
            else "billing.labels.image_generate"
        )

    @staticmethod
    def _generation_parent_usage_log_id(task) -> int | None:
        task_params = task.params if isinstance(getattr(task, "params", None), dict) else {}
        raw_parent_id = task_params.get("parent_usage_log_id")
        try:
            return int(raw_parent_id) if raw_parent_id else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _generation_task_usage_params(task) -> dict[str, Any]:
        task_params = task.params if isinstance(getattr(task, "params", None), dict) else {}
        return {
            "task_id": task.id,
            "request_id": getattr(task, "external_task_id", None),
            "external_task_id": getattr(task, "external_task_id", None),
            "provider_request_id": getattr(task, "provider_request_id", None),
            "provider_trace_id": getattr(task, "provider_trace_id", None),
            "task_type": task.task_type,
            "status": task.status,
            "result_url": task.result_url,
            "artifact_ref": getattr(task, "artifact_ref", None) or task_params.get("artifact_ref"),
            "conversation_id": task_params.get("agent_conversation_id") or task_params.get("conversation_id"),
            "agent_run_id": task_params.get("agent_run_id"),
            "tool_call_id": task_params.get("tool_call_id"),
        }

    @staticmethod
    def _generation_elapsed_ms(task) -> int | None:
        started_at = normalize_app_datetime(getattr(task, "created_at", None))
        finished_at = (
            normalize_app_datetime(getattr(task, "terminalized_at", None))
            or normalize_app_datetime(getattr(task, "updated_at", None))
        )
        if started_at is None or finished_at is None:
            return None
        return max(int((finished_at - started_at).total_seconds() * 1000), 0)

    async def _refresh_generation_parent_log(self, log: UsageLog | None, task) -> None:
        parent_id = getattr(log, "parent_id", None) or self._generation_parent_usage_log_id(task)
        if not parent_id:
            return
        finished_at = normalize_app_datetime(getattr(task, "updated_at", None)) or datetime.now(UTC)
        await self.refresh_parent_usage_log(parent_id, finished_at=finished_at)

    async def get_usage_logs(
        self,
        user_id: int | None = None,
        task_type: str | None = None,
        billing_label: str | None = None,
        model_name: str | None = None,
        log_status: str | None = None,
        task_id: int | None = None,
        parent_id: int | None = None,
        top_level_only: bool = True,
        page: int = 1,
        page_size: int = 10,
        include_params: bool = True,
    ) -> tuple[list[dict], int]:
        await self._recover_completed_provider_balance_sync_generation_logs(user_id=user_id)
        return await self.usage_repo.get_paginated(
            user_id=user_id,
            task_type=task_type,
            billing_label=billing_label,
            model_name=model_name,
            status=log_status,
            task_id=task_id,
            parent_id=parent_id,
            top_level_only=top_level_only,
            page=page,
            page_size=page_size,
            include_params=include_params,
        )

    async def _recover_completed_provider_balance_sync_generation_logs(
        self,
        *,
        user_id: int | None,
        limit: int = 50,
    ) -> int:
        if not is_provider_balance_sync_enabled():
            return 0
        list_logs = getattr(self.usage_repo, "list_completed_provider_balance_sync_generation_logs", None)
        if not callable(list_logs):
            return 0
        rows = await list_logs(provider_code="lingyaai", user_id=user_id, limit=limit)
        recovered = 0
        for log, task in rows:
            await self._finalize_provider_balance_sync_usage_log(
                log,
                task=task,
                provider_code="lingyaai",
                provider_request_id=getattr(task, "provider_request_id", None),
                provider_trace_id=getattr(task, "provider_trace_id", None),
                provider_task_id=(
                    getattr(task, "external_task_id", None)
                    if getattr(task, "task_type", None) in {"text2video", "image2video"}
                    else None
                ),
            )
            recovered += 1
        return recovered

    async def get_usage_log_children(
        self,
        parent_id: int,
        *,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        return await self.usage_repo.get_paginated(
            user_id=user_id,
            parent_id=parent_id,
            top_level_only=False,
            page=page,
            page_size=page_size,
        )

    async def get_usage_log_summary(self, log_id: int) -> dict | None:
        log = await self.usage_repo.get(log_id)
        if not log:
            return None

        params = log.params if isinstance(log.params, dict) else {}
        billing_summary = params.get("billing_summary")
        if not isinstance(billing_summary, dict):
            billing_summary = None

        return {
            "id": log.id,
            "engine": params.get("engine") if isinstance(params.get("engine"), str) else None,
            "conversation_id": params.get("conversation_id") if isinstance(params.get("conversation_id"), str) else None,
            "agent_run_id": params.get("agent_run_id") if isinstance(params.get("agent_run_id"), str) else None,
            "billing_summary": billing_summary,
        }

    async def refresh_parent_usage_log(
        self,
        log_id: int,
        *,
        finished_at: datetime | None = None,
        params: dict | None = None,
        status_override: str | None = None,
        fallback_amount_cents: int | None = None,
        billing_label: str | None = None,
        elapsed_ms: int | None = None,
    ) -> UsageLog | None:
        log = await self.usage_repo.get(log_id)
        if not log:
            return None

        children = await self.usage_repo.get_children(log_id)
        successful_children = [child for child in children if child.status == "success"]
        active_children = [child for child in children if child.status == "pending"]

        child_amount_cents = sum(max(int(child.amount_cents or 0), 0) for child in successful_children)
        fallback_amount_cents = max(int(fallback_amount_cents or 0), 0)
        amount_cents = max(child_amount_cents, fallback_amount_cents) if children else fallback_amount_cents
        if finished_at is None:
            finished_at = datetime.now(UTC)
        finished_at = normalize_app_datetime(finished_at)

        started_at = None
        if isinstance(log.params, dict):
            started_at_raw = log.params.get("agent_started_at")
            if started_at_raw:
                try:
                    started_at = datetime.fromisoformat(started_at_raw)
                except ValueError:
                    started_at = None
        if started_at is None:
            started_at = log.created_at
        started_at = normalize_app_datetime(started_at)

        merged_params = dict(log.params or {})
        if params:
            merged_params.update(params)
        merged_params = self._refresh_agent_billing_summary_from_children(merged_params, children)

        if log.status == "cancelled" or status_override == "cancelled":
            next_status = "cancelled"
        elif active_children:
            next_status = "pending"
        elif status_override:
            next_status = status_override
        else:
            next_status = "success"

        if elapsed_ms is not None:
            next_elapsed_ms = max(int(elapsed_ms), 0)
        else:
            agent_elapsed_ms = self._agent_parent_elapsed_ms(merged_params)
            next_elapsed_ms = (
                agent_elapsed_ms
                if agent_elapsed_ms is not None
                else max(int((finished_at - started_at).total_seconds() * 1000), 0)
            )
        update_data = {
            "amount_cents": amount_cents,
            "amount_cents_original": amount_cents,
            "elapsed_ms": next_elapsed_ms,
            "status": next_status,
            "params": sanitize_persistent_payload(merged_params),
        }
        if billing_label is not None:
            update_data["billing_label"] = billing_label

        updated_log = await self.usage_repo.update(
            log,
            update_data,
        )

        if updated_log.parent_id:
            await self.refresh_parent_usage_log(updated_log.parent_id, finished_at=finished_at)

        return updated_log

    @staticmethod
    def get_pricing_rules() -> dict:
        return PRICING_RULES

    @staticmethod
    def calculate_amount(
        model_name: str,
        resolution: str | None = None,
        duration: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        task_type: str | None = None,
        audio: bool | None = None,
    ) -> int:
        return calculate_amount_cents(
            model_name,
            resolution,
            duration,
            input_tokens,
            output_tokens,
            task_type,
            audio,
        )
