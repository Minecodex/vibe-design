from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.models.generation import GenerationTask
from app.repositories.base_repository import BaseRepository


def _datetime_sort_value(value: datetime | None) -> tuple[int, float]:
    if value is None:
        return (0, 0.0)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (1, value.timestamp())


class GenerationTaskRepository(BaseRepository[GenerationTask]):
    def __init__(self, db: AsyncSession):
        super().__init__(GenerationTask, db)

    async def create(self, obj: GenerationTask) -> GenerationTask:
        if isinstance(getattr(obj, "params", None), dict):
            obj.params = sanitize_persistent_payload(obj.params)
        return await super().create(obj)

    async def update(self, obj: GenerationTask, data: dict) -> GenerationTask:
        if "params" in data:
            data = {**data, "params": sanitize_persistent_payload(data.get("params"))}
        return await super().update(obj, data)

    async def get_by_project(self, project_id: int, user_id: int) -> list[GenerationTask]:
        result = await self.db.execute(
            select(GenerationTask)
            .where(
                and_(
                    GenerationTask.project_id == project_id,
                    GenerationTask.user_id == user_id,
                )
            )
            .order_by(GenerationTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_incomplete_tasks(self) -> list[GenerationTask]:
        """Return all tasks still pending or processing (for startup recovery)."""
        result = await self.db.execute(
            select(GenerationTask)
            .where(GenerationTask.status.in_(["pending", "processing"]))
            .order_by(GenerationTask.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_terminal_tasks_pending_side_effects(
        self,
        *,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[GenerationTask]:
        result = await self.db.execute(
            select(GenerationTask)
            .where(
                GenerationTask.id > int(after_id or 0),
                GenerationTask.status.in_(["completed", "failed"]),
                GenerationTask.terminal_side_effects_finalized_at.is_(None),
            )
            .order_by(GenerationTask.id.asc())
            .limit(max(1, int(limit or 1)))
        )
        return list(result.scalars().all())

    async def list_due_scheduler_tasks(
        self,
        *,
        now: datetime,
        limit: int = 10,
    ) -> list[GenerationTask]:
        task_ids = await self.list_due_scheduler_task_ids(now=now, limit=limit)
        if not task_ids:
            return []

        result = await self.db.execute(
            select(GenerationTask).where(GenerationTask.id.in_(task_ids))
        )
        tasks_by_id = {int(task.id): task for task in result.scalars().all()}
        return [tasks_by_id[task_id] for task_id in task_ids if task_id in tasks_by_id]

    def build_due_scheduler_task_ids_stmt(
        self,
        *,
        status: str,
        now: datetime,
        limit: int = 10,
    ):
        """Build the due scheduler scan without large Text/JSON payload columns."""
        normalized_limit = max(1, int(limit or 1))
        return (
            select(
                GenerationTask.id,
                GenerationTask.scheduler_next_run_at,
                GenerationTask.created_at,
            )
            .where(
                GenerationTask.status == str(status),
                or_(
                    GenerationTask.workflow_stage.is_(None),
                    GenerationTask.workflow_stage != "provider_operation",
                ),
                or_(
                    GenerationTask.scheduler_next_run_at.is_(None),
                    GenerationTask.scheduler_next_run_at <= now,
                ),
                or_(
                    GenerationTask.scheduler_lease_expires_at.is_(None),
                    GenerationTask.scheduler_lease_expires_at <= now,
                ),
            )
            .order_by(
                GenerationTask.scheduler_next_run_at.asc(),
                GenerationTask.created_at.asc(),
                GenerationTask.id.asc(),
            )
            .limit(normalized_limit)
        )

    async def list_due_scheduler_task_ids(
        self,
        *,
        now: datetime,
        limit: int = 10,
    ) -> list[int]:
        normalized_limit = max(1, int(limit or 1))
        rows = []
        for status in ("pending", "processing"):
            result = await self.db.execute(
                self.build_due_scheduler_task_ids_stmt(
                    status=status,
                    now=now,
                    limit=normalized_limit,
                )
            )
            rows.extend(result.mappings().all())

        rows.sort(
            key=lambda row: (
                _datetime_sort_value(row["scheduler_next_run_at"]),
                _datetime_sort_value(row["created_at"]),
                int(row["id"]),
            )
        )
        return [int(row["id"]) for row in rows[:normalized_limit]]

    async def claim_scheduler_task(
        self,
        *,
        task_id: int,
        now: datetime,
        lease_expires_at: datetime,
        claim_token: str,
    ) -> GenerationTask | None:
        result = await self.db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == int(task_id),
                GenerationTask.status.in_(["pending", "processing"]),
                or_(
                    GenerationTask.scheduler_lease_expires_at.is_(None),
                    GenerationTask.scheduler_lease_expires_at <= now,
                ),
            )
            .values(
                scheduler_claim_token=claim_token,
                scheduler_claimed_at=now,
                scheduler_lease_expires_at=lease_expires_at,
                scheduler_attempt_count=GenerationTask.scheduler_attempt_count + 1,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        result = await self.db.execute(
            select(GenerationTask).where(
                GenerationTask.id == int(task_id),
                GenerationTask.scheduler_claim_token == claim_token,
            ).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def renew_scheduler_task_claim(
        self,
        *,
        task_id: int,
        now: datetime,
        lease_expires_at: datetime,
        claim_token: str,
    ) -> GenerationTask | None:
        result = await self.db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == int(task_id),
                GenerationTask.scheduler_claim_token == claim_token,
                GenerationTask.status.in_(["pending", "processing"]),
            )
            .values(
                scheduler_lease_expires_at=lease_expires_at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        result = await self.db.execute(
            select(GenerationTask).where(
                GenerationTask.id == int(task_id),
                GenerationTask.scheduler_claim_token == claim_token,
            ).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def update_for_scheduler_claim(
        self,
        *,
        task_id: int,
        user_id: int,
        claim_token: str,
        data: dict,
    ) -> GenerationTask | None:
        if "params" in data:
            data = {**data, "params": sanitize_persistent_payload(data.get("params"))}
        result = await self.db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == int(task_id),
                GenerationTask.user_id == int(user_id),
                GenerationTask.scheduler_claim_token == claim_token,
                GenerationTask.status.in_(["pending", "processing"]),
            )
            .values(**data)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        if int(result.rowcount or 0) != 1:
            return None
        result = await self.db.execute(
            select(GenerationTask).where(
                GenerationTask.id == int(task_id),
                GenerationTask.user_id == int(user_id),
            ).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def release_scheduler_task_claim(
        self,
        *,
        task_id: int,
        claim_token: str,
    ) -> None:
        await self.db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == int(task_id),
                GenerationTask.scheduler_claim_token == claim_token,
            )
            .values(
                scheduler_claim_token=None,
                scheduler_claimed_at=None,
                scheduler_lease_expires_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def mark_terminal_side_effects_finalized(
        self,
        task_id: int,
        *,
        finalized_at: datetime | None = None,
    ) -> None:
        await self.db.execute(
            update(GenerationTask)
            .where(
                GenerationTask.id == int(task_id),
                GenerationTask.status.in_(["completed", "failed"]),
                GenerationTask.terminal_side_effects_finalized_at.is_(None),
            )
            .values(terminal_side_effects_finalized_at=finalized_at or datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def get_by_id_and_user(
        self, task_id: int, user_id: int
    ) -> GenerationTask | None:
        result = await self.db.execute(
            select(GenerationTask).where(
                and_(
                    GenerationTask.id == task_id,
                    GenerationTask.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_by_artifact_ref(
        self, user_id: int, artifact_ref: str
    ) -> GenerationTask | None:
        result = await self.db.execute(
            select(GenerationTask)
            .where(
                GenerationTask.user_id == user_id,
                GenerationTask.artifact_ref == artifact_ref,
            )
            .order_by(GenerationTask.created_at.desc(), GenerationTask.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_client_request_id(
        self,
        *,
        user_id: int,
        project_id: int | None,
        task_type: str,
        client_request_id: str,
    ) -> GenerationTask | None:
        result = await self.db.execute(
            select(GenerationTask).where(
                and_(
                    GenerationTask.user_id == user_id,
                    GenerationTask.project_id == project_id,
                    GenerationTask.task_type == task_type,
                    GenerationTask.client_request_id == client_request_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_client_request_items(
        self,
        *,
        user_id: int,
        project_id: int,
        items: list[tuple[str, str]],
    ) -> list[GenerationTask]:
        if not items:
            return []

        request_ids = [client_request_id for _, client_request_id in items]
        allowed_keys = {f"{task_type}:{client_request_id}" for task_type, client_request_id in items}

        result = await self.db.execute(
            select(GenerationTask)
            .where(
                and_(
                    GenerationTask.user_id == user_id,
                    GenerationTask.project_id == project_id,
                    GenerationTask.client_request_id.in_(request_ids),
                )
            )
            .order_by(GenerationTask.created_at.desc(), GenerationTask.id.desc())
        )
        tasks = []
        seen_keys: set[str] = set()
        for task in result.scalars().all():
            key = f"{task.task_type}:{task.client_request_id}"
            if key not in allowed_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            tasks.append(task)
        return tasks
