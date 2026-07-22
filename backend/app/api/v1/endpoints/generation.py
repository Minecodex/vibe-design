from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.core.billing_errors import raise_insufficient_balance
from app.core.billing_pricing import get_model_label
from app.core.default_models import (
    get_default_image_analysis_model,
    get_default_image_analysis_provider,
)
from app.core.feature_models import get_feature_image_model
from app.core.providers import get_active_builtin_provider_code
from app.repositories.generation_repository import GenerationTaskRepository
from app.schemas.generation import (
    GenerateContentRequest,
    GenerateContentResponse,
    GenerateHDUpscaleRequest,
    GenerateHDUpscaleResponse,
    GenerateImageEraseRequest,
    GenerateImageRequest,
    GenerateSpatialAngleRequest,
    GenerateVideoRequest,
    GenerationTaskRead,
    RecoverGenerationTasksRequest,
    RecoverGenerationTasksResponse,
    RetryGenerationTaskRequest,
    TextRedrawExtractRequest,
    TextRedrawExtractResponse,
    TextRedrawSubmitRequest,
)
from app.services.agent_harness.core.utils.media_utils import resolve_url_for_api
from app.services.billing_service import BillingService
from app.services.generation_intake_service import GenerationIntakeRequest, GenerationIntakeService
from app.services.generation_service import GenerationService
from app.services.image_erase import build_image_erase_prompt
from app.services.image_output_selection import DEFAULT_IMAGE_PROVIDER, select_image_output
from app.services.project_service import ProjectService
from app.services.task_poller import task_poller
from app.services.text_redraw import (
    build_text_redraw_extraction_prompt,
    build_text_redraw_prompt,
    extract_text_redraw_response_text,
    parse_text_redraw_segments,
)

router = APIRouter(tags=["generation"])


async def _handle_builtin_billing(
    db,
    user_id: int,
    model_name: str,
    task_type: str,
    resolution: str | None,
    duration: int | None,
    params: dict,
) -> int:
    """Calculate and deduct billing amount for builtin provider. Returns cents."""
    billing_svc = BillingService(db)
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
            raise_insufficient_balance(
                required_cents=amount_cents,
                balance_cents=balance_cents,
            )
    return amount_cents


async def _finalize_completed_builtin_billing(db, task) -> None:
    if task.provider_code != "builtin" or task.status != "completed":
        return
    if getattr(task, "builtin_provider_code", None) != "lingyaai":
        return
    billing_svc = BillingService(db)
    await billing_svc.finalize_lingyaai_generation_billing(task)


@router.post(
    "/projects/{project_id}/generate/image", response_model=GenerationTaskRead
)
async def generate_image(
    project_id: int,
    data: GenerateImageRequest,
    db: DbSession,
    user: CurrentUser,
):
    # Verify project ownership
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    result = await GenerationIntakeService(db).submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=data.prompt,
            model_name=data.model_name,
            provider_code=data.provider_code,
            aspect_ratio=data.aspect_ratio,
            resolution=data.resolution,
            image_urls=data.image_urls,
            client_request_id=data.client_request_id,
        )
    )
    return result.task


@router.post(
    "/projects/{project_id}/generate/video", response_model=GenerationTaskRead
)
async def generate_video(
    project_id: int,
    data: GenerateVideoRequest,
    db: DbSession,
    user: CurrentUser,
):
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)
    has_image_inputs = bool(data.image_urls or data.first_frame_image or data.tail_frame_image)
    resolved_resolution = data.resolution or data.quality
    audio_enabled = bool(data.audio or (resolved_resolution or "").lower().endswith("_audio"))
    task_type = "image2video" if has_image_inputs else "text2video"

    result = await GenerationIntakeService(db).submit_video(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=data.prompt,
            model_name=data.model_name,
            provider_code=data.provider_code,
            task_type=task_type,
            aspect_ratio=data.aspect_ratio,
            duration=data.duration,
            quality=data.quality,
            resolution=resolved_resolution,
            audio=audio_enabled,
            image_urls=data.image_urls,
            first_frame_image=data.first_frame_image,
            tail_frame_image=data.tail_frame_image,
            client_request_id=data.client_request_id,
        )
    )
    return result.task


@router.post("/multimodal/generate", response_model=GenerateContentResponse)
async def generate_content(
    data: GenerateContentRequest,
    db: DbSession,
    user: CurrentUser,
):
    from app.services.multimodal_service import MultimodalService
    svc = MultimodalService(db)
    result = await svc.chat(
        user_id=user.id,
        model_name=data.model_name,
        messages=data.messages,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
    )
    return result


@router.post(
    "/projects/{project_id}/text-redraw/extract",
    response_model=TextRedrawExtractResponse,
)
async def extract_text_redraw(
    project_id: int,
    data: TextRedrawExtractRequest,
    db: DbSession,
    user: CurrentUser,
):
    from app.services.multimodal_service import MultimodalService

    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    svc = MultimodalService(db)
    resolved = resolve_url_for_api(data.image_url, prefer="base64")
    if resolved and resolved["type"] == "base64":
        image_url = f"data:{resolved['mime_type']};base64,{resolved['data']}"
    elif resolved and resolved["type"] == "url":
        image_url = resolved["url"]
    else:
        image_url = data.image_url

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": build_text_redraw_extraction_prompt()},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]

    try:
        result = await svc.chat(
            user_id=user.id,
            model_name=get_default_image_analysis_model(),
            provider_code=get_default_image_analysis_provider(),
            messages=messages,
            task_type="text_recognition",
            billing_label="billing.labels.text_recognition",
        )
        text = extract_text_redraw_response_text(result)
        segments = parse_text_redraw_segments(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text redraw extraction failed: {str(exc)}",
        ) from exc

    return TextRedrawExtractResponse(segments=segments)


@router.post(
    "/projects/{project_id}/generate/text-redraw",
    response_model=GenerationTaskRead,
)
async def generate_text_redraw(
    project_id: int,
    data: TextRedrawSubmitRequest,
    db: DbSession,
    user: CurrentUser,
):
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    aspect_ratio = "1:1"
    resolution = "1K"
    if data.source_width and data.source_height:
        output_config = select_image_output(data.source_width, data.source_height, feature_name="text_redraw")
        aspect_ratio = output_config["aspect_ratio"]
        resolution = output_config["resolution"]

    prompt = build_text_redraw_prompt(
        [segment.model_dump() for segment in data.original_segments],
        [segment.model_dump() for segment in data.edited_segments],
    )

    model_name = get_feature_image_model("text_redraw")

    result = await GenerationIntakeService(db).submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=prompt,
            model_name=model_name,
            provider_code=DEFAULT_IMAGE_PROVIDER,
            task_type="text_redraw",
            billing_label="billing.labels.text_redraw",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            image_urls=[data.source_image_url],
            metadata_params={
                "generation_kind": "text_redraw",
                "source_image_url": data.source_image_url,
                "source_width": data.source_width,
                "source_height": data.source_height,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
        )
    )

    return result.task


@router.post(
    "/projects/{project_id}/generate/erase",
    response_model=GenerationTaskRead,
)
async def generate_image_erase(
    project_id: int,
    data: GenerateImageEraseRequest,
    db: DbSession,
    user: CurrentUser,
):
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    output_config = select_image_output(data.source_width, data.source_height, feature_name="erase")
    prompt = build_image_erase_prompt()
    model_name = get_feature_image_model("erase")

    result = await GenerationIntakeService(db).submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=prompt,
            model_name=model_name,
            provider_code=DEFAULT_IMAGE_PROVIDER,
            task_type="image_erase",
            billing_label="billing.labels.image_erase",
            aspect_ratio=output_config["aspect_ratio"],
            resolution=output_config["resolution"],
            image_urls=[data.source_image_url],
            metadata_params={
                "generation_kind": "image_erase",
                "source_image_url": data.source_image_url,
                "source_width": data.source_width,
                "source_height": data.source_height,
                "aspect_ratio": output_config["aspect_ratio"],
                "resolution": output_config["resolution"],
            },
        )
    )

    return result.task


@router.post(
    "/projects/{project_id}/generation-tasks/recover",
    response_model=RecoverGenerationTasksResponse,
)
async def recover_generation_tasks(
    project_id: int,
    data: RecoverGenerationTasksRequest,
    db: DbSession,
    user: CurrentUser,
):
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    repo = GenerationTaskRepository(db)
    tasks = await repo.list_by_client_request_items(
        user_id=user.id,
        project_id=project_id,
        items=[(item.task_type, item.client_request_id) for item in data.items],
    )
    return RecoverGenerationTasksResponse(
        tasks={
            f"{task.task_type}:{task.client_request_id}": GenerationTaskRead.model_validate(task)
            for task in tasks
            if task.client_request_id
        }
    )


@router.get(
    "/generation-tasks/{task_id}/status", response_model=GenerationTaskRead
)
async def query_task_status(
    task_id: int,
    db: DbSession,
    user: CurrentUser,
):
    # Pure DB read — backend poller handles provider queries and balance management
    repo = GenerationTaskRepository(db)
    task = await repo.get_by_id_and_user(task_id, user.id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
        )
    return task


@router.post(
    "/generation-tasks/{task_id}/retry", response_model=GenerationTaskRead
)
async def retry_generation_task(
    task_id: int,
    data: RetryGenerationTaskRequest,
    db: DbSession,
    user: CurrentUser,
):
    repo = GenerationTaskRepository(db)
    task = await repo.get_by_id_and_user(task_id, user.id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
        )
    if task.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="仅失败任务支持重新生成"
        )
    if not task.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="任务缺少项目信息"
        )

    project_svc = ProjectService(db)
    await project_svc.get(task.project_id, user.id)

    params = task.params or {}
    prompt = data.prompt if data.prompt is not None else task.prompt
    model_name = data.model_name if data.model_name is not None else task.model_name
    provider_code = data.provider_code if data.provider_code is not None else task.provider_code
    gen_svc = GenerationService(db)
    billing_svc = BillingService(db)
    amount_cents = 0

    try:
        if task.task_type in {"text2image", "image_edit"}:
            aspect_ratio = data.aspect_ratio or params.get("aspect_ratio") or "1:1"
            requested_resolution = data.resolution or params.get("resolution") or "1K"
            resolution = gen_svc._clamp_image_resolution_to_model_capability(
                provider_code,
                model_name,
                requested_resolution,
            )
            image_urls = data.image_urls
            if image_urls is None:
                image_urls = [data.image_url] if data.image_url else params.get("image_urls")
            if provider_code == "builtin":
                amount_cents = await _handle_builtin_billing(
                    db,
                    user.id,
                    model_name,
                    "text2image",
                    resolution,
                    None,
                    {"resolution": resolution, "aspect_ratio": aspect_ratio},
                )
            updated_task = await gen_svc.generate_image(
                user_id=user.id,
                project_id=task.project_id,
                prompt=prompt,
                model_name=model_name,
                provider_code=provider_code,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                image_urls=image_urls,
                existing_task=task,
            )
            billing_label = "billing.labels.image_generate"
            usage_task_type = "text2image"
            usage_params = {"resolution": resolution, "aspect_ratio": aspect_ratio}
        elif task.task_type in {"text2video", "image2video"}:
            aspect_ratio = data.aspect_ratio or params.get("aspect_ratio") or "16:9"
            duration = data.duration or params.get("duration") or 5
            resolution = data.resolution or params.get("resolution")
            quality = data.quality or params.get("quality") or resolution or "720p"
            audio = bool(data.audio if data.audio is not None else params.get("audio"))
            image_urls = data.image_urls
            if image_urls is None:
                image_urls = [data.image_url] if data.image_url else params.get("image_urls")
            first_frame_image = (
                data.first_frame_image
                if data.first_frame_image is not None
                else params.get("first_frame_image")
            )
            tail_frame_image = (
                data.tail_frame_image
                if data.tail_frame_image is not None
                else params.get("tail_frame_image")
            )
            has_image_inputs = bool(image_urls or first_frame_image or tail_frame_image)
            usage_task_type = "image2video" if has_image_inputs else "text2video"
            if provider_code == "builtin":
                amount_cents = await _handle_builtin_billing(
                    db,
                    user.id,
                    model_name,
                    usage_task_type,
                    resolution or quality,
                    duration,
                    {
                        "resolution": resolution or quality,
                        "duration": duration,
                        "aspect_ratio": aspect_ratio,
                        "audio": audio,
                    },
                )
            updated_task = await gen_svc.generate_video(
                user_id=user.id,
                project_id=task.project_id,
                prompt=prompt,
                model_name=model_name,
                provider_code=provider_code,
                aspect_ratio=aspect_ratio,
                duration=duration,
                quality=quality,
                resolution=resolution,
                audio=audio,
                image_urls=image_urls,
                first_frame_image=first_frame_image,
                tail_frame_image=tail_frame_image,
                existing_task=task,
            )
            billing_label = "billing.labels.video_generate"
            usage_params = {
                "resolution": resolution or quality,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "audio": audio,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该任务类型暂不支持重新生成",
            )
    except Exception:
        if amount_cents > 0:
            await billing_svc.refund_balance(user.id, amount_cents)
        raise

    if provider_code == "builtin" and amount_cents > 0 and updated_task.status == "failed":
        await billing_svc.refund_balance(user.id, amount_cents)
        usage_log = await billing_svc.usage_repo.get_by_task_id(updated_task.id)
        if usage_log:
            await billing_svc.update_usage_log(
                usage_log.id,
                {
                    "amount_cents": 0,
                    "amount_cents_original": amount_cents,
                    "status": "refunded",
                },
            )

    if provider_code == "builtin" and amount_cents > 0 and updated_task.status != "failed":
        usage_log = await billing_svc.usage_repo.get_by_task_id(updated_task.id)
        usage_data = {
            "model_name": model_name,
            "model_label": get_model_label(model_name),
            "task_type": usage_task_type,
            "amount_cents": amount_cents,
            "amount_cents_original": amount_cents,
            "billing_label": billing_label,
            "params": usage_params,
            "status": "pending",
            "provider_code": "apimart",
            "billing_mode": "local_price",
        }
        if usage_log:
            await billing_svc.update_usage_log(usage_log.id, usage_data)
        else:
            await billing_svc.create_usage_log(
                user_id=user.id,
                task_id=updated_task.id,
                model_name=model_name,
                task_type=usage_task_type,
                amount_cents=amount_cents,
                params=usage_params,
                task_status="pending",
                billing_label=billing_label,
                provider_code="apimart",
                billing_mode="local_price",
            )

    if updated_task.status == "processing":
        await task_poller.enqueue_task(updated_task.id, workflow_stage="provider_query")

    return updated_task


@router.post(
    "/projects/{project_id}/generate/hd",
    response_model=GenerateHDUpscaleResponse,
)
async def generate_hd_upscale(
    project_id: int,
    data: GenerateHDUpscaleRequest,
    db: DbSession,
    user: CurrentUser,
):
    from app.services.hd_upscale import build_hd_upscale_prompt, select_hd_upscale_output

    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    output_config = select_hd_upscale_output(data.source_width, data.source_height)
    prompt = build_hd_upscale_prompt()
    model_name = get_feature_image_model("hd_upscale")

    result = await GenerationIntakeService(db).submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=prompt,
            model_name=model_name,
            provider_code=DEFAULT_IMAGE_PROVIDER,
            task_type="hd_upscale",
            billing_label="billing.labels.hd_upscale",
            aspect_ratio=output_config["aspect_ratio"],
            resolution=output_config["resolution"],
            image_urls=[data.source_image_url],
            metadata_params={
                "generation_kind": "image_hd_upscale",
                "source_image_url": data.source_image_url,
                "source_width": data.source_width,
                "source_height": data.source_height,
                "aspect_ratio": output_config["aspect_ratio"],
                "resolution": output_config["resolution"],
            },
        )
    )

    return GenerateHDUpscaleResponse(
        task=result.task,
        calculated_width=output_config["width"],
        calculated_height=output_config["height"],
    )


@router.post(
    "/projects/{project_id}/generate/spatial-angle",
    response_model=GenerationTaskRead,
)
async def generate_spatial_angle(
    project_id: int,
    data: GenerateSpatialAngleRequest,
    db: DbSession,
    user: CurrentUser,
):
    project_svc = ProjectService(db)
    await project_svc.get(project_id, user.id)

    prompt = f"camera position: center x=0 y=0; up y positive, down y negative (range -30 to 60); left x negative, right x positive (range -90 to 90); scale: close-up, normal, wide-angle; x={data.x}, y={data.y}, scale={data.scale}"

    output_config = select_image_output(data.source_width, data.source_height, feature_name="spatial_angle")
    resolution = output_config["resolution"]
    model_name = get_feature_image_model("spatial_angle")
    resolution = GenerationService(db)._clamp_image_resolution_to_model_capability(
        DEFAULT_IMAGE_PROVIDER,
        model_name,
        resolution,
    )

    result = await GenerationIntakeService(db).submit_image(
        GenerationIntakeRequest(
            user_id=user.id,
            project_id=project_id,
            prompt=prompt,
            model_name=model_name,
            provider_code=DEFAULT_IMAGE_PROVIDER,
            task_type="spatial_angle",
            billing_label="billing.labels.spatial_angle",
            aspect_ratio=output_config["aspect_ratio"],
            resolution=resolution,
            image_urls=[data.source_image_url],
            metadata_params={
                "generation_kind": "image_spatial_angle",
                "source_image_url": data.source_image_url,
                "source_width": data.source_width,
                "source_height": data.source_height,
                "aspect_ratio": output_config["aspect_ratio"],
                "resolution": resolution,
                "x": data.x,
                "y": data.y,
                "scale": data.scale,
            },
        )
    )

    return result.task
