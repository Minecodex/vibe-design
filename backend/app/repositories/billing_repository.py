import logging
from datetime import datetime

from sqlalchemy import and_, desc, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.models.billing import UsageLog
from app.models.generation import GenerationTask
from app.models.user import User
from app.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)

_USAGE_LOG_COPY_FIELDS = (
    "user_id",
    "parent_id",
    "task_id",
    "model_name",
    "model_label",
    "task_type",
    "billing_key",
    "amount_cents",
    "amount_cents_original",
    "billing_label",
    "elapsed_ms",
    "status",
    "provider_code",
    "provider_request_id",
    "provider_trace_id",
    "provider_task_id",
    "billing_mode",
    "billing_attempt_count",
    "billing_next_run_at",
    "billing_locked_until",
    "billing_lock_token",
    "billing_finalized_at",
    "provider_quota",
    "provider_prompt_tokens",
    "provider_completion_tokens",
    "params",
)


def _is_duplicate_primary_key_error(exc: IntegrityError) -> bool:
    text_value = " ".join(str(part) for part in getattr(exc.orig, "args", ()) if part is not None)
    if not text_value:
        text_value = str(exc.orig or exc)
    return "Duplicate entry" in text_value and (
        "usage_logs.PRIMARY" in text_value
        or "for key 'PRIMARY'" in text_value
        or 'for key "PRIMARY"' in text_value
    )


def _copy_usage_log_without_id(log: UsageLog) -> UsageLog:
    return UsageLog(**{field: getattr(log, field) for field in _USAGE_LOG_COPY_FIELDS})


class UsageLogRepository(BaseRepository[UsageLog]):
    def __init__(self, db: AsyncSession):
        super().__init__(UsageLog, db)

    async def create(self, obj: UsageLog) -> UsageLog:
        if isinstance(getattr(obj, "params", None), dict):
            obj.params = sanitize_persistent_payload(obj.params)
        return await super().create(obj)

    async def update(self, obj: UsageLog, data: dict) -> UsageLog:
        if "params" in data:
            data = {**data, "params": sanitize_persistent_payload(data.get("params"))}
        return await super().update(obj, data)

    async def get_by_task_id(self, task_id: int) -> UsageLog | None:
        result = await self.db.execute(
            select(UsageLog).where(UsageLog.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_billing_key(self, billing_key: str) -> UsageLog | None:
        result = await self.db.execute(
            select(UsageLog).where(UsageLog.billing_key == billing_key)
        )
        return result.scalar_one_or_none()

    async def create_or_get_by_task_id(self, log: UsageLog) -> UsageLog:
        if log.task_id is None:
            try:
                return await self.create(log)
            except IntegrityError as exc:
                await self.db.rollback()
                if not _is_duplicate_primary_key_error(exc):
                    raise
                return await self._retry_create_after_primary_key_collision(log)
        try:
            return await self.create(log)
        except IntegrityError as exc:
            await self.db.rollback()
            existing = await self.get_by_task_id(int(log.task_id))
            if existing is None:
                if not _is_duplicate_primary_key_error(exc):
                    raise
                try:
                    return await self._retry_create_after_primary_key_collision(log)
                except IntegrityError:
                    existing = await self.get_by_task_id(int(log.task_id))
                    if existing is None:
                        raise
                    return existing
            return existing

    async def create_or_get_by_billing_key(self, log: UsageLog) -> UsageLog:
        existing, _created = await self.create_or_get_by_billing_key_with_created(log)
        return existing

    async def create_or_get_by_billing_key_with_created(self, log: UsageLog) -> tuple[UsageLog, bool]:
        billing_key = str(log.billing_key or "").strip()
        if not billing_key:
            return await self.create(log), True
        try:
            return await self.create(log), True
        except IntegrityError as exc:
            await self.db.rollback()
            existing = await self.get_by_billing_key(billing_key)
            if existing is None:
                if not _is_duplicate_primary_key_error(exc):
                    raise
                try:
                    retry_log = await self._retry_create_after_primary_key_collision(log)
                except IntegrityError:
                    existing = await self.get_by_billing_key(billing_key)
                    if existing is None:
                        raise
                    return existing, False
                return retry_log, True
            return existing, False

    async def _retry_create_after_primary_key_collision(self, log: UsageLog) -> UsageLog:
        await self._repair_mysql_auto_increment()
        retry_log = _copy_usage_log_without_id(log)
        try:
            return await self.create(retry_log)
        except IntegrityError:
            await self.db.rollback()
            raise

    async def _repair_mysql_auto_increment(self) -> None:
        bind = self.db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect_name not in {"mysql", "mariadb"}:
            return
        next_id = await self.db.scalar(select(func.coalesce(func.max(UsageLog.id), 0) + 1))
        next_id = max(int(next_id or 1), 1)
        await self.db.execute(text(f"ALTER TABLE usage_logs AUTO_INCREMENT = {next_id}"))
        await self.db.commit()
        logger.warning("Repaired usage_logs AUTO_INCREMENT after PRIMARY key collision: next_id=%s", next_id)

    async def get_children(self, parent_id: int) -> list[UsageLog]:
        result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.parent_id == parent_id)
            .order_by(UsageLog.created_at.asc(), UsageLog.id.asc())
        )
        return list(result.scalars().all())

    async def get_latest_agent_log_by_run_id(self, agent_run_id: str) -> UsageLog | None:
        result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.model_name == "agent")
            .order_by(desc(UsageLog.id))
            .limit(200)
        )
        for log in result.scalars().all():
            params = log.params or {}
            if isinstance(params, dict) and params.get("agent_run_id") == agent_run_id:
                return log
        return None

    async def get_paginated(
        self,
        user_id: int | None = None,
        task_type: str | None = None,
        billing_label: str | None = None,
        model_name: str | None = None,
        status: str | None = None,
        task_id: int | None = None,
        parent_id: int | None = None,
        top_level_only: bool = False,
        page: int = 1,
        page_size: int = 10,
        include_params: bool = True,
    ) -> tuple[list[dict], int]:
        conditions = []
        if user_id is not None:
            conditions.append(UsageLog.user_id == user_id)
        if task_type:
            conditions.append(UsageLog.task_type == task_type)
        if billing_label:
            conditions.append(UsageLog.billing_label == billing_label)
        if model_name:
            conditions.append(UsageLog.model_name == model_name)
        if status:
            conditions.append(UsageLog.status == status)
        if task_id is not None:
            conditions.append(UsageLog.task_id == task_id)
        if parent_id is not None:
            conditions.append(UsageLog.parent_id == parent_id)
        if top_level_only:
            conditions.append(UsageLog.parent_id.is_(None))

        where_clause = and_(*conditions) if conditions else True

        count_result = await self.db.execute(
            select(func.count()).select_from(UsageLog).where(where_clause)
        )
        total = count_result.scalar_one()

        stmt = (
            select(
                UsageLog,
                User.nickname,
                User.avatar_url
            )
            .outerjoin(User, UsageLog.user_id == User.id)
            .where(where_clause)
            .order_by(UsageLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(stmt)
        items = []
        for row in result.all():
            log_obj = row[0]
            nickname = row[1]
            avatar_url = row[2]

            data = {
                **({
                    "kind": (log_obj.params or {}).get("kind"),
                    "subagent_task_id": (log_obj.params or {}).get("subagent_task_id"),
                    "subagent_label": (log_obj.params or {}).get("subagent_label"),
                } if isinstance(log_obj.params, dict) else {}),
                "id": log_obj.id,
                "user_id": log_obj.user_id,
                "parent_id": log_obj.parent_id,
                "task_id": log_obj.task_id,
                "model_name": log_obj.model_name,
                "model_label": log_obj.model_label,
                "task_type": log_obj.task_type,
                "billing_key": log_obj.billing_key,
                "amount_cents": log_obj.amount_cents,
                "amount_cents_original": log_obj.amount_cents_original,
                "billing_label": log_obj.billing_label,
                "elapsed_ms": log_obj.elapsed_ms,
                "status": log_obj.status,
                "provider_code": log_obj.provider_code,
                "provider_request_id": log_obj.provider_request_id,
                "provider_trace_id": log_obj.provider_trace_id,
                "provider_task_id": log_obj.provider_task_id,
                "billing_mode": log_obj.billing_mode,
                "billing_attempt_count": log_obj.billing_attempt_count,
                "billing_next_run_at": log_obj.billing_next_run_at,
                "billing_locked_until": log_obj.billing_locked_until,
                "billing_finalized_at": log_obj.billing_finalized_at,
                "provider_quota": log_obj.provider_quota,
                "provider_prompt_tokens": log_obj.provider_prompt_tokens,
                "provider_completion_tokens": log_obj.provider_completion_tokens,
                "created_at": log_obj.created_at,
                "updated_at": log_obj.updated_at,
                "nickname": nickname,
                "avatar_url": avatar_url,
            }
            if include_params:
                data["params"] = log_obj.params
            items.append(data)

        return items, total

    async def list_due_provider_reconcile_logs(
        self,
        *,
        provider_code: str,
        now: datetime,
        limit: int,
    ) -> list[UsageLog]:
        result = await self.db.execute(
            select(UsageLog)
            .where(
                UsageLog.provider_code == provider_code,
                UsageLog.billing_mode == "provider_reconcile",
                UsageLog.status == "pending",
                UsageLog.billing_next_run_at.is_not(None),
                UsageLog.billing_next_run_at <= now,
                or_(UsageLog.billing_locked_until.is_(None), UsageLog.billing_locked_until <= now),
            )
            .order_by(UsageLog.billing_next_run_at.asc(), UsageLog.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_completed_provider_balance_sync_generation_logs(
        self,
        *,
        provider_code: str,
        user_id: int | None = None,
        limit: int = 50,
    ) -> list[tuple[UsageLog, GenerationTask]]:
        conditions = [
            UsageLog.provider_code == provider_code,
            UsageLog.billing_mode == "provider_balance_sync",
            UsageLog.status == "pending",
            UsageLog.task_id.is_not(None),
            GenerationTask.id == UsageLog.task_id,
            GenerationTask.provider_code == "builtin",
            GenerationTask.builtin_provider_code == provider_code,
            GenerationTask.status == "completed",
        ]
        if user_id is not None:
            conditions.append(UsageLog.user_id == user_id)

        result = await self.db.execute(
            select(UsageLog, GenerationTask)
            .join(GenerationTask, GenerationTask.id == UsageLog.task_id)
            .where(and_(*conditions))
            .order_by(UsageLog.id.asc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def claim_provider_reconcile_logs(
        self,
        *,
        log_ids: list[int],
        now: datetime,
        locked_until: datetime,
        lock_token: str,
    ) -> list[UsageLog]:
        if not log_ids:
            return []
        await self.db.execute(
            update(UsageLog)
            .where(
                UsageLog.id.in_(log_ids),
                UsageLog.status == "pending",
                UsageLog.billing_mode == "provider_reconcile",
                or_(UsageLog.billing_locked_until.is_(None), UsageLog.billing_locked_until <= now),
            )
            .values(
                billing_locked_until=locked_until,
                billing_lock_token=lock_token,
            )
        )
        await self.db.commit()
        result = await self.db.execute(
            select(UsageLog)
            .where(
                UsageLog.id.in_(log_ids),
                UsageLog.status == "pending",
                UsageLog.billing_lock_token == lock_token,
            )
            .order_by(UsageLog.id.asc())
        )
        return list(result.scalars().all())

    async def claim_log_lock(
        self,
        *,
        log_id: int,
        now: datetime,
        locked_until: datetime,
        lock_token: str,
        statuses: list[str] | None = None,
    ) -> UsageLog | None:
        conditions = [
            UsageLog.id == int(log_id),
            or_(UsageLog.billing_locked_until.is_(None), UsageLog.billing_locked_until <= now),
        ]
        if statuses:
            conditions.append(UsageLog.status.in_([str(status) for status in statuses]))
        await self.db.execute(
            update(UsageLog)
            .where(*conditions)
            .values(
                billing_locked_until=locked_until,
                billing_lock_token=lock_token,
            )
        )
        await self.db.commit()
        result = await self.db.execute(
            select(UsageLog).where(
                UsageLog.id == int(log_id),
                UsageLog.billing_lock_token == lock_token,
            )
        )
        return result.scalar_one_or_none()
