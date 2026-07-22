"""Unified generation service - dispatches to KlingAI or Jimeng based on provider_code."""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APIMART_IMAGE_SUBMIT_MAX_ATTEMPTS, settings
from app.core.ollama_credentials import get_ollama_image_api_key
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.core.providers import build_provider_registry, resolve_builtin_model_name_for_provider
from app.models.generation import GenerationTask
from app.models.user import User
from app.repositories.generation_repository import GenerationTaskRepository
from app.repositories.provider_operation_repository import ProviderOperationRepository
from app.repositories.provider_repository import (
    ProviderCredentialRepository,
    ProviderModelRepository,
)
from app.services.billing_service import BillingService
from app.services.builtin_provider import (
    BuiltinQueryResult,
    BuiltinSubmitResult,
    get_active_builtin_provider,
    get_builtin_provider,
)
from app.services.generated_uploads import build_generated_upload, resolve_generated_upload_path
from app.services.generation_media_resolver import GenerationMediaResolveError
from app.services.generation_reference_diagnostics import (
    merge_reference_diagnostics,
    summarize_reference_values,
)
from app.services.generation_result_materializer import GenerationResultMaterializer
from app.services.generation_task_scheduler import wake_generation_scheduler_sync
from app.services.generation_terminalization import (
    GenerationTerminalizationService,
    build_generation_terminal_update,
)
from app.services.jimeng_client import JimengClient
from app.services.klingai_client import KlingAIClient
from app.services.ollama_image_generation import (
    submit_ollama_image_generation,
    validate_ollama_image_generation_request,
)
from app.services.provider_operation_service import ProviderOperationService
from app.services.provider_request_policy import ProviderRequestPolicy
from app.services.provider_result_urls import extract_task_result_urls
from app.services.user_apimart_key_service import UserApimartKeyService
from app.services.volcark_client import VolcArkClient

logger = logging.getLogger(__name__)

LINGYAAI_IMAGE_PENDING_TASK_PREFIX = "lingyaai-image-pending:"
OLLAMA_IMAGE_PENDING_TASK_PREFIX = "ollama-image-pending:"
ProviderRequestResult = TypeVar("ProviderRequestResult")

# Aspect-ratio to pixel size mapping for jimeng image generation, keyed by resolution tier
JIMENG_RATIO_TO_SIZE = {
    "1K": {
        "1:1": (1024, 1024),
    },
    "2K": {
        "1:1": (2048, 2048),
        "4:3": (2304, 1728),
        "3:2": (2496, 1664),
        "16:9": (2560, 1440),
        "21:9": (3024, 1296),
    },
    "4K": {
        "1:1": (4096, 4096),
        "4:3": (4694, 3520),
        "3:2": (4992, 3328),
        "16:9": (5404, 3040),
        "21:9": (6198, 2656),
    },
}


class GenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_repo = GenerationTaskRepository(db)
        self.cred_repo = ProviderCredentialRepository(db)
        self.model_repo = ProviderModelRepository(db)

    async def _get_credentials(
        self,
        user_id: int,
        provider_code: str,
        *,
        credential_id: int | None = None,
    ):
        if provider_code == "builtin":
            user = await self.db.get(User, user_id)
            api_key, credential_id = await UserApimartKeyService(self.db).resolve_key(
                user_id,
                credential_id=credential_id,
                user_role=getattr(user, "role", None),
            )
            return SimpleNamespace(
                access_key=api_key,
                secret_key="",
                auth_type="api_key",
                credential_id=credential_id,
            )
        if provider_code == "ollama":
            return SimpleNamespace(
                access_key=get_ollama_image_api_key(),
                secret_key="",
                auth_type="api_key",
            )

        creds = await self.cred_repo.get_by_user_and_provider(user_id, provider_code)
        if not creds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"未找到供应商 {provider_code} 的密钥配置，请先在供应商管理中配置",
            )
        return creds[0]

    async def _get_model_endpoint(self, user_id: int, provider_code: str, model_name: str) -> str | None:
        """Retrieve the endpoint associated with a model (e.g. for volcark)."""
        models = await self.model_repo.get_by_user_and_provider(user_id, provider_code)
        for m in models:
            if m.model_name == model_name:
                return m.endpoint
        return None

    async def _get_task_credentials(
        self,
        task: GenerationTask,
        *,
        user_id: int | None = None,
        provider_code: str | None = None,
    ):
        credential_id = getattr(task, "apimart_credential_id", None)
        resolved_user_id = int(getattr(task, "user_id", None) or user_id or 0)
        resolved_provider_code = provider_code or str(getattr(task, "provider_code", "builtin") or "builtin")
        if credential_id is None:
            return await self._get_credentials(resolved_user_id, resolved_provider_code)
        return await self._get_credentials(
            resolved_user_id, resolved_provider_code, credential_id=credential_id
        )

    def _build_volcark_client(self, cred) -> VolcArkClient:
        """Build VolcArkClient from credentials."""
        if cred.auth_type == "api_key":
            return VolcArkClient(api_key=cred.access_key)
        # AK/SK mode - use access_key as API key for now
        return VolcArkClient(api_key=cred.access_key)

    # ========================= Image Generation =========================
    def _get_model_label(self, provider_code: str, model_name: str) -> str | None:
        provider = build_provider_registry().get(provider_code)
        if not provider:
            return None
        for category in ["text2image", "text2video", "multimodal"]:
            models = provider.get("models", {}).get(category, [])
            for m in models:
                if m.get("model_name") == model_name:
                    return m.get("label")
        return None

    def _get_model_allowed_image_sizes(self, provider_code: str, model_name: str) -> list[str]:
        provider = build_provider_registry().get(provider_code)
        if not provider:
            return []
        for model in provider.get("models", {}).get("text2image", []):
            if model.get("model_name") == model_name:
                allowed_sizes = model.get("config", {}).get("allowed_sizes", [])
                return [size for size in allowed_sizes if isinstance(size, str)]
        return []

    @staticmethod
    def _image_resolution_sort_key(value: str) -> tuple[int, float | str]:
        normalized = value.strip().upper()
        if normalized.endswith("K"):
            try:
                return (0, float(normalized[:-1]))
            except ValueError:
                return (1, normalized)
        return (1, normalized)

    def _clamp_image_resolution_to_model_capability(
        self,
        provider_code: str,
        model_name: str,
        resolution: str,
    ) -> str:
        allowed_sizes = self._get_model_allowed_image_sizes(provider_code, model_name)
        if not allowed_sizes or resolution in allowed_sizes:
            return resolution
        return max(allowed_sizes, key=self._image_resolution_sort_key)

    @staticmethod
    def _normalize_builtin_result_urls(urls: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_url in urls:
            value = str(raw_url or "").strip()
            if not value:
                continue
            if "," in value:
                parts = [part.strip() for part in value.split(",") if part.strip()]
                if parts:
                    value = parts[0]
            normalized.append(value)
        return normalized

    def _extract_builtin_result_urls(self, data: dict) -> list[str]:
        urls = self._normalize_builtin_result_urls(extract_task_result_urls(data))
        if urls:
            return urls

        result = data.get("result", data)
        raw_result_urls = result.get("result_urls", []) if isinstance(result, dict) else []
        if isinstance(raw_result_urls, str):
            raw_result_urls = [raw_result_urls]
        if isinstance(raw_result_urls, list):
            return self._normalize_builtin_result_urls(
                [url for url in raw_result_urls if isinstance(url, str)]
            )
        return []

    @staticmethod
    def _merge_provider_submit_params(
        params: dict | None,
        *,
        provider_code: str,
        raw: dict | None = None,
        request_diagnostics: dict | None = None,
    ) -> dict:
        merged = dict(params or {})
        submit = dict(merged.get("provider_submit") or {})
        submit["provider_code"] = provider_code
        if raw is not None:
            submit["raw"] = sanitize_persistent_payload(raw)
        if request_diagnostics is not None:
            submit["request_diagnostics"] = sanitize_persistent_payload(request_diagnostics)
            merged["reference_diagnostics"] = merge_reference_diagnostics(
                merged.get("reference_diagnostics"),
                provider_request=submit["request_diagnostics"],
            )
        merged["provider_submit"] = submit
        return sanitize_persistent_payload(merged)

    @staticmethod
    def _sanitize_provider_raw_for_params(value):
        return sanitize_persistent_payload(value)

    @staticmethod
    def _is_within_path(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            return False
        return True

    def _resolve_builtin_image_urls_for_provider(
        self,
        task: GenerationTask,
        image_urls: list[str] | None,
    ) -> list[str] | None:
        if not image_urls:
            return image_urls

        task_params = task.params if isinstance(task.params, dict) else {}
        conversation_id = str(
            task_params.get("agent_conversation_id")
            or task_params.get("conversation_id")
            or ""
        ).strip()
        conversation_dir: Path | None = None
        if conversation_id:
            try:
                from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
                    get_conversation_dir,
                )

                conversation_dir = get_conversation_dir(
                    int(task.user_id),
                    conversation_id,
                    project_id=getattr(task, "project_id", None),
                ).resolve()
            except Exception:
                logger.warning(
                    "Failed to resolve harness conversation directory for generation task %s",
                    getattr(task, "id", None),
                    exc_info=True,
                )

        resolved_urls: list[str] = []
        for raw_url in image_urls:
            value = str(raw_url or "").strip()
            if not value:
                continue
            if value.startswith(("http://", "https://", "data:")):
                resolved_urls.append(value)
                continue
            if conversation_dir is not None:
                normalized = value.replace("\\", "/").lstrip("/")
                candidate = (conversation_dir / Path(normalized)).resolve()
                if (
                    self._is_within_path(candidate, conversation_dir)
                    and candidate.exists()
                    and candidate.is_file()
                ):
                    resolved_urls.append(str(candidate))
                    continue
            resolved_urls.append(value)
        return resolved_urls or None

    async def _store_builtin_result_urls(
        self,
        task: GenerationTask,
        urls: list[str] | None,
    ) -> dict:
        materializer = GenerationResultMaterializer(
            download_file_to_local=self._download_file_to_local,
            build_download_failure_error=self._build_download_failure_error,
        )
        return await materializer.store_builtin_result_urls(task, urls)

    @staticmethod
    def _build_download_failure_error(file_url: str, exc: Exception) -> str:
        return f"result_url_download_failed: {type(exc).__name__}"

    @staticmethod
    def _stringify_submission_error(exc: Exception) -> str:
        if isinstance(exc, HTTPException):
            detail = exc.detail
            if isinstance(detail, str):
                return detail
            return str(detail)
        return str(exc)

    @staticmethod
    def _is_retryable_image_submission_error(exc: Exception) -> bool:
        if isinstance(exc, GenerationMediaResolveError):
            return False
        if isinstance(exc, HTTPException):
            return exc.status_code >= 500
        return True

    async def _retry_image_submission(
        self,
        submitter: Callable[[], Awaitable[dict]],
        *,
        provider_code: str,
        model_name: str,
        max_attempts: int | None = None,
    ) -> dict:
        if max_attempts is None:
            max_attempts = APIMART_IMAGE_SUBMIT_MAX_ATTEMPTS if provider_code == "builtin" else 3
        max_attempts = max(3 if provider_code == "builtin" else 1, max_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                return await submitter()
            except Exception as exc:
                if not self._is_retryable_image_submission_error(exc) or attempt >= max_attempts:
                    raise
                delay_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "Image submission failed for provider=%s model=%s on attempt %s/%s, retrying in %ss",
                    provider_code,
                    model_name,
                    attempt,
                    max_attempts,
                    delay_seconds,
                    exc_info=True,
                )
                await asyncio.sleep(delay_seconds)

    async def _execute_provider_request(
        self,
        *,
        provider: str,
        operation: str,
        request: Callable[[], Awaitable[ProviderRequestResult]],
        priority: str = "normal",
    ) -> ProviderRequestResult:
        limit, window_seconds = self._provider_request_limits(operation)
        decision = await ProviderRequestPolicy(namespace="generation").allow(
            provider=provider,
            operation=operation,
            priority=priority,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="provider_request_rate_limited",
            )
        return await request()

    @staticmethod
    def _provider_request_limits(operation: str) -> tuple[int, float]:
        if operation == "generation_query":
            return (
                max(int(settings.PROVIDER_RATE_LIMIT_GENERATION_QUERY_LIMIT), 0),
                max(float(settings.PROVIDER_RATE_LIMIT_GENERATION_QUERY_WINDOW_SECONDS), 0.001),
            )
        if operation == "result_download":
            return (
                max(int(settings.PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_LIMIT), 0),
                max(float(settings.PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_WINDOW_SECONDS), 0.001),
            )
        return (
            max(int(settings.PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_LIMIT), 0),
            max(float(settings.PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_WINDOW_SECONDS), 0.001),
        )

    async def generate_image(
        self,
        user_id: int,
        project_id: int | None,
        prompt: str,
        model_name: str,
        provider_code: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        image_urls: list[str] | None = None,
        mask_url: str | None = None,
        image_count: int = 1,
        planned_result_url: str | None = None,
        client_request_id: str | None = None,
        existing_task: GenerationTask | None = None,
        metadata_params: dict | None = None,
    ) -> GenerationTask:
        image_count = 1
        if provider_code == "builtin":
            model_name = resolve_builtin_model_name_for_provider("text2image", model_name)
        resolution = self._clamp_image_resolution_to_model_capability(provider_code, model_name, resolution)
        model_label = self._get_model_label(provider_code, model_name)
        task_type = "image_edit" if mask_url else "text2image"

        if mask_url and provider_code != "builtin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前仅内置图片模型支持蒙版擦除",
            )

        if existing_task is None and client_request_id:
            existing_request_task = await self.task_repo.get_by_client_request_id(
                user_id=user_id,
                project_id=project_id,
                task_type=task_type,
                client_request_id=client_request_id,
            )
            if existing_request_task is not None:
                return existing_request_task

        task_params = {
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "image_urls": image_urls,
            "mask_url": mask_url,
            "image_count": image_count,
        }
        if planned_result_url:
            task_params["planned_result_url"] = planned_result_url
        if metadata_params:
            task_params.update(metadata_params)
        task_params["reference_diagnostics"] = merge_reference_diagnostics(
            task_params.get("reference_diagnostics"),
            intake_image_urls=summarize_reference_values(image_urls),
        )
        task_params = sanitize_persistent_payload(task_params)
        if existing_task is None:
            task = GenerationTask(
                user_id=user_id,
                project_id=project_id,
                task_type=task_type,
                provider_code=provider_code,
                model_name=model_name,
                model_label=model_label,
                prompt=prompt,
                params=task_params,
                status="pending",
                client_request_id=client_request_id,
                artifact_ref=task_params.get("artifact_ref"),
            )
            task = await self.task_repo.create(task)
        else:
            task = await self.task_repo.update(
                existing_task,
                {
                    "project_id": project_id,
                    "task_type": task_type,
                    "provider_code": provider_code,
                    "model_name": model_name,
                    "model_label": model_label,
                    "prompt": prompt,
                    "params": task_params,
                    "artifact_ref": task_params.get("artifact_ref"),
                    "status": "pending",
                    "external_task_id": None,
                    "result_url": None,
                    "result_urls": None,
                    "error_message": None,
                    "progress": 0,
                    "scheduler_claim_token": None,
                    "scheduler_claimed_at": None,
                    "scheduler_lease_expires_at": None,
                    "scheduler_next_run_at": None,
                    "workflow_stage": None,
                    "last_error_type": None,
                },
            )

        try:
            cred = await self._get_credentials(user_id, provider_code)
            if provider_code == "builtin" and getattr(cred, "credential_id", None) is not None:
                task = await self.task_repo.update(task, {"apimart_credential_id": cred.credential_id})
            if provider_code == "kling":
                client = KlingAIClient(cred.access_key, cred.secret_key)
                result = await self._retry_image_submission(
                    lambda: client.generate_image(
                        prompt=prompt,
                        model_name=model_name,
                        aspect_ratio=aspect_ratio,
                        image=image_urls[0] if image_urls else None,
                    ),
                    provider_code=provider_code,
                    model_name=model_name,
                )
                external_id = result.get("data", {}).get("task_id")
            elif provider_code == "jimeng":
                client = JimengClient(cred.access_key, cred.secret_key)
                res_map = JIMENG_RATIO_TO_SIZE.get(resolution, JIMENG_RATIO_TO_SIZE["1K"])
                width, height = res_map.get(aspect_ratio, (1024, 1024))
                result = await self._retry_image_submission(
                    lambda: client.generate_image(
                        prompt=prompt,
                        req_key=model_name,
                        width=width,
                        height=height,
                    ),
                    provider_code=provider_code,
                    model_name=model_name,
                )
                external_id = result.get("data", {}).get("task_id")
            elif provider_code == "volcark":
                endpoint_id = await self._get_model_endpoint(user_id, provider_code, model_name)
                if not endpoint_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="模型未配置接入点(Endpoint)，请先在模型配置中设置",
                    )
                client = self._build_volcark_client(cred)
                result = await self._retry_image_submission(
                    lambda: client.generate_image(
                        prompt=prompt,
                        endpoint_id=endpoint_id,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                    ),
                    provider_code=provider_code,
                    model_name=model_name,
                )
                images = result.get("data", [])
                if images:
                    remote_url = images[0].get("url", "")
                    try:
                        result_url = await self._download_file_to_local(
                            remote_url,
                            "png",
                            target_url=planned_result_url,
                        )
                    except Exception as e:
                        logger.error("Failed to download volcark image result: %s", type(e).__name__)
                        error_message = self._build_download_failure_error(remote_url, e)
                        task = await self.task_repo.update(
                            task,
                            {
                                "status": "failed",
                                "error_message": error_message,
                                "external_task_id": "sync",
                            },
                        )
                        return task
                    task = await self.task_repo.update(
                        task,
                        {
                            "status": "completed",
                            "result_url": result_url,
                            "result_urls": [result_url] if result_url else None,
                            "external_task_id": "sync",
                        },
                    )
                    return task
                raise RuntimeError("Image generation returned no images")
            elif provider_code == "ollama":
                reference_image_urls = self._resolve_builtin_image_urls_for_provider(task, image_urls) or []
                validate_ollama_image_generation_request(
                    model_name=model_name,
                    image_urls=reference_image_urls,
                    local_path_resolver=self._resolve_ollama_reference_filepath,
                )
                task_params = self._merge_provider_submit_params(task.params, provider_code="ollama")
                task = await self.task_repo.update(
                    task,
                    {
                        "status": "processing",
                        "external_task_id": self._build_ollama_pending_image_task_id(task.id),
                        "params": task_params,
                        "workflow_stage": "ollama_image_submit",
                        "scheduler_next_run_at": datetime.now(UTC),
                    },
                )
                self._schedule_ollama_image_completion(task_id=task.id, user_id=user_id)
                return task
            elif provider_code == "builtin":
                provider = get_active_builtin_provider(cred.access_key)
                task_params = self._merge_provider_submit_params(
                    task.params,
                    provider_code=provider.code,
                )
                task = await self.task_repo.update(
                    task,
                    {
                        "status": "processing",
                        "external_task_id": None,
                        "builtin_provider_code": provider.code,
                        "params": task_params,
                        "workflow_stage": "provider_operation",
                        "scheduler_next_run_at": None,
                    },
                )
                await ProviderOperationService(self.db).enqueue_generation_submit(
                    task,
                    task_kind="image",
                    provider_code=provider.code,
                    priority="foreground",
                )
                return task
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的供应商: {provider_code}",
                )

            task = await self.task_repo.update(
                task,
                {
                    "status": "processing",
                    "external_task_id": str(external_id),
                },
            )
        except HTTPException as exc:
            logger.warning("Image generation submission failed with HTTP error: %s", exc.detail)
            task = await self.task_repo.update(
                task,
                {"status": "failed", "error_message": self._stringify_submission_error(exc)},
            )
        except Exception as e:
            logger.exception("Image generation submission failed")
            task = await self.task_repo.update(
                task,
                {"status": "failed", "error_message": self._stringify_submission_error(e)},
            )

        return task

    @staticmethod
    def _build_lingyaai_pending_image_task_id(task_id: int) -> str:
        return f"{LINGYAAI_IMAGE_PENDING_TASK_PREFIX}{task_id}"

    @staticmethod
    def _is_lingyaai_pending_image_task(task: GenerationTask | SimpleNamespace | None) -> bool:
        if task is None:
            return False
        external_task_id = str(getattr(task, "external_task_id", "") or "").strip()
        if not external_task_id.startswith(LINGYAAI_IMAGE_PENDING_TASK_PREFIX):
            return False
        if str(getattr(task, "provider_code", "") or "").strip() != "builtin":
            return False
        if str(getattr(task, "task_type", "") or "").strip() not in {"text2image", "image_edit"}:
            return False
        builtin_provider_code = str(getattr(task, "builtin_provider_code", "") or "").strip()
        if builtin_provider_code == "lingyaai":
            return True
        params = getattr(task, "params", None)
        if isinstance(params, dict):
            provider_submit = params.get("provider_submit")
            if isinstance(provider_submit, dict) and str(provider_submit.get("provider_code") or "").strip() == "lingyaai":
                return True
        return False

    def _schedule_lingyaai_image_completion(self, *, task_id: int, user_id: int) -> None:
        del task_id, user_id
        wake_generation_scheduler_sync()

    @staticmethod
    def _build_ollama_pending_image_task_id(task_id: int) -> str:
        return f"{OLLAMA_IMAGE_PENDING_TASK_PREFIX}{task_id}"

    @staticmethod
    def _is_ollama_pending_image_task(task: GenerationTask | SimpleNamespace | None) -> bool:
        if task is None:
            return False
        external_task_id = str(getattr(task, "external_task_id", "") or "").strip()
        if not external_task_id.startswith(OLLAMA_IMAGE_PENDING_TASK_PREFIX):
            return False
        if str(getattr(task, "provider_code", "") or "").strip() != "ollama":
            return False
        if str(getattr(task, "task_type", "") or "").strip() not in {"text2image", "image_edit"}:
            return False
        return True

    def _schedule_ollama_image_completion(self, *, task_id: int, user_id: int) -> None:
        del task_id, user_id
        wake_generation_scheduler_sync()

    async def complete_ollama_image_task(
        self,
        *,
        task_id: int,
        user_id: int,
        scheduler_claim_token: str | None = None,
    ) -> None:
        task = await self.task_repo.get_by_id_and_user(task_id, user_id)
        if task is None or task.status in {"completed", "failed"}:
            return
        if not self._is_ollama_pending_image_task(task):
            return
        if scheduler_claim_token and getattr(task, "scheduler_claim_token", None) != scheduler_claim_token:
            logger.info(
                "Skipped Ollama image completion because scheduler claim was lost: task_id=%s",
                task_id,
            )
            return

        cred = await self._get_credentials(user_id, "ollama")
        params = task.params or {}
        reference_image_urls = self._resolve_builtin_image_urls_for_provider(
            task,
            params.get("image_urls"),
        ) or []
        try:
            submit_result = await self._retry_image_submission(
                lambda: submit_ollama_image_generation(
                    base_url=settings.OLLAMA_BASE_URL,
                    api_key=cred.access_key,
                    model_name=task.model_name,
                    prompt=task.prompt,
                    resolution=params.get("resolution") or "1K",
                    aspect_ratio=params.get("aspect_ratio") or "1:1",
                    image_urls=reference_image_urls,
                    local_path_resolver=self._resolve_ollama_reference_filepath,
                ),
                provider_code="ollama",
                model_name=task.model_name,
                max_attempts=3,
            )
            update = await self._store_builtin_result_urls(task, submit_result["result_values"])
            update.update({
                "external_task_id": submit_result["external_task_id"],
                "params": self._merge_provider_submit_params(
                    params,
                    provider_code="ollama",
                    request_diagnostics=submit_result.get("request_diagnostics"),
                ),
                "workflow_stage": "terminal_completed",
                "terminalized_at": datetime.now(UTC),
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            })
        except Exception as exc:
            logger.warning("Ollama image generation completion failed: %s", self._stringify_submission_error(exc))
            update = {
                "status": "failed",
                "error_message": self._stringify_submission_error(exc),
                "params": self._merge_provider_submit_params(params, provider_code="ollama"),
                "last_error_type": "provider_failed",
                "workflow_stage": "terminal_failed",
                "terminalized_at": datetime.now(UTC),
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            }
        if scheduler_claim_token:
            updated_task = await self.task_repo.update_for_scheduler_claim(
                task_id=task_id,
                user_id=user_id,
                claim_token=scheduler_claim_token,
                data=update,
            )
        else:
            updated_task = await self.task_repo.update(task, update)
        if updated_task is not None and self.db is not None:
            await BillingService(self.db).finalize_ollama_generation_billing(updated_task)

    async def complete_lingyaai_image_task(
        self,
        *,
        task_id: int,
        user_id: int,
        scheduler_claim_token: str | None = None,
    ) -> None:
        task = await self.task_repo.get_by_id_and_user(task_id, user_id)
        if task is None or task.status in {"completed", "failed"}:
            return
        if scheduler_claim_token and getattr(task, "scheduler_claim_token", None) != scheduler_claim_token:
            logger.info(
                "Skipped LingyaAI image completion because scheduler claim was lost: task_id=%s",
                task_id,
            )
            return

        cred = await self._get_task_credentials(task, user_id=user_id)
        if getattr(task, "apimart_credential_id", None) != getattr(cred, "credential_id", None) and getattr(cred, "credential_id", None) is not None:
            task = await self.task_repo.update(task, {"apimart_credential_id": cred.credential_id})
        provider = get_builtin_provider("apimart", cred.access_key)
        submit_result: BuiltinSubmitResult = await self._retry_image_submission(
            lambda: self._execute_provider_request(
                provider=provider.code,
                operation="generation_submit",
                request=lambda: provider.submit_image(
                    prompt=task.prompt,
                    model_name=task.model_name,
                    resolution=(task.params or {}).get("resolution") or "1K",
                    aspect_ratio=(task.params or {}).get("aspect_ratio") or "1:1",
                    image_urls=self._resolve_builtin_image_urls_for_provider(
                        task,
                        (task.params or {}).get("image_urls"),
                    ),
                    mask_url=(task.params or {}).get("mask_url"),
                    image_count=(task.params or {}).get("image_count") or 1,
                ),
            ),
            provider_code="builtin",
            model_name=task.model_name,
        )
        task_params = self._merge_provider_submit_params(
            task.params,
            provider_code=provider.code,
            raw=submit_result.raw,
            request_diagnostics=submit_result.request_diagnostics,
        )

        if submit_result.status == "failed":
            payload = {
                "status": "failed",
                "error_message": submit_result.error_message or "调用 LingyaAI 图片生成失败",
                "builtin_provider_code": provider.code,
                "provider_request_id": submit_result.oneapi_request_id,
                "provider_trace_id": submit_result.request_id,
                "params": task_params,
                "last_error_type": "provider_failed",
                "workflow_stage": "terminal_failed",
                "terminalized_at": datetime.now(UTC),
                "scheduler_next_run_at": None,
                "scheduler_claim_token": None,
                "scheduler_claimed_at": None,
                "scheduler_lease_expires_at": None,
            }
            if scheduler_claim_token:
                updated_task = await self.task_repo.update_for_scheduler_claim(
                    task_id=task_id,
                    user_id=user_id,
                    claim_token=scheduler_claim_token,
                    data=payload,
                )
            else:
                updated_task = await self.task_repo.update(task, payload)
            if updated_task is not None and self.db is not None:
                await self._finalize_terminal_side_effects(updated_task)
            return

        update = await self._store_builtin_result_urls(task, submit_result.result_urls)
        update.update({
            "builtin_provider_code": provider.code,
            "provider_request_id": submit_result.oneapi_request_id,
            "provider_trace_id": submit_result.request_id,
            "params": task_params,
            "workflow_stage": "terminal_completed",
            "terminalized_at": datetime.now(UTC),
            "scheduler_next_run_at": None,
            "scheduler_claim_token": None,
            "scheduler_claimed_at": None,
            "scheduler_lease_expires_at": None,
        })
        if submit_result.external_task_id or task.external_task_id:
            update["external_task_id"] = str(submit_result.external_task_id or task.external_task_id)
        if scheduler_claim_token:
            updated_task = await self.task_repo.update_for_scheduler_claim(
                task_id=task_id,
                user_id=user_id,
                claim_token=scheduler_claim_token,
                data=update,
            )
        else:
            updated_task = await self.task_repo.update(task, update)
        if updated_task is not None and self.db is not None:
            await self._finalize_terminal_side_effects(updated_task)

    @staticmethod
    def _resolve_local_filepath(url: str) -> str | None:
        """Try to resolve a local API URL to a filesystem path.

        Handles URLs like:
        - /api/v1/uploads/canvas/{project_id}/{filename}
        - /api/v1/uploads/generated/{filename}
        - /api/v1/uploads/...
        """
        api_prefix = "/api/v1/uploads/"
        if url.startswith(api_prefix):
            generated_path = resolve_generated_upload_path(url)
            if generated_path is not None:
                return str(generated_path)
            relative = url.removeprefix("/api/v1/")  # → "uploads/canvas/123/abc.png"
            if os.path.exists(relative):
                return relative
        return None

    @staticmethod
    def _resolve_ollama_reference_filepath(url: str) -> str | None:
        local_path = GenerationService._resolve_local_filepath(url)
        if local_path:
            return local_path

        candidate = Path(str(url or ""))
        if not candidate.is_absolute():
            return None
        try:
            resolved = candidate.resolve()
        except OSError:
            return None

        harness_root = Path(getattr(settings, "HARNESS_WORKSPACE_ROOT", "uploads/harness")).resolve()
        allowed_roots = [Path("uploads").resolve(), harness_root]
        if (
            resolved.exists()
            and resolved.is_file()
            and any(GenerationService._is_within_path(resolved, root) for root in allowed_roots)
        ):
            return str(resolved)
        return None

    @staticmethod
    async def _download_to_temp(file_url: str) -> str:
        """Download a remote or local-served URL to a temp file."""
        import uuid

        from app.services.media_streaming import stream_http_to_file

        upload = build_generated_upload(f"src_{uuid.uuid4().hex}.png")
        filepath = str(upload.path)

        # If the URL is a relative API path, make it absolute for httpx
        actual_url = file_url
        if file_url.startswith("/api/"):
            actual_url = f"http://127.0.0.1:8000{file_url}"

        await stream_http_to_file(actual_url, upload.path)

        return filepath

    # ========================= Video Generation =========================

    async def generate_video(
        self,
        user_id: int,
        project_id: int,
        prompt: str,
        model_name: str,
        provider_code: str,
        aspect_ratio: str = "16:9",
        duration: int = 5,
        quality: str = "720p",
        resolution: str | None = None,
        audio: bool = False,
        image_urls: list[str] | None = None,
        first_frame_image: str | None = None,
        tail_frame_image: str | None = None,
        return_last_frame: bool | None = None,
        negative_prompt: str | None = None,
        watermark: bool | None = None,
        multi_shot: bool | None = None,
        shot_type: str | None = None,
        multi_prompt: list[dict] | None = None,
        element_list: list[dict] | None = None,
        planned_result_url: str | None = None,
        client_request_id: str | None = None,
        existing_task: GenerationTask | None = None,
        metadata_params: dict | None = None,
    ) -> GenerationTask:
        if provider_code == "builtin":
            model_name = resolve_builtin_model_name_for_provider("text2video", model_name)
        model_label = self._get_model_label(provider_code, model_name)
        provider_image_urls = image_urls or [
            url for url in (first_frame_image, tail_frame_image) if url
        ]

        task_type = "image2video" if provider_image_urls else "text2video"

        if existing_task is None and client_request_id:
            existing_request_task = await self.task_repo.get_by_client_request_id(
                user_id=user_id,
                project_id=project_id,
                task_type=task_type,
                client_request_id=client_request_id,
            )
            if existing_request_task is not None:
                return existing_request_task

        task_params = {
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "quality": quality,
            "resolution": resolution,
            "audio": audio,
            "image_urls": image_urls,
            "first_frame_image": first_frame_image,
            "tail_frame_image": tail_frame_image,
            "return_last_frame": return_last_frame,
            "negative_prompt": negative_prompt,
            "watermark": watermark,
            "multi_shot": multi_shot,
            "shot_type": shot_type,
            "multi_prompt": multi_prompt,
            "element_list": element_list,
        }
        if planned_result_url:
            task_params["planned_result_url"] = planned_result_url
        if metadata_params:
            task_params.update(metadata_params)
        task_params["reference_diagnostics"] = merge_reference_diagnostics(
            task_params.get("reference_diagnostics"),
            intake_image_urls=summarize_reference_values(provider_image_urls),
        )
        task_params = sanitize_persistent_payload(task_params)
        if existing_task is None:
            task = GenerationTask(
                user_id=user_id,
                project_id=project_id,
                task_type=task_type,
                provider_code=provider_code,
                model_name=model_name,
                model_label=model_label,
                prompt=prompt,
                params=task_params,
                status="pending",
                client_request_id=client_request_id,
                artifact_ref=task_params.get("artifact_ref"),
            )
            task = await self.task_repo.create(task)
        else:
            task = await self.task_repo.update(
                existing_task,
                {
                    "project_id": project_id,
                    "task_type": task_type,
                    "provider_code": provider_code,
                    "model_name": model_name,
                    "model_label": model_label,
                    "prompt": prompt,
                    "params": task_params,
                    "artifact_ref": task_params.get("artifact_ref"),
                    "status": "pending",
                    "external_task_id": None,
                    "result_url": None,
                    "result_urls": None,
                    "error_message": None,
                    "progress": 0,
                    "scheduler_claim_token": None,
                    "scheduler_claimed_at": None,
                    "scheduler_lease_expires_at": None,
                    "scheduler_next_run_at": None,
                    "workflow_stage": None,
                    "last_error_type": None,
                },
            )

        try:
            cred = await self._get_credentials(user_id, provider_code)
            if provider_code == "builtin" and getattr(cred, "credential_id", None) is not None:
                task = await self.task_repo.update(task, {"apimart_credential_id": cred.credential_id})
            if provider_code == "kling":
                client = KlingAIClient(cred.access_key, cred.secret_key)
                if provider_image_urls:
                    result = await client.image_to_video(
                        prompt=prompt,
                        image=provider_image_urls[0],
                        model_name=model_name,
                        duration=duration,
                        image_tail=provider_image_urls[1] if len(provider_image_urls) > 1 else None,
                    )
                else:
                    result = await client.generate_video(
                        prompt=prompt,
                        model_name=model_name,
                        aspect_ratio=aspect_ratio,
                        duration=duration,
                    )
                external_id = result.get("data", {}).get("task_id")
            elif provider_code == "jimeng":
                client = JimengClient(cred.access_key, cred.secret_key)
                result = await client.generate_video(
                    prompt=prompt,
                    req_key=model_name,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                    image_urls=provider_image_urls or None,
                )
                external_id = result.get("data", {}).get("task_id")
            elif provider_code == "volcark":
                endpoint_id = await self._get_model_endpoint(user_id, provider_code, model_name)
                if not endpoint_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="模型未配置接入点(Endpoint)，请先在模型配置中设置",
                    )
                volcark = self._build_volcark_client(cred)
                result = await volcark.create_video_task(
                    prompt=prompt,
                    endpoint_id=endpoint_id,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                )
                external_id = result.get("id")
            elif provider_code == "builtin":
                provider = get_active_builtin_provider(cred.access_key)
                task_params = self._merge_provider_submit_params(
                    task.params,
                    provider_code=provider.code,
                )
                task = await self.task_repo.update(
                    task,
                    {
                        "status": "processing",
                        "external_task_id": None,
                        "builtin_provider_code": provider.code,
                        "params": task_params,
                        "workflow_stage": "provider_operation",
                        "scheduler_next_run_at": None,
                    },
                )
                await ProviderOperationService(self.db).enqueue_generation_submit(
                    task,
                    task_kind="video",
                    provider_code=provider.code,
                    priority="foreground",
                )
                return task
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的供应商: {provider_code}",
                )

            task = await self.task_repo.update(
                task,
                {
                    "status": "processing",
                    "external_task_id": str(external_id),
                },
            )
        except HTTPException as exc:
            logger.warning("Video generation submission failed with HTTP error: %s", exc.detail)
            task = await self.task_repo.update(
                task,
                {"status": "failed", "error_message": self._stringify_submission_error(exc)},
            )
        except Exception as e:
            logger.exception("Video generation submission failed")
            task = await self.task_repo.update(
                task,
                {"status": "failed", "error_message": self._stringify_submission_error(e)},
            )

        return task

    # ========================= Query Task Status =========================

    async def query_task_status(
        self,
        task_id: int,
        user_id: int,
        *,
        scheduler_claim_token: str | None = None,
    ) -> GenerationTask:
        task = await self.task_repo.get_by_id_and_user(task_id, user_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

        if task.status in ("completed", "failed"):
            return task

        if self._is_lingyaai_pending_image_task(task):
            return task
        if self._is_ollama_pending_image_task(task):
            return task

        if not task.external_task_id:
            return task

        cred = await self._get_task_credentials(task, user_id=user_id)

        try:
            if task.provider_code == "kling":
                result = await self._query_klingai(task, cred)
            elif task.provider_code == "jimeng":
                result = await self._query_jimeng(task, cred)
            elif task.provider_code == "volcark":
                result = await self._query_volcark(task, cred)
            elif task.provider_code == "builtin":
                result = await self._query_builtin(task, cred)
            else:
                return task

            if result:
                result = build_generation_terminal_update(result)
                if result.get("status") == "failed":
                    logger.error(
                        "Generation task failed: task_id=%s provider=%s model=%s external_task_id=%s error=%s",
                        task.id,
                        task.provider_code,
                        task.model_name,
                        task.external_task_id,
                        result.get("error_message") or "unknown error",
                    )
                if scheduler_claim_token:
                    claimed_task = await self.task_repo.update_for_scheduler_claim(
                        task_id=task_id,
                        user_id=user_id,
                        claim_token=scheduler_claim_token,
                        data=result,
                    )
                    if claimed_task is None:
                        logger.info(
                            "Skipped generation task status update because scheduler claim was lost: task_id=%s",
                            task_id,
                        )
                        return task
                    task = claimed_task
                else:
                    task = await self.task_repo.update(task, result)
        except Exception:
            logger.exception(
                "Task status query failed: task_id=%s provider=%s model=%s external_task_id=%s",
                task.id,
                task.provider_code,
                task.model_name,
                task.external_task_id,
            )
            try:
                await self.db.rollback()
            except Exception:
                logger.warning("Failed to rollback transaction after query error")
            else:
                # rollback expires ORM state; reload before returning so callers
                # do not trigger implicit async IO via attribute access.
                refreshed_task = await self.task_repo.get_by_id_and_user(task_id, user_id)
                if refreshed_task is not None:
                    task = refreshed_task

        return task

    async def _query_klingai(self, task: GenerationTask, cred) -> dict | None:
        client = KlingAIClient(cred.access_key, cred.secret_key)

        if task.task_type == "text2image":
            result = await client.query_image(task.external_task_id)
        elif task.task_type == "text2video":
            result = await client.query_video(task.external_task_id)
        elif task.task_type == "image2video":
            result = await client.query_image_to_video(task.external_task_id)
        else:
            return None

        data = result.get("data", {})
        task_status = data.get("task_status", "")

        if task_status == "succeed":
            task_result = data.get("task_result", {})
            if task.task_type == "text2image":
                images = task_result.get("images", [])
                raw_url = images[0]["url"] if images else None
                if raw_url:
                    try:
                        url = await self._download_file_to_local(
                            raw_url,
                            "png",
                            target_url=(task.params or {}).get("planned_result_url"),
                        )
                    except Exception as e:
                        logger.error("Failed to download image result: %s", type(e).__name__)
                        return {
                            "status": "failed",
                            "error_message": self._build_download_failure_error(raw_url, e),
                        }
                else:
                    url = None
                return {
                    "status": "completed",
                    "result_url": url,
                    "result_urls": [url] if url else None,
                    "progress": 100,
                }
            videos = task_result.get("videos", [])
            raw_url = videos[0]["url"] if videos else None
            if raw_url:
                try:
                    url = await self._download_file_to_local(
                        raw_url,
                        "mp4",
                        target_url=(task.params or {}).get("planned_result_url"),
                    )
                except Exception as e:
                    logger.error("Failed to download video result: %s", type(e).__name__)
                    return {
                        "status": "failed",
                        "error_message": self._build_download_failure_error(raw_url, e),
                    }
            else:
                url = None
            return {"status": "completed", "result_url": url, "progress": 100}
        if task_status == "failed":
            return {
                "status": "failed",
                "error_message": data.get("task_status_msg", "生成失败"),
            }
        return None

    async def _query_jimeng(self, task: GenerationTask, cred) -> dict | None:
        client = JimengClient(cred.access_key, cred.secret_key)

        if task.task_type in ("text2image",):
            result = await client.query_image(task.model_name, task.external_task_id)
        else:
            result = await client.query_video(task.model_name, task.external_task_id)

        data = result.get("data", {})
        task_status = data.get("status", "")

        if task_status == "done":
            if task.task_type == "text2image":
                image_urls = data.get("image_urls", [])
                binary_data = data.get("binary_data_base64", [])
                if image_urls:
                    url = image_urls[0]
                elif binary_data:
                    url = self._save_base64_to_file(binary_data[0], "png")
                else:
                    url = None
                return {
                    "status": "completed",
                    "result_url": url,
                    "result_urls": [url] if url else None,
                    "progress": 100,
                }
            raw_url = data.get("video_url")
            if raw_url:
                try:
                    url = await self._download_file_to_local(
                        raw_url,
                        "mp4",
                        target_url=(task.params or {}).get("planned_result_url"),
                    )
                except Exception as e:
                    logger.error("Failed to download video result: %s", type(e).__name__)
                    return {
                        "status": "failed",
                        "error_message": self._build_download_failure_error(raw_url, e),
                    }
            else:
                url = None
            return {"status": "completed", "result_url": url, "progress": 100}
        if task_status == "failed":
            return {"status": "failed", "error_message": "生成失败"}

        return None

    async def _query_volcark(self, task: GenerationTask, cred) -> dict | None:
        client = self._build_volcark_client(cred)

        if task.task_type == "text2image":
            return None

        result = await client.query_video_task(task.external_task_id)
        task_status = result.get("status", "")

        if task_status == "succeeded":
            content = result.get("content", {})
            video_url = content.get("video_url", "")
            if video_url:
                try:
                    local_url = await self._download_file_to_local(
                        video_url,
                        "mp4",
                        target_url=(task.params or {}).get("planned_result_url"),
                    )
                except Exception as e:
                    logger.error("Failed to download volcark video result: %s", type(e).__name__)
                    return {
                        "status": "failed",
                        "error_message": self._build_download_failure_error(video_url, e),
                    }
                return {"status": "completed", "result_url": local_url, "progress": 100}
            return {"status": "completed", "result_url": video_url, "progress": 100}
        if task_status == "failed":
            error_msg = result.get("error", {}).get("message", "生成失败")
            return {"status": "failed", "error_message": error_msg}

        return None

    async def _query_builtin(self, task: GenerationTask, cred) -> dict | None:
        builtin_provider_code = str(
            getattr(task, "builtin_provider_code", None)
            or ((task.params or {}).get("provider_submit") or {}).get("provider_code")
            or ""
        ).strip()
        provider = get_builtin_provider(builtin_provider_code or "apimart", cred.access_key)
        result: BuiltinQueryResult = await self._execute_provider_request(
            provider=provider.code,
            operation="generation_query",
            priority="background",
            request=lambda: provider.query_generation(
                task.external_task_id,
                task_type=task.task_type,
                model_name=getattr(task, "model_name", ""),
            ),
        )

        task_params = self._merge_provider_submit_params(
            task.params,
            provider_code=provider.code,
        )

        if result.status == "completed":
            urls = self._normalize_builtin_result_urls(result.result_urls or [])
            expected_count = (task.params or {}).get("expected_image_count")
            if expected_count and len(urls) != expected_count:
                return {
                    "status": "failed",
                    "error_message": f"模型未返回 {expected_count} 张图片",
                    "params": task_params,
                }

            update = await self._store_builtin_result_urls(task, urls)
            update["params"] = task_params
            return update

        if result.status == "failed":
            return {
                "status": "failed",
                "error_message": result.error_message or "生成失败",
                "params": task_params,
            }

        update = {"params": task_params}
        if result.progress is not None:
            update["progress"] = result.progress
        return update

    async def complete_builtin_image_submit_operation(self, task: GenerationTask, operation) -> GenerationTask:
        params = task.params or {}
        cred = await self._get_task_credentials(task)
        if getattr(task, "apimart_credential_id", None) != getattr(cred, "credential_id", None) and getattr(cred, "credential_id", None) is not None:
            task = await self.task_repo.update(task, {"apimart_credential_id": cred.credential_id})
        provider = get_builtin_provider(
            "apimart",
            cred.access_key,
        )
        submit_result: BuiltinSubmitResult = await self._retry_image_submission(
            lambda: provider.submit_image(
                prompt=task.prompt,
                model_name=task.model_name,
                resolution=params.get("resolution") or "1K",
                aspect_ratio=params.get("aspect_ratio") or "1:1",
                image_urls=self._resolve_builtin_image_urls_for_provider(task, params.get("image_urls")),
                mask_url=params.get("mask_url"),
                image_count=params.get("image_count") or 1,
            ),
            provider_code="builtin",
            model_name=task.model_name,
        )
        return await self._complete_builtin_submit_operation(task, operation, provider, submit_result)

    async def complete_builtin_video_submit_operation(self, task: GenerationTask, operation) -> GenerationTask:
        params = task.params or {}
        cred = await self._get_task_credentials(task)
        if getattr(task, "apimart_credential_id", None) != getattr(cred, "credential_id", None) and getattr(cred, "credential_id", None) is not None:
            task = await self.task_repo.update(task, {"apimart_credential_id": cred.credential_id})
        provider = get_builtin_provider(
            "apimart",
            cred.access_key,
        )
        submit_result: BuiltinSubmitResult = await provider.submit_video(
            prompt=task.prompt,
            model_name=task.model_name,
            aspect_ratio=params.get("aspect_ratio") or "16:9",
            duration=params.get("duration") or 5,
            quality=params.get("quality"),
            resolution=params.get("resolution"),
            audio=bool(params.get("audio")),
            image_urls=params.get("image_urls"),
            first_frame_image=params.get("first_frame_image"),
            tail_frame_image=params.get("tail_frame_image"),
            return_last_frame=params.get("return_last_frame"),
            negative_prompt=params.get("negative_prompt"),
            watermark=params.get("watermark"),
            multi_shot=params.get("multi_shot"),
            shot_type=params.get("shot_type"),
            multi_prompt=params.get("multi_prompt"),
            element_list=params.get("element_list"),
        )
        return await self._complete_builtin_submit_operation(task, operation, provider, submit_result)

    async def _complete_builtin_submit_operation(
        self,
        task: GenerationTask,
        operation,
        provider,
        submit_result: BuiltinSubmitResult,
    ) -> GenerationTask:
        operation_repo = ProviderOperationRepository(self.db)
        task_params = self._merge_provider_submit_params(
            task.params,
            provider_code=provider.code,
            raw=submit_result.raw,
            request_diagnostics=submit_result.request_diagnostics,
        )
        if submit_result.status == "failed":
            task = await self.task_repo.update(
                task,
                {
                    "status": "failed",
                    "error_message": submit_result.error_message or "调用内置供应商失败",
                    "builtin_provider_code": provider.code,
                    "provider_request_id": submit_result.oneapi_request_id,
                    "provider_trace_id": submit_result.request_id,
                    "params": task_params,
                    "last_error_type": "provider_failed",
                    "workflow_stage": "terminal_failed",
                    "terminalized_at": datetime.now(UTC),
                },
            )
            await operation_repo.mark_failed(
                operation,
                error_type="provider_failed",
                error_message=submit_result.error_message,
            )
            await self._finalize_terminal_side_effects(task)
            return task

        update = {
            "builtin_provider_code": provider.code,
            "provider_request_id": submit_result.oneapi_request_id,
            "provider_trace_id": submit_result.request_id,
            "params": task_params,
            "workflow_stage": "provider_operation",
            "last_error_type": None,
        }
        if submit_result.external_task_id:
            update["external_task_id"] = str(submit_result.external_task_id)
        elif submit_result.status != "completed":
            task = await self.task_repo.update(
                task,
                {
                    "status": "failed",
                    "error_message": submit_result.error_message or "内置供应商未返回任务 ID",
                    "builtin_provider_code": provider.code,
                    "provider_request_id": submit_result.oneapi_request_id,
                    "provider_trace_id": submit_result.request_id,
                    "params": task_params,
                    "last_error_type": "provider_missing_task_id",
                    "workflow_stage": "terminal_failed",
                    "terminalized_at": datetime.now(UTC),
                },
            )
            await operation_repo.mark_failed(
                operation,
                error_type="provider_missing_task_id",
                error_message=submit_result.error_message or "missing external task id",
            )
            await self._finalize_terminal_side_effects(task)
            return task
        task = await self.task_repo.update(task, update)
        await operation_repo.mark_succeeded(
            operation,
            result_payload={"external_task_id": submit_result.external_task_id, "status": submit_result.status},
        )

        if submit_result.status == "completed":
            await ProviderOperationService(self.db).enqueue_result_download(
                task,
                provider_code=provider.code,
                result_urls=self._normalize_builtin_result_urls(submit_result.result_urls or []),
            )
            return task

        await ProviderOperationService(self.db).enqueue_generation_query(
            task,
            provider_code=provider.code,
        )
        return task

    async def query_builtin_task_for_operation(self, task: GenerationTask) -> dict | None:
        cred = await self._get_task_credentials(task)
        provider = get_builtin_provider("apimart", cred.access_key)
        result: BuiltinQueryResult = await provider.query_generation(
            task.external_task_id,
            task_type=task.task_type,
            model_name=getattr(task, "model_name", ""),
        )
        task_params = self._merge_provider_submit_params(task.params, provider_code=provider.code)

        if result.status == "completed":
            urls = self._normalize_builtin_result_urls(result.result_urls or [])
            expected_count = (task.params or {}).get("expected_image_count")
            if expected_count and len(urls) != expected_count:
                task = await self.task_repo.update(
                    task,
                    {
                        "status": "failed",
                        "error_message": f"模型未返回 {expected_count} 张图片",
                        "params": task_params,
                        "last_error_type": "provider_failed",
                        "workflow_stage": "terminal_failed",
                        "terminalized_at": datetime.now(UTC),
                    },
                )
                await self._finalize_terminal_side_effects(task)
                return {"status": "failed"}
            await ProviderOperationService(self.db).enqueue_result_download(
                task,
                provider_code=provider.code,
                result_urls=urls,
            )
            return {"status": "completed", "pending_result_download": True, "result_urls": urls}

        if result.status == "failed":
            task = await self.task_repo.update(
                task,
                {
                    "status": "failed",
                    "error_message": result.error_message or "生成失败",
                    "params": task_params,
                    "last_error_type": "provider_failed",
                    "workflow_stage": "terminal_failed",
                    "terminalized_at": datetime.now(UTC),
                },
            )
            await self._finalize_terminal_side_effects(task)
            return {"status": "failed"}

        update = {"params": task_params}
        if result.progress is not None:
            update["progress"] = result.progress
        await self.task_repo.update(task, update)
        return None

    async def complete_result_download_operation(self, task: GenerationTask, operation) -> GenerationTask:
        operation_repo = ProviderOperationRepository(self.db)
        payload = operation.payload if isinstance(operation.payload, dict) else {}
        urls = self._normalize_builtin_result_urls(payload.get("result_urls") or [])
        update = await self._store_builtin_result_urls(task, urls)
        if update.get("status") == "completed":
            update.update(
                {
                    "workflow_stage": "terminal_completed",
                    "terminalized_at": datetime.now(UTC),
                    "last_error_type": None,
                }
            )
            task = await self.task_repo.update(task, update)
            await operation_repo.mark_succeeded(operation, result_payload={"result_urls": task.result_urls or []})
            await self._finalize_terminal_side_effects(task)
            return task

        update.update(
            {
                "workflow_stage": "terminal_failed",
                "terminalized_at": datetime.now(UTC),
                "last_error_type": "result_download_failed",
            }
        )
        task = await self.task_repo.update(task, update)
        await operation_repo.mark_failed(
            operation,
            error_type="result_download_failed",
            error_message=task.error_message,
        )
        await self._finalize_terminal_side_effects(task)
        return task

    async def _finalize_terminal_side_effects(self, task: GenerationTask) -> None:
        if getattr(task, "terminal_side_effects_finalized_at", None) is not None:
            return
        finalized = await GenerationTerminalizationService(
            self.db,
            billing_service_factory=BillingService,
        ).finalize_terminal_task(task, user_id=getattr(task, "user_id", None))
        if finalized:
            await self.task_repo.mark_terminal_side_effects_finalized(task.id)

    @staticmethod
    def _save_base64_to_file(base64_data: str, ext: str = "png") -> str:
        """Save base64-encoded data to a file and return the URL path."""
        import base64
        import uuid

        filename = f"{uuid.uuid4().hex}.{ext}"
        upload = build_generated_upload(filename)

        with open(upload.path, "wb") as f:
            f.write(base64.b64decode(base64_data))

        return upload.url

    @staticmethod
    async def _download_file_to_local(
        file_url: str,
        ext: str = "mp4",
        *,
        target_url: str | None = None,
    ) -> str:
        """Download remote URL to local file and return the URL path."""
        import uuid

        from app.services.media_streaming import stream_http_to_file, write_data_uri_to_file

        upload = None
        filepath = None
        if target_url:
            target_path = resolve_generated_upload_path(target_url, must_exist=False)
            if target_path is not None:
                filepath = str(target_path)
        if filepath is None:
            filename = f"{uuid.uuid4().hex}.{ext}"
            upload = build_generated_upload(filename)
            filepath = str(upload.path)

        if isinstance(file_url, str) and file_url.startswith("data:"):
            write_data_uri_to_file(file_url, Path(filepath))
            return target_url if target_url and upload is None else upload.url

        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                await stream_http_to_file(file_url, Path(filepath))
                break
            except Exception:
                if attempt >= max_attempts:
                    raise
                delay_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "Download failed for %s on attempt %s/%s, retrying in %ss",
                    file_url,
                    attempt,
                    max_attempts,
                    delay_seconds,
                )
                await asyncio.sleep(delay_seconds)

        return target_url if target_url and upload is None else upload.url
