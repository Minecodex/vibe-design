from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.generation_service import GenerationService

LINGYAAI_IMAGE_SUBMIT_STAGE = "lingyaai_image_submit"
OLLAMA_IMAGE_SUBMIT_STAGE = "ollama_image_submit"

GenerationServiceFactory = Callable[[Any], GenerationService]


class GenerationTaskExecutor:
    """Executes one claimed Generation Task workflow step."""

    def __init__(
        self,
        db: Any,
        *,
        generation_service_factory: GenerationServiceFactory = GenerationService,
    ) -> None:
        self.db = db
        self._generation_service_factory = generation_service_factory

    async def execute_once(
        self,
        *,
        task_id: int,
        user_id: int,
        scheduler_claim_token: str,
    ):
        generation_service = self._generation_service_factory(self.db)
        task = await generation_service.task_repo.get_by_id_and_user(task_id, user_id)
        if task is None or getattr(task, "status", None) in {"completed", "failed"}:
            return task

        if self._is_lingyaai_image_submit_task(task):
            await generation_service.complete_lingyaai_image_task(
                task_id=task_id,
                user_id=user_id,
                scheduler_claim_token=scheduler_claim_token,
            )
            refreshed = await generation_service.task_repo.get_by_id_and_user(task_id, user_id)
            return refreshed or task

        if self._is_ollama_image_submit_task(task):
            await generation_service.complete_ollama_image_task(
                task_id=task_id,
                user_id=user_id,
                scheduler_claim_token=scheduler_claim_token,
            )
            refreshed = await generation_service.task_repo.get_by_id_and_user(task_id, user_id)
            return refreshed or task

        return await generation_service.query_task_status(
            task_id,
            user_id,
            scheduler_claim_token=scheduler_claim_token,
        )

    @staticmethod
    def _is_lingyaai_image_submit_task(task: Any) -> bool:
        if not GenerationService._is_lingyaai_pending_image_task(task):
            return False
        workflow_stage = str(getattr(task, "workflow_stage", "") or "").strip()
        return workflow_stage in {"", LINGYAAI_IMAGE_SUBMIT_STAGE, "provider_query"}

    @staticmethod
    def _is_ollama_image_submit_task(task: Any) -> bool:
        if not GenerationService._is_ollama_pending_image_task(task):
            return False
        workflow_stage = str(getattr(task, "workflow_stage", "") or "").strip()
        return workflow_stage in {"", OLLAMA_IMAGE_SUBMIT_STAGE, "provider_query"}
