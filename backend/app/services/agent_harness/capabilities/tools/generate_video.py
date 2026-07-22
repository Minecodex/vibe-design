"""Video generation tool for the Harness agent.

Uses the shared GenerationIntakeService so Harness media tasks are persisted in
the SQL ``generation_tasks`` table and scheduled through the same intake path as
canvas generation.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.media_capabilities import (
    build_video_tool_schema,
    get_model_config,
    resolve_video_generation_selection,
)

from app.services.agent_harness.core.utils.artifacts import build_artifact_metadata
from app.services.agent_harness.core.utils.media_generation_preferences import (
    resolve_video_generation_preferences,
)
from app.services.agent_harness.core.utils.media_defaults import resolve_harness_video_defaults
from app.services.agent_harness.core.utils.media_utils import (
    local_path_to_oss,
    resolve_safe_local_media_path,
    resolve_url_for_api,
)
from app.services.agent_harness.core.utils.model_labels import resolve_model_label
from app.services.agent_harness.workspace.generated_content.asset_store import planned_reference_asset_path
from app.services.agent_harness.canvas.agent_item_persistence import persist_agent_canvas_item_patch
from app.services.agent_harness.canvas.generation_mapper import build_canvas_generation_item
from app.services.agent_harness.workflow.tool_gating import normalize_presentation_scope
from app.services.generation_intake_service import GenerationIntakeRequest, GenerationIntakeService
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context
from ._internal.base import BaseTool, ToolResult
from ._internal.reference_diagnostics import message_reference_diagnostics

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

logger = logging.getLogger(__name__)


class GenerateVideoMultiPromptStep(BaseModel):
    index: int = Field(..., description="分镜序号，从 1 开始连续递增。")
    prompt: str = Field(..., description="单个分镜的提示词。")
    duration: int = Field(..., description="该分镜时长（秒）。")


class GenerateVideoElementRef(BaseModel):
    name: str = Field(..., description="元素名称，可在提示词中通过 @name 引用。")
    description: str = Field(..., description="元素描述。")
    element_input_urls: list[str] = Field(..., description="主体参考图 URL 列表，建议 2-4 张。")


class GenerateVideoOutputOptions(BaseModel):
    resolution: str | None = Field(
        None, description="视频输出分辨率，如 720p, 1080p。省略时使用模型支持的最高分辨率。"
    )
    generate_audio: bool | None = Field(
        None,
        description="是否生成带音频的视频。省略时按模型默认值和分辨率档位处理。",
    )


class GenerateVideoFrameInput(BaseModel):
    first_image_url: str | None = Field(
        None,
        description="首帧图 URL、references/generated/... 或 project/... 相对路径或 artifact_ref。",
    )
    last_image_url: str | None = Field(
        None,
        description="尾帧图 URL、references/generated/... 或 project/... 相对路径或 artifact_ref。使用尾帧时必须同时提供首帧。",
    )


class GenerateVideoReferenceInput(BaseModel):
    image_urls: list[str] | None = Field(
        None,
        description="参考图片列表。适合参考图模式或多模态参考模式。",
    )
    video_urls: list[str] | None = Field(
        None,
        description="参考视频列表。仅支持具备视频参考能力的模型。",
    )
    audio_urls: list[str] | None = Field(
        None,
        description="参考音频列表。需与参考图片或参考视频搭配使用。",
    )


class GenerateVideoInputSpec(BaseModel):
    mode: Literal["text", "frames", "references"] = Field(
        "text",
        description="输入模式：text 为纯文生视频，frames 为首尾帧控制，references 为参考图/视频/音频模式。",
    )
    frames: GenerateVideoFrameInput | None = Field(
        None,
        description="首尾帧控制输入。仅在 mode=frames 时使用。",
    )
    references: GenerateVideoReferenceInput | None = Field(
        None,
        description="参考素材输入。仅在 mode=references 时使用。",
    )

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "text":
            if self.frames or self.references:
                raise ValueError("mode=text 时不要再提供 frames 或 references。")
            return self
        if self.mode == "frames":
            if not self.frames:
                raise ValueError("mode=frames 时必须提供 frames。")
            if self.references:
                raise ValueError("mode=frames 时不能同时提供 references。")
            if self.frames.last_image_url and not self.frames.first_image_url:
                raise ValueError("使用尾帧时必须同时提供首帧 first_image_url。")
            return self
        if not self.references:
            raise ValueError("mode=references 时必须提供 references。")
        if self.frames:
            raise ValueError("mode=references 时不能同时提供 frames。")
        if not (
            (self.references.image_urls or [])
            or (self.references.video_urls or [])
            or (self.references.audio_urls or [])
        ):
            raise ValueError("mode=references 时至少要提供一种参考素材。")
        if self.references.audio_urls and not (
            self.references.image_urls or self.references.video_urls
        ):
            raise ValueError("audio_urls 需要与 image_urls 或 video_urls 搭配使用。")
        return self


class GenerateVideoKlingOptions(BaseModel):
    mode: Literal["std", "pro", "4k"] | None = Field(
        None,
        description="Kling 专用模式。std 对应 720p，pro 对应 1080p，4k 对应 4k；若同时开启音频会自动切到对应音频档。",
    )


class GenerateVideoKlingV3Options(BaseModel):
    multi_shot: bool | None = Field(
        None,
        description="是否启用 Kling 3 多镜头分镜模式。",
    )
    shot_type: Literal["customize", "intelligence"] | None = Field(
        None,
        description="多镜头分镜方式：customize 或 intelligence。",
    )
    multi_prompt: list[GenerateVideoMultiPromptStep] | None = Field(
        None,
        description="自定义分镜列表。multi_shot=true 且 shot_type=customize 时使用。",
    )
    element_list: list[GenerateVideoElementRef] | None = Field(
        None,
        description="元素引用列表，可为角色/主体提供一致性参考。",
    )

    @model_validator(mode="after")
    def validate_multi_shot(self):
        if self.multi_shot and self.shot_type == "customize" and not self.multi_prompt:
            raise ValueError("multi_shot=true 且 shot_type=customize 时必须提供 multi_prompt。")
        return self


class GenerateVideoSeedance2Options(BaseModel):
    return_last_frame: bool | None = Field(
        None,
        description="是否在结果中返回最后一帧，便于连续生成。",
    )


class GenerateVideoModelOptions(BaseModel):
    kling: GenerateVideoKlingOptions | None = Field(
        None,
        description="Kling 系列模型专属参数。",
    )
    kling_v3: GenerateVideoKlingV3Options | None = Field(
        None,
        description="Kling 3 专属参数。",
    )
    seedance_2: GenerateVideoSeedance2Options | None = Field(
        None,
        description="Seedance 2.0 专属参数。",
    )


class GenerateVideoParams(BaseModel):
    prompt: str | None = Field(
        None,
        description="详细的视频生成提示词（请使用当前会话语言撰写）。参考素材驱动或 Kling 多镜头模式下可省略。",
    )
    aspect_ratio: str | None = Field(
        None, description="视频宽高比，如 16:9, 9:16, 1:1。省略时使用模型默认值。"
    )
    duration: int | None = Field(
        None, description="视频时长（秒），如 5 或 10。省略时使用模型支持的最短时长。"
    )
    output: GenerateVideoOutputOptions | None = Field(
        None,
        description="输出控制参数，如分辨率和是否生成音频。",
    )
    input: GenerateVideoInputSpec | None = Field(
        None,
        description="输入模式与输入素材。省略时默认按纯文生视频处理。",
    )
    model_options: GenerateVideoModelOptions | None = Field(
        None,
        description="模型专属参数。不同模型只读取各自对应的字段。",
    )
    negative_prompt: str | None = Field(
        None,
        description="负面提示词，用于排除不希望出现的内容。",
    )
    watermark: bool | None = Field(
        None,
        description="是否添加水印。",
    )

    @model_validator(mode="after")
    def validate_generation_mode(self):
        input_spec = self.input
        model_options = self.model_options
        has_reference_inputs = bool(input_spec and input_spec.mode != "text")
        has_multi_shot = bool(model_options and model_options.kling_v3 and model_options.kling_v3.multi_shot)
        if not self.prompt and not has_reference_inputs and not has_multi_shot:
            raise ValueError("prompt 不能为空；若只依赖参考素材，请通过 input 指定输入模式与素材。")
        return self


def _is_kling_model(model_name: str | None) -> bool:
    return str(model_name or "").lower().startswith("kling-")


def _is_seedance_2_model(model_name: str | None) -> bool:
    return str(model_name or "").lower().startswith("doubao-seedance-2.0")


def _normalize_audio_flag(generate_audio: bool | None, resolution: str | None) -> bool:
    normalized_resolution = str(resolution or "").strip().lower()
    return bool(generate_audio) or normalized_resolution.endswith("_audio")


def _resolve_kling_resolution(
    *,
    requested_resolution: str | None,
    kling_mode: str | None,
    audio_enabled: bool,
    fallback_resolution: str,
) -> str:
    mode_to_resolution = {
        "std": "720p",
        "pro": "1080p",
        "4k": "4k",
    }

    normalized_requested = str(requested_resolution or "").strip().lower() or None
    normalized_mode = str(kling_mode or "").strip().lower() or None
    if normalized_mode and normalized_mode not in mode_to_resolution:
        raise ValueError("kling_mode 仅支持 std、pro 或 4k。")

    if normalized_mode:
        resolved_base = mode_to_resolution[normalized_mode]
        if normalized_requested:
            requested_base = normalized_requested.replace("_audio", "")
            if requested_base != resolved_base:
                raise ValueError("kling_mode 与 resolution 冲突，请二选一或保持一致。")
    elif normalized_requested:
        resolved_base = normalized_requested.replace("_audio", "")
    else:
        resolved_base = str(fallback_resolution or "720p").strip().lower().replace("_audio", "")

    return f"{resolved_base}_audio" if audio_enabled else resolved_base


def _resolve_reference_urls(urls: list[str] | None, ctx: "HarnessContext") -> list[str]:
    resolved_urls: list[str] = []
    for url in urls or []:
        resolved = _resolve_reference_to_url(url, ctx)
        if resolved:
            resolved_urls.append(resolved)
    return resolved_urls


def _resolve_reference_to_url(
    url_or_path: str | None, ctx: "HarnessContext"
) -> str | None:
    if not url_or_path:
        return None

    if url_or_path.startswith(("http://", "https://")):
        return url_or_path
    if url_or_path.startswith("data:"):
        logger.warning("Skipping data URI reference for video generation task params")
        return None

    safe_local_path = resolve_safe_local_media_path(url_or_path, ctx)
    if safe_local_path is not None:
        uploaded_url = local_path_to_oss(str(safe_local_path))
        if uploaded_url:
            return uploaded_url
        logger.warning("Failed to upload local reference image to TOS: %s", safe_local_path)
        return None

    resolved = resolve_url_for_api(url_or_path, prefer="url")
    if resolved and resolved.get("type") == "url":
        return resolved["url"]
    if resolved and resolved.get("type") == "base64":
        logger.warning(
            "Reference image fell back to base64 while resolving URL for video generation: %s",
            url_or_path,
        )
        return None

    logger.warning("Reference image not found or could not be resolved to URL: %s", url_or_path)
    return None


def _extract_external_id(result: dict) -> str | None:
    data = result.get("data")
    if isinstance(data, list) and data:
        return data[0].get("task_id") or data[0].get("id")
    if isinstance(data, dict):
        return data.get("task_id") or data.get("id")
    return result.get("task_id")


def _build_canvas_item_for_generation(
    *,
    ctx: "HarnessContext",
    existing_artifact: dict | None,
    task_id: str,
    prompt: str,
    model_name: str,
    model_label: str | None,
    provider_code: str,
    aspect_ratio: str,
    resolution: str,
    duration: int,
    artifact_ref: str | None,
) -> dict | None:
    if ctx.runtime_profile != "canvas":
        return None

    agent_media_key = str(artifact_ref or task_id or "").strip() or None
    existing_canvas_item = (existing_artifact or {}).get("canvas_item")
    if isinstance(existing_canvas_item, dict):
        next_item = dict(existing_canvas_item)
        next_item.update({
            "task_id": task_id,
            "artifact_ref": artifact_ref,
            "agent_media_key": next_item.get("agent_media_key") or agent_media_key,
            "agent_conversation_id": next_item.get("agent_conversation_id") or ctx.conversation_id,
            "prompt": prompt,
            "model_name": model_name,
            "model_label": model_label,
            "provider_code": provider_code,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration": duration,
            "status": "generating",
            "url": "",
        })
        return next_item

    return build_canvas_generation_item(
        conversation_id=ctx.conversation_id,
        kind="video",
        task_id=task_id,
        prompt=prompt,
        model_name=model_name,
        model_label=model_label,
        provider_code=provider_code,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration=duration,
        result_url="",
        status="processing",
        artifact_ref=artifact_ref,
        position={"x": 0, "y": 0},
    )


def _existing_artifact_result(
    *,
    task: dict,
    artifact: dict,
    prompt: str,
    ctx: "HarnessContext",
) -> ToolResult:
    status = str(task.get("status") or artifact.get("status") or "processing")
    result_url = task.get("result_url") or artifact.get("result_url")
    task_id = str(task.get("task_id") or artifact.get("current_task_id") or "")
    retry_metadata = {
        "auto_retry_count": int((artifact or task).get("auto_retry_count") or 0),
        "auto_retry_max": int((artifact or task).get("auto_retry_max") or 3),
        "manual_retry_count": int((artifact or task).get("manual_retry_count") or 0),
    }
    async_execution = status in {"processing", "running", "pending"}
    preview_url = artifact.get("planned_result_url") or task.get("planned_result_url")
    message = (
        "不要再用同一个 artifact_ref 重复创建。"
        "你可以直接执行下一步动作；在回复中引用这个视频请使用 preview_url，写成 [查看视频](preview_url)，"
        "不要编造文件名或使用可能为空的 result_url。"
        "如果后续工具需要依赖这个媒体，请在下游依赖参数中使用 artifact_ref，运行时会自动等待。"
    )
    data = {
        "task_id": task_id,
        "artifact_ref": artifact.get("artifact_ref"),
        **retry_metadata,
        "status": status,
        "result_url": result_url,
        "artifact": build_artifact_metadata(result_url, ctx),
        "model_name": task.get("model_name"),
        "model_label": task.get("model_label"),
        "prompt": task.get("prompt") or prompt,
        "aspect_ratio": task.get("aspect_ratio"),
        "duration": task.get("duration"),
        "resolution": task.get("resolution"),
        "async_execution": async_execution,
        "do_not_repeat_same_generation": True,
        "duplicate_generation_blocked": True,
        "preview_url": preview_url,
        "next_action_hint": message,
        "message": message,
        "canvas_item": task.get("canvas_item") or artifact.get("canvas_item"),
    }
    return ToolResult(
        output=json.dumps(data, ensure_ascii=False),
        metadata={
            "task_id": task_id,
            "artifact_ref": artifact.get("artifact_ref"),
            **retry_metadata,
            "media_type": "video",
            "status": status,
            "result_url": result_url,
            "artifact": build_artifact_metadata(result_url, ctx),
            "prompt": data["prompt"],
            "model_name": data["model_name"],
            "model_label": data["model_label"],
            "aspect_ratio": data["aspect_ratio"],
            "duration": data["duration"],
            "resolution": data["resolution"],
            "async_execution": async_execution,
            "do_not_repeat_same_generation": True,
            "duplicate_generation_blocked": True,
            "preview_url": preview_url,
            "next_action_hint": message,
            "message": message,
            "canvas_item": data["canvas_item"],
        },
    )


def _retry_metadata(task: dict | None, artifact: dict | None) -> dict[str, int]:
    base = artifact or task or {}
    return {
        "auto_retry_count": int(base.get("auto_retry_count") or 0),
        "auto_retry_max": int(base.get("auto_retry_max") or 3),
        "manual_retry_count": int(base.get("manual_retry_count") or 0),
    }


def _resolved_output_metadata(
    output_options: GenerateVideoOutputOptions,
    *,
    resolution: str,
    audio_enabled: bool,
) -> dict[str, Any]:
    payload = output_options.model_dump(exclude_none=True)
    payload["resolution"] = resolution
    if audio_enabled:
        payload["generate_audio"] = True
    else:
        payload.pop("generate_audio", None)
    return payload


def _resolved_model_options_metadata(
    model_options: GenerateVideoModelOptions,
    *,
    resolution_overrides_kling_mode: bool,
) -> dict[str, Any] | None:
    payload = model_options.model_dump(exclude_none=True)
    if resolution_overrides_kling_mode:
        kling_options = payload.get("kling")
        if isinstance(kling_options, dict):
            kling_options.pop("mode", None)
            if not kling_options:
                payload.pop("kling", None)
    return payload or None


async def submit_video_generation(
    *,
    params: GenerateVideoParams,
    ctx: "HarnessContext",
    artifact_ref: str | None = None,
    retry_source: str | None = None,
) -> ToolResult:
    from fastapi import HTTPException
    from app.services.agent_harness.core.utils import generation_store
    from app.services.agent_harness.core.utils.generation_item_events import (
        emit_generation_item_completed,
        emit_generation_item_started,
    )

    model_name = ctx.video_model
    provider_code = ctx.video_provider or "builtin"

    if not model_name:
        return ToolResult(
            output=json.dumps(
                {
                    "error": (
                        "Missing harness video_model. "
                        "generate_video only uses the frontend-selected video model."
                    )
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )

    if provider_code != "builtin":
        return ToolResult(
            output=json.dumps(
                {
                    "error": (
                        "Only the builtin provider is supported in harness. "
                        "Only APIMart is supported in harness video generation."
                    )
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )

    try:
        await resolve_user_apimart_key_for_context(ctx.user_id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return ToolResult(
            output=json.dumps(
                {"error": detail.get("message", "APIMart Key is not configured.")},
                ensure_ascii=False,
            ),
            is_error=True,
        )

    tool_schema = build_video_tool_schema(provider_code, model_name)
    input_spec = params.input or GenerateVideoInputSpec()
    output_options = params.output or GenerateVideoOutputOptions()
    model_options = params.model_options or GenerateVideoModelOptions()
    frame_input = input_spec.frames
    reference_input = input_spec.references
    kling_options = model_options.kling
    kling_v3_options = model_options.kling_v3
    seedance2_options = model_options.seedance_2

    if input_spec.mode == "frames" and not tool_schema.get("supports_frame_images"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持首尾帧输入。"}, ensure_ascii=False), is_error=True)
    if input_spec.mode == "references":
        if reference_input and reference_input.image_urls and not tool_schema.get("supports_reference_image_list"):
            return ToolResult(output=json.dumps({"error": "当前模型不支持参考图片模式。"}, ensure_ascii=False), is_error=True)
        if reference_input and reference_input.video_urls and not tool_schema.get("supports_reference_video"):
            return ToolResult(output=json.dumps({"error": "当前模型不支持参考视频。"}, ensure_ascii=False), is_error=True)
        if reference_input and reference_input.audio_urls and not tool_schema.get("supports_reference_audio"):
            return ToolResult(output=json.dumps({"error": "当前模型不支持参考音频。"}, ensure_ascii=False), is_error=True)
    if seedance2_options and seedance2_options.return_last_frame and not tool_schema.get("supports_return_last_frame"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持 return_last_frame。"}, ensure_ascii=False), is_error=True)
    if kling_options and kling_options.mode and not tool_schema.get("supports_kling_mode"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持 model_options.kling。"}, ensure_ascii=False), is_error=True)
    if kling_v3_options and kling_v3_options.multi_shot and not tool_schema.get("supports_multi_shot"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持 model_options.kling_v3.multi_shot。"}, ensure_ascii=False), is_error=True)
    if kling_v3_options and kling_v3_options.element_list and not tool_schema.get("supports_element_list"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持 model_options.kling_v3.element_list。"}, ensure_ascii=False), is_error=True)
    if output_options.generate_audio and not tool_schema.get("supports_generate_audio"):
        return ToolResult(output=json.dumps({"error": "当前模型不支持 output.generate_audio。"}, ensure_ascii=False), is_error=True)

    prompt_text = (params.prompt or "").strip()
    first_frame_url = _resolve_reference_to_url(frame_input.first_image_url if frame_input else None, ctx)
    last_frame_url = _resolve_reference_to_url(frame_input.last_image_url if frame_input else None, ctx)
    reference_image_urls = _resolve_reference_urls(reference_input.image_urls if reference_input else None, ctx)
    has_frame_inputs = bool(first_frame_url or last_frame_url)
    has_reference_images = bool(reference_image_urls)
    has_image_inputs = bool(has_frame_inputs or has_reference_images)

    defaults = resolve_harness_video_defaults(
        model_name, provider_code, has_reference_image=has_image_inputs
    )
    preferences = resolve_video_generation_preferences(
        ctx.model_preferences,
        provider_code=provider_code,
        model_name=model_name,
    )
    preferred_resolution = None if retry_source else preferences.resolution
    preferred_aspect_ratio = None if retry_source else preferences.aspect_ratio
    preferred_duration = None if retry_source else preferences.duration
    effective_output_resolution = preferred_resolution or output_options.resolution
    requested_audio = (
        None
        if preferred_resolution and _is_kling_model(model_name)
        else output_options.generate_audio
    )
    audio_enabled = _normalize_audio_flag(requested_audio, effective_output_resolution)
    try:
        requested_resolution = (
            _resolve_kling_resolution(
                requested_resolution=effective_output_resolution,
                kling_mode=(
                    None
                    if preferred_resolution
                    else kling_options.mode if kling_options else None
                ),
                audio_enabled=audio_enabled,
                fallback_resolution=str(defaults["resolution"]),
            )
            if _is_kling_model(model_name)
            else (effective_output_resolution or str(defaults["resolution"]))
        )
    except ValueError as exc:
        return ToolResult(
            output=json.dumps({"error": str(exc)}, ensure_ascii=False),
            is_error=True,
        )

    selection = resolve_video_generation_selection(
        config=get_model_config(provider_code, "text2video", model_name),
        aspect_ratio=preferred_aspect_ratio or params.aspect_ratio or str(defaults["aspect_ratio"]),
        resolution=requested_resolution,
        duration=preferred_duration or params.duration or int(defaults["duration"]),
        has_reference_image=has_image_inputs,
        preferred_aspect_ratio=str(defaults["aspect_ratio"]),
        preferred_resolution=str(defaults["resolution"]),
        preferred_duration=int(defaults["duration"]),
    )
    aspect_ratio = str(selection["aspect_ratio"])
    duration = int(selection["duration"])
    resolution = str(selection["resolution"])
    output_metadata = _resolved_output_metadata(
        output_options,
        resolution=resolution,
        audio_enabled=audio_enabled,
    )
    model_options_metadata = _resolved_model_options_metadata(
        model_options,
        resolution_overrides_kling_mode=bool(preferred_resolution and _is_kling_model(model_name)),
    )
    video_task_type = "image2video" if input_spec.mode != "text" else "text2video"
    model_label = resolve_model_label(
        model_name,
        provider_code=provider_code,
        bucket="text2video",
    )

    asset_id = None
    existing_artifact = generation_store.read_artifact(ctx, artifact_ref) if artifact_ref else None
    if artifact_ref and not existing_artifact:
        return ToolResult(
            output=json.dumps(
                {
                    "error": "unknown_artifact_ref",
                    "artifact_ref": artifact_ref,
                    "message": "Unknown generated artifact reference.",
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )
    if existing_artifact:
        current_task_id = str(existing_artifact.get("current_task_id") or "").strip()
        current_task = await generation_store.read_generation_task(ctx, current_task_id) if current_task_id else None
        current_status = str((current_task or existing_artifact).get("status") or "").strip().lower()
        if current_task and current_status in {"processing", "running", "pending", "completed"}:
            return _existing_artifact_result(
                task=current_task,
                artifact=existing_artifact,
                prompt=prompt_text,
                ctx=ctx,
            )
        artifact_ref = str(existing_artifact["artifact_ref"])
        planned_result_url = str(existing_artifact.get("planned_result_url") or "")
        asset_id = str(existing_artifact.get("asset_id") or "")
    else:
        artifact_ref = generation_store.new_artifact_ref()
        asset_id = f"generated_video_{artifact_ref.removeprefix('artifact_ref:')[:16]}"
        planned_result_url = planned_reference_asset_path(
            ctx.user_id,
            ctx.conversation_id,
            asset_id=asset_id,
            extension="mp4",
        )
        generation_store.create_or_read_artifact(
            ctx,
            kind="video",
            planned_result_url=planned_result_url,
            artifact_ref=artifact_ref,
        )
        generation_store.update_artifact(ctx, artifact_ref, {"asset_id": asset_id})

    artifact = generation_store.read_artifact(ctx, artifact_ref) or {}
    retry_metadata = _retry_metadata(None, artifact)
    scope = ctx.get_tool_stream_scope() or {}
    tool_call_id = str(scope.get("tool_call_id") or "").strip() or None
    presentation_scope = normalize_presentation_scope(scope)
    try:
        presentation_order = int(scope.get("order") or 0)
    except (TypeError, ValueError):
        presentation_order = 0
    retry_request_suffix = (
        f":retry:{retry_source}:{retry_metadata['auto_retry_count']}:{retry_metadata['manual_retry_count']}"
        if retry_source
        else ""
    )
    client_request_id = f"harness:video:{ctx.conversation_id}:{tool_call_id or artifact_ref}{retry_request_suffix}"
    metadata_params = {
        "agent_run_id": ctx.run_id,
        "agent_conversation_id": ctx.conversation_id,
        "conversation_id": ctx.conversation_id,
        "runtime_profile": ctx.runtime_profile,
        "skill_id": ctx.skill_id,
        "artifact_mode": ctx.artifact_mode,
        "artifact_ref": artifact_ref,
        "asset_id": asset_id,
        "tool_call_id": tool_call_id,
        "planned_result_url": planned_result_url,
        "parent_usage_log_id": ctx.parent_usage_log_id,
        "retry_source": retry_source,
        "output": output_metadata,
        "input": params.input.model_dump(exclude_none=True) if params.input else {"mode": "text"},
        "model_options": model_options_metadata,
        **retry_metadata,
    }
    if presentation_scope:
        metadata_params["presentation_scope"] = presentation_scope
        metadata_params["presentation_message_key"] = presentation_scope.get("message_key")
        metadata_params["presentation_parent_block_key"] = presentation_scope.get("parent_block_key")
    if presentation_order > 0:
        metadata_params["presentation_order"] = presentation_order
    reference_diagnostics = message_reference_diagnostics(
        ctx,
        used_reference_image_count=len(reference_image_urls) + int(bool(first_frame_url)) + int(bool(last_frame_url)),
    )
    if reference_diagnostics:
        metadata_params["reference_diagnostics"] = reference_diagnostics

    from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory

    t0 = time.monotonic()
    session_factory = get_harness_db_session_factory()
    task_type = "image2video" if (reference_image_urls or first_frame_url or last_frame_url) else "text2video"
    async with session_factory() as db:
        intake_result = await GenerationIntakeService(db).submit_video(
            GenerationIntakeRequest(
                user_id=ctx.user_id,
                project_id=ctx.project_id if ctx.runtime_profile == "canvas" else None,
                prompt=prompt_text,
                model_name=model_name,
                provider_code=provider_code,
                task_type=task_type,
                aspect_ratio=aspect_ratio,
                duration=duration,
                quality=resolution,
                resolution=resolution,
                audio=audio_enabled,
                image_urls=reference_image_urls or None,
                first_frame_image=first_frame_url,
                tail_frame_image=last_frame_url,
                return_last_frame=seedance2_options.return_last_frame if seedance2_options else None,
                negative_prompt=params.negative_prompt,
                watermark=params.watermark,
                multi_shot=kling_v3_options.multi_shot if kling_v3_options else None,
                shot_type=kling_v3_options.shot_type if kling_v3_options else None,
                multi_prompt=[
                    item.model_dump(exclude_none=True)
                    for item in (kling_v3_options.multi_prompt or [])
                ] if kling_v3_options and kling_v3_options.multi_prompt else None,
                element_list=[
                    item.model_dump(exclude_none=True)
                    for item in (kling_v3_options.element_list or [])
                ] if kling_v3_options and kling_v3_options.element_list else None,
                planned_result_url=planned_result_url,
                client_request_id=client_request_id,
                reserve_billing=False,
                metadata_params=metadata_params,
            )
        )
        task = intake_result.task

    task_id = str(task.id)
    canvas_item = _build_canvas_item_for_generation(
        ctx=ctx,
        existing_artifact=existing_artifact,
        task_id=task_id,
        prompt=prompt_text,
        model_name=model_name,
        model_label=model_label,
        provider_code=provider_code,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration=duration,
        artifact_ref=artifact_ref,
    )
    canvas_patch = await persist_agent_canvas_item_patch(
        ctx,
        canvas_item,
        "generating",
    )
    canvas_item = canvas_patch.canvas_item if canvas_patch else canvas_item
    canvas_revision = canvas_patch.canvas_revision if canvas_patch else None
    canvas_item_deleted = canvas_patch is not None and canvas_patch.canvas_item is None
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "status": "processing",
            "current_task_id": task_id,
            "error": None,
            "canvas_item": canvas_item,
            "canvas_revision": canvas_revision,
            "canvas_item_deleted": canvas_item_deleted,
            **(
                {
                    "presentation_scope": presentation_scope,
                    "presentation_message_key": presentation_scope.get("message_key"),
                    "presentation_parent_block_key": presentation_scope.get("parent_block_key"),
                    **({"presentation_order": presentation_order} if presentation_order > 0 else {}),
                }
                if presentation_scope
                else {}
            ),
        },
    )
    await emit_generation_item_started(
        ctx,
        task,
        artifact_ref=artifact_ref,
        canvas_item=canvas_item,
        kind="video",
        canvas_revision=canvas_revision,
        canvas_item_deleted=canvas_item_deleted,
    )
    if task.status == "failed":
        err_msg = task.error_message or "Video generation failed."
        failed_artifact = generation_store.mark_artifact_failed(
            ctx,
            artifact_ref,
            error=err_msg,
            current_task_id=task_id,
        )
        failed_canvas_source_item = failed_artifact.get("canvas_item") if isinstance(failed_artifact, dict) else canvas_item
        failed_canvas_patch = await persist_agent_canvas_item_patch(
            ctx,
            failed_canvas_source_item,
            "failed",
        )
        failed_canvas_item = failed_canvas_source_item
        failed_canvas_revision = canvas_revision
        failed_canvas_item_deleted = canvas_item_deleted
        if failed_canvas_patch:
            failed_canvas_item = failed_canvas_patch.canvas_item
            failed_canvas_revision = failed_canvas_patch.canvas_revision
            failed_canvas_item_deleted = failed_canvas_patch.canvas_item is None
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "canvas_item": failed_canvas_item,
                "canvas_revision": failed_canvas_revision,
                "canvas_item_deleted": failed_canvas_item_deleted,
            },
        )
        await emit_generation_item_completed(
            ctx,
            task,
            artifact_ref=artifact_ref,
            canvas_item=failed_canvas_item,
            kind="video",
            status="failed",
            error=err_msg,
            canvas_revision=failed_canvas_revision,
            canvas_item_deleted=failed_canvas_item_deleted,
        )
        return ToolResult(
            output=json.dumps(
                {
                    "task_id": task_id,
                    "artifact_ref": artifact_ref,
                    **_retry_metadata(None, failed_artifact),
                    "canvas_item": failed_canvas_item,
                    "canvas_revision": failed_canvas_revision,
                    "canvas_item_deleted": failed_canvas_item_deleted,
                    "error": err_msg,
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )

    result_url: str | None = task.result_url
    status = task.status

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "status": status,
            "current_task_id": task_id,
            "result_url": result_url if status == "completed" else None,
            "error": None,
        },
    )
    if status == "completed":
        completed_canvas_patch = await persist_agent_canvas_item_patch(
            ctx,
            canvas_item,
            "completed",
            result_url=result_url,
        )
        if completed_canvas_patch:
            canvas_item = completed_canvas_patch.canvas_item
            canvas_revision = completed_canvas_patch.canvas_revision
            canvas_item_deleted = completed_canvas_patch.canvas_item is None
        generation_store.update_artifact(
            ctx,
            artifact_ref,
            {
                "canvas_item": canvas_item,
                "canvas_revision": canvas_revision,
                "canvas_item_deleted": canvas_item_deleted,
            },
        )
        await emit_generation_item_completed(
            ctx,
            task,
            artifact_ref=artifact_ref,
            canvas_item=canvas_item,
            kind="video",
            status="completed",
            result_url=result_url,
            canvas_revision=canvas_revision,
            canvas_item_deleted=canvas_item_deleted,
        )
    result_data = {
        "task_id": task_id,
        "artifact_ref": artifact_ref,
        **retry_metadata,
        "status": status,
        "result_url": result_url,
        "artifact": build_artifact_metadata(result_url, ctx),
        "model_name": model_name,
        "model_label": model_label,
        "prompt": params.prompt,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
        "resolution": resolution,
        "async_execution": status == "processing",
        "do_not_repeat_same_generation": status == "processing",
        "preview_url": planned_result_url,
        "canvas_item": canvas_item,
        "canvas_revision": canvas_revision,
        "canvas_item_deleted": canvas_item_deleted,
        "next_action_hint": (
            "在你给用户的回复中引用这个视频时，请直接使用 preview_url 字段的值，"
            "例如写成 [查看视频](preview_url)。preview_url 是当前会话已分配的稳定路径，"
            "视频落盘前用户会看到占位内容，落盘后自动可播放。"
            "禁止根据 prompt 或场景编造文件名/路径，也不要使用 result_url（异步阶段它可能为空）。"
            "不要重复调用 generate_video 获取同一个结果；"
            "如果后续工具需要依赖这个媒体，请在下游依赖参数中使用 artifact_ref，运行时会自动等待。"
        ),
        "message": (
            f"视频生成任务已提交成功，可继续使用 artifact_ref (ID: {task_id}, 状态: {status})。"
        ),
    }

    return ToolResult(
        output=json.dumps(result_data, ensure_ascii=False),
        metadata={
            "task_id": task_id,
            "artifact_ref": artifact_ref,
            **retry_metadata,
            "media_type": "video",
            "status": status,
            "result_url": result_url,
            "artifact": build_artifact_metadata(result_url, ctx),
            "prompt": params.prompt,
            "model_name": model_name,
            "model_label": model_label,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "async_execution": result_data["async_execution"],
            "do_not_repeat_same_generation": result_data["do_not_repeat_same_generation"],
            "preview_url": planned_result_url,
            "canvas_item": canvas_item,
            "canvas_revision": canvas_revision,
            "canvas_item_deleted": canvas_item_deleted,
            "next_action_hint": result_data["next_action_hint"],
            "message": result_data["message"],
        },
    )


class GenerateVideoTool(BaseTool):
    """根据文本提示词生成视频。"""

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        from app.services.agent_harness.core.context import get_current_context

        base = (
            "根据文本提示词生成视频。"
            "请使用当前会话语言撰写详细的描述性提示词。"
            "输入结构分为三层：公共参数、input 输入模式、model_options 模型专属参数。"
            "如需首尾帧控制，请使用 input.mode=frames；如需参考图/视频/音频，请使用 input.mode=references。"
            "When the latest user message includes structured media references, copy the exact tool_reference "
            "from relevant image references into existing fields only: input.frames.first_image_url/last_image_url "
            "for frame-driven video, or input.references.image_urls for reference-image video. Do not invent "
            "reference_ids or new tool fields."
            "Kling 专属参数放到 model_options.kling；Kling 3 多镜头参数放到 model_options.kling_v3；Seedance 2.0 连续视频参数放到 model_options.seedance_2。"
            "当本工具成功返回 artifact_ref 后，就把它当作可继续使用的媒体句柄。"
            "当任务是在当前会话中继续延展、动画化或改编一份已确认的视觉结果时，应优先沿用该结果的引用继续推进，而不是只根据文字复述重新生成一个平行版本。"
            "不要复制生成结果里的 URL；若后续工具需要依赖这个媒体，请在下游依赖参数中使用 artifact_ref，"
            "运行时会在执行前自动等待。"
        )
        try:
            ctx = get_current_context()
            return base + build_video_tool_schema(ctx.video_provider or "builtin", ctx.video_model).get("description", "")
        except Exception:
            return base + "工具会根据当前模型自动选择兼容的视频分辨率、比例、时长和输入限制，超出范围时自动收敛到接近的可用设置。"

    @property
    def input_model(self) -> type[BaseModel]:
        return GenerateVideoParams

    def get_input_schema(self, language: str = "zh") -> dict:
        schema = super().get_input_schema(language)
        from app.services.agent_harness.core.context import get_current_context

        try:
            ctx = get_current_context()
            tool_schema = build_video_tool_schema(ctx.video_provider or "builtin", ctx.video_model)
        except Exception:
            tool_schema = {"aspect_ratios": [], "resolutions": [], "durations": [], "description": ""}

        properties = schema.get("properties", {})
        schema_defs = schema.get("$defs", {})
        output_def = schema_defs.get("GenerateVideoOutputOptions", {})
        input_def = schema_defs.get("GenerateVideoInputSpec", {})
        frame_def = schema_defs.get("GenerateVideoFrameInput", {})
        reference_def = schema_defs.get("GenerateVideoReferenceInput", {})
        model_options_def = schema_defs.get("GenerateVideoModelOptions", {})
        kling_def = schema_defs.get("GenerateVideoKlingOptions", {})
        kling_v3_def = schema_defs.get("GenerateVideoKlingV3Options", {})
        seedance2_def = schema_defs.get("GenerateVideoSeedance2Options", {})
        aspect_ratios = tool_schema.get("aspect_ratios") or []
        resolutions = tool_schema.get("resolutions") or []
        durations = tool_schema.get("durations") or []
        if "aspect_ratio" in properties:
            if aspect_ratios:
                properties["aspect_ratio"]["enum"] = aspect_ratios
            supported = ", ".join(aspect_ratios) if aspect_ratios else (
                "自动按模型处理" if language == "zh" else "handled automatically by the model"
            )
            properties["aspect_ratio"]["description"] = (
                f"视频宽高比。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用比例。"
                if language == "zh"
                else f"Video aspect ratio. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported ratio."
            )
        if "resolution" in properties:
            if resolutions:
                properties["resolution"]["enum"] = resolutions
            supported = ", ".join(resolutions) if resolutions else (
                "自动按模型处理" if language == "zh" else "handled automatically by the model"
            )
            properties["resolution"]["description"] = (
                f"视频输出分辨率。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用分辨率。"
                if language == "zh"
                else f"Video output resolution. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported resolution."
            )
        if "duration" in properties:
            if durations:
                properties["duration"]["enum"] = [int(duration) for duration in durations]
            supported = ", ".join(durations) if durations else (
                "自动按模型处理" if language == "zh" else "handled automatically by the model"
            )
            properties["duration"]["description"] = (
                f"视频时长（秒）。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用时长。"
                if language == "zh"
                else f"Video duration in seconds. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported duration."
            )

        if isinstance(output_def.get("properties"), dict):
            output_props = output_def["properties"]
            if "resolution" in output_props:
                if resolutions:
                    output_props["resolution"]["enum"] = resolutions
                supported = ", ".join(resolutions) if resolutions else (
                    "自动按模型处理" if language == "zh" else "handled automatically by the model"
                )
                output_props["resolution"]["description"] = (
                    f"视频输出分辨率。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用分辨率。"
                    if language == "zh"
                    else f"Video output resolution. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported resolution."
                )
            if not tool_schema.get("supports_generate_audio"):
                output_props.pop("generate_audio", None)

        if isinstance(input_def.get("properties"), dict):
            input_props = input_def["properties"]
            input_modes = ["text"]
            if tool_schema.get("supports_frame_images"):
                input_modes.append("frames")
            if (
                tool_schema.get("supports_reference_image_list")
                or tool_schema.get("supports_reference_video")
                or tool_schema.get("supports_reference_audio")
            ):
                input_modes.append("references")
            if "mode" in input_props:
                input_props["mode"]["enum"] = input_modes
            if not tool_schema.get("supports_frame_images"):
                input_props.pop("frames", None)
            if "references" in input_props and input_modes == ["text", "frames"]:
                input_props.pop("references", None)

        if isinstance(reference_def.get("properties"), dict):
            reference_props = reference_def["properties"]
            if not tool_schema.get("supports_reference_image_list"):
                reference_props.pop("image_urls", None)
            if not tool_schema.get("supports_reference_video"):
                reference_props.pop("video_urls", None)
            if not tool_schema.get("supports_reference_audio"):
                reference_props.pop("audio_urls", None)

        if isinstance(model_options_def.get("properties"), dict):
            model_options_props = model_options_def["properties"]
            if not tool_schema.get("supports_kling_mode"):
                model_options_props.pop("kling", None)
            if not tool_schema.get("supports_multi_shot") and not tool_schema.get("supports_element_list"):
                model_options_props.pop("kling_v3", None)
            if not tool_schema.get("supports_return_last_frame"):
                model_options_props.pop("seedance_2", None)

        if isinstance(kling_v3_def.get("properties"), dict):
            kling_v3_props = kling_v3_def["properties"]
            if not tool_schema.get("supports_multi_shot"):
                kling_v3_props.pop("multi_shot", None)
                kling_v3_props.pop("shot_type", None)
                kling_v3_props.pop("multi_prompt", None)
            if not tool_schema.get("supports_element_list"):
                kling_v3_props.pop("element_list", None)

        if not tool_schema.get("supports_kling_mode"):
            schema_defs.pop("GenerateVideoKlingOptions", None)
        if not (tool_schema.get("supports_multi_shot") or tool_schema.get("supports_element_list")):
            schema_defs.pop("GenerateVideoKlingV3Options", None)
        if not tool_schema.get("supports_return_last_frame"):
            schema_defs.pop("GenerateVideoSeedance2Options", None)
        if not tool_schema.get("supports_frame_images"):
            schema_defs.pop("GenerateVideoFrameInput", None)
        if not (
            tool_schema.get("supports_reference_image_list")
            or tool_schema.get("supports_reference_video")
            or tool_schema.get("supports_reference_audio")
        ):
            schema_defs.pop("GenerateVideoReferenceInput", None)

        return schema

    async def execute(
        self, params: GenerateVideoParams, ctx: "HarnessContext"
    ) -> ToolResult:
        return await submit_video_generation(params=params, ctx=ctx)

