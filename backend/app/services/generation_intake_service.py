from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_errors import raise_insufficient_balance
from app.core.provider_balance_mode import is_provider_balance_sync_enabled
from app.core.providers import (
    build_provider_registry,
    get_active_builtin_provider_code,
    resolve_builtin_model_name_for_provider,
)
from app.models.generation import GenerationTask
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.billing_service import BillingService
from app.services.generation_service import GenerationService
from app.services.task_poller import task_poller


@dataclass(frozen=True)
class GenerationIntakeRequest:
    user_id: int
    project_id: int | None
    prompt: str
    model_name: str
    provider_code: str
    task_type: str = "text2image"
    billing_label: str | None = None
    aspect_ratio: str = "1:1"
    resolution: str | None = "1K"
    duration: int | None = None
    quality: str | None = None
    audio: bool = False
    image_urls: list[str] | None = None
    first_frame_image: str | None = None
    tail_frame_image: str | None = None
    return_last_frame: bool | None = None
    negative_prompt: str | None = None
    watermark: bool | None = None
    multi_shot: bool | None = None
    shot_type: str | None = None
    multi_prompt: list[dict[str, Any]] | None = None
    element_list: list[dict[str, Any]] | None = None
    planned_result_url: str | None = None
    client_request_id: str | None = None
    reserve_billing: bool = True
    metadata_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationIntakeResult:
    task: GenerationTask
    reused_existing: bool
    amount_cents: int = 0


class GenerationIntakeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.task_repo = GenerationTaskRepository(db)
        self.generation_service = GenerationService(db)

    async def submit_image(self, request: GenerationIntakeRequest) -> GenerationIntakeResult:
        task_type = request.task_type or "text2image"
        billing_label = request.billing_label or "billing.labels.image_generate"
        existing = await self._find_existing(request, task_type=task_type)
        if existing is not None:
            await self._resume_processing(existing)
            return GenerationIntakeResult(task=existing, reused_existing=True, amount_cents=0)

        await self._validate_provider_model(request, task_type=task_type)
        resolved_resolution = self.generation_service._clamp_image_resolution_to_model_capability(
            request.provider_code,
            request.model_name,
            request.resolution or "1K",
        )

        amount_cents = 0
        if request.provider_code == "builtin" and request.reserve_billing:
            amount_cents = await self._reserve_builtin_billing(
                user_id=request.user_id,
                model_name=request.model_name,
                task_type=task_type,
                resolution=resolved_resolution,
                duration=None,
                params={"resolution": resolved_resolution, "aspect_ratio": request.aspect_ratio},
            )

        try:
            task = await self.generation_service.generate_image(
                user_id=request.user_id,
                project_id=request.project_id,
                prompt=request.prompt,
                model_name=request.model_name,
                provider_code=request.provider_code,
                aspect_ratio=request.aspect_ratio,
                resolution=resolved_resolution,
                image_urls=request.image_urls,
                planned_result_url=request.planned_result_url,
                client_request_id=request.client_request_id,
                metadata_params=request.metadata_params or None,
            )
        except Exception:
            if amount_cents > 0:
                await BillingService(self.db).refund_balance(request.user_id, amount_cents)
            raise

        await self._finalize_submission(
            request=request,
            task=task,
            amount_cents=amount_cents,
            task_type=task_type,
            params={"resolution": resolved_resolution, "aspect_ratio": request.aspect_ratio},
            billing_label=billing_label,
        )
        return GenerationIntakeResult(task=task, reused_existing=False, amount_cents=amount_cents)

    async def submit_video(self, request: GenerationIntakeRequest) -> GenerationIntakeResult:
        task_type = request.task_type
        existing = await self._find_existing(request, task_type=task_type)
        if existing is not None:
            await self._resume_processing(existing)
            return GenerationIntakeResult(task=existing, reused_existing=True, amount_cents=0)

        await self._validate_provider_model(request, task_type=task_type)

        amount_cents = 0
        if request.provider_code == "builtin" and request.reserve_billing:
            amount_cents = await self._reserve_builtin_billing(
                user_id=request.user_id,
                model_name=request.model_name,
                task_type=task_type,
                resolution=request.resolution,
                duration=request.duration,
                params={
                    "resolution": request.resolution,
                    "duration": request.duration,
                    "aspect_ratio": request.aspect_ratio,
                    "audio": request.audio,
                    "image_urls": request.image_urls,
                    "first_frame_image": request.first_frame_image,
                    "tail_frame_image": request.tail_frame_image,
                },
            )

        try:
            task = await self.generation_service.generate_video(
                user_id=request.user_id,
                project_id=request.project_id,
                prompt=request.prompt,
                model_name=request.model_name,
                provider_code=request.provider_code,
                aspect_ratio=request.aspect_ratio,
                duration=int(request.duration or 5),
                quality=request.quality or request.resolution or "720p",
                resolution=request.resolution,
                audio=request.audio,
                image_urls=request.image_urls,
                first_frame_image=request.first_frame_image,
                tail_frame_image=request.tail_frame_image,
                return_last_frame=request.return_last_frame,
                negative_prompt=request.negative_prompt,
                watermark=request.watermark,
                multi_shot=request.multi_shot,
                shot_type=request.shot_type,
                multi_prompt=request.multi_prompt,
                element_list=request.element_list,
                planned_result_url=request.planned_result_url,
                client_request_id=request.client_request_id,
                metadata_params=request.metadata_params or None,
            )
        except Exception:
            if amount_cents > 0:
                await BillingService(self.db).refund_balance(request.user_id, amount_cents)
            raise

        await self._finalize_submission(
            request=request,
            task=task,
            amount_cents=amount_cents,
            task_type=task_type,
            params={
                "resolution": request.resolution,
                "duration": request.duration,
                "aspect_ratio": request.aspect_ratio,
                "audio": request.audio,
                "image_urls": request.image_urls,
                "first_frame_image": request.first_frame_image,
                "tail_frame_image": request.tail_frame_image,
            },
            billing_label="billing.labels.video_generate",
        )
        return GenerationIntakeResult(task=task, reused_existing=False, amount_cents=amount_cents)

    async def _finalize_submission(
        self,
        *,
        request: GenerationIntakeRequest,
        task: GenerationTask,
        amount_cents: int,
        task_type: str,
        params: dict[str, Any],
        billing_label: str,
    ) -> None:
        try:
            await self._record_builtin_usage_log(
                request=request,
                task=task,
                amount_cents=amount_cents,
                task_type=task_type,
                params=params,
                billing_label=billing_label,
            )
            await self._finalize_completed_lingyaai_billing(task)
            await self._resume_processing(task)
        except Exception:
            if amount_cents > 0:
                await BillingService(self.db).refund_balance(request.user_id, amount_cents)
            raise

    async def _find_existing(self, request: GenerationIntakeRequest, *, task_type: str) -> GenerationTask | None:
        if not request.client_request_id:
            return None
        return await self.task_repo.get_by_client_request_id(
            user_id=request.user_id,
            project_id=request.project_id,
            task_type=task_type,
            client_request_id=request.client_request_id,
        )

    async def _validate_provider_model(self, request: GenerationIntakeRequest, *, task_type: str) -> None:
        provider_code = str(request.provider_code or "").strip()
        if not provider_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的供应商: ",
            )

        registry = build_provider_registry()
        provider = registry.get(provider_code)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的供应商: {provider_code}",
            )

        bucket = self._model_bucket_for_task_type(task_type)
        model_name = str(request.model_name or "").strip()
        if not model_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的模型: {provider_code}/{model_name}",
            )

        model_names = {model_name}
        if provider_code == "builtin":
            model_names.add(resolve_builtin_model_name_for_provider(bucket, model_name))

        registry_models = provider.get("models", {}).get(bucket, [])
        if any(model.get("model_name") in model_names for model in registry_models):
            return

        if provider_code != "builtin":
            user_models = await self.generation_service.model_repo.get_by_user_and_provider(
                request.user_id,
                provider_code,
            )
            if any(getattr(model, "is_enabled", False) and model.model_name == model_name for model in user_models):
                return

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的模型: {provider_code}/{model_name}",
        )

    @staticmethod
    def _model_bucket_for_task_type(task_type: str) -> str:
        if task_type in {"text2video", "image2video"}:
            return "text2video"
        return "text2image"

    async def _reserve_builtin_billing(
        self,
        *,
        user_id: int,
        model_name: str,
        task_type: str,
        resolution: str | None,
        duration: int | None,
        params: dict[str, Any],
    ) -> int:
        billing_svc = BillingService(self.db)
        if get_active_builtin_provider_code() == "lingyaai":
            balance_cents = await billing_svc.get_balance(user_id)
            if balance_cents <= 0:
                raise_insufficient_balance(required_cents=1, balance_cents=balance_cents)
            return 0

        amount_cents = billing_svc.calculate_amount(
            model_name,
            resolution,
            duration,
            task_type=task_type,
            audio=bool(params.get("audio")),
        )
        if amount_cents > 0:
            balance_cents = await billing_svc.get_balance(user_id)
            ok = await billing_svc.deduct_balance(user_id, amount_cents)
            if not ok:
                raise_insufficient_balance(required_cents=amount_cents, balance_cents=balance_cents)
        return amount_cents

    async def _record_builtin_usage_log(
        self,
        *,
        request: GenerationIntakeRequest,
        task: GenerationTask,
        amount_cents: int,
        task_type: str,
        params: dict[str, Any],
        billing_label: str,
    ) -> None:
        if request.provider_code != "builtin":
            return

        builtin_provider_code = str(getattr(task, "builtin_provider_code", "") or "").strip()
        if not builtin_provider_code:
            builtin_provider_code = get_active_builtin_provider_code()
        provider_balance_sync_log = (
            request.reserve_billing
            and builtin_provider_code == "lingyaai"
            and is_provider_balance_sync_enabled()
        )

        if amount_cents <= 0 and not provider_balance_sync_log:
            return
        billing_svc = BillingService(self.db)
        if task.status == "failed":
            if amount_cents > 0:
                await billing_svc.refund_balance(request.user_id, amount_cents)
            return
        await billing_svc.create_usage_log(
            user_id=request.user_id,
            task_id=task.id,
            model_name=request.model_name,
            task_type=task_type,
            amount_cents=amount_cents,
            parent_id=self._generation_parent_usage_log_id(task),
            params=params,
            task_status="pending",
            billing_label=billing_label,
            provider_code=builtin_provider_code,
            billing_mode="provider_balance_sync" if provider_balance_sync_log else "local_price",
        )

    async def _finalize_completed_lingyaai_billing(self, task: GenerationTask) -> None:
        if task.provider_code != "builtin" or task.status != "completed":
            return
        if getattr(task, "builtin_provider_code", None) != "lingyaai":
            return
        await BillingService(self.db).finalize_lingyaai_generation_billing(task)

    @staticmethod
    def _generation_parent_usage_log_id(task: GenerationTask) -> int | None:
        task_params = task.params if isinstance(getattr(task, "params", None), dict) else {}
        raw_parent_id = task_params.get("parent_usage_log_id")
        try:
            return int(raw_parent_id) if raw_parent_id else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def _resume_processing(task: GenerationTask) -> None:
        if task.status != "processing":
            return
        if str(getattr(task, "workflow_stage", "") or "") == "provider_operation":
            return
        if GenerationService._is_lingyaai_pending_image_task(task):
            workflow_stage = "lingyaai_image_submit"
        elif GenerationService._is_ollama_pending_image_task(task):
            workflow_stage = "ollama_image_submit"
        else:
            workflow_stage = "provider_query"
        await task_poller.enqueue_task(task.id, workflow_stage=workflow_stage)
