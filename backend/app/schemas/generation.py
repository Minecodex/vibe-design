from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.generator_capabilities import (
    get_allowed_video_durations,
    get_image_model_capability,
    get_video_model_capability,
    is_audio_resolution,
    normalize_image_urls,
    normalize_video_resolution,
)


class GenerateImageRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt: str
    model_name: str
    provider_code: str
    aspect_ratio: str = "1:1"
    resolution: str = "1K"
    image_url: str | None = None
    image_urls: list[str] | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def validate_image_inputs(self):
        normalized_urls = self.image_urls or normalize_image_urls(self.image_url)
        self.image_urls = normalized_urls or None
        if normalized_urls:
            self.image_url = normalized_urls[0]

        capability = get_image_model_capability(self.model_name, self.provider_code)
        max_reference_images = capability.get("max_reference_images")
        if max_reference_images and len(normalized_urls) > max_reference_images:
            raise ValueError(f"当前模型最多支持 {max_reference_images} 张参考图")
        return self


class GenerateVideoRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt: str
    model_name: str
    provider_code: str
    aspect_ratio: str = "16:9"
    duration: int = 5
    quality: str = "720p"
    resolution: str | None = None
    audio: bool = False
    image_url: str | None = None
    image_tail_url: str | None = None
    first_frame_image: str | None = None
    tail_frame_image: str | None = None
    image_urls: list[str] | None = None
    reference_video_urls: list[str] | None = None
    reference_audio_urls: list[str] | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def validate_video_inputs(self):
        capability = get_video_model_capability(self.model_name, self.provider_code)
        if self.reference_video_urls:
            raise ValueError("当前版本不支持参考视频输入")
        if self.reference_audio_urls:
            raise ValueError("当前版本不支持参考音频输入")
        reference_urls = self.image_urls or []
        raw_first_frame = self.first_frame_image or self.image_url
        raw_tail_frame = self.tail_frame_image or self.image_tail_url
        frame_urls = normalize_image_urls(raw_first_frame, raw_tail_frame)
        normalized_urls = reference_urls or frame_urls

        self.image_urls = reference_urls or None
        if not reference_urls and frame_urls and not capability.get("image_modes_conflict"):
            self.image_urls = frame_urls
        self.first_frame_image = raw_first_frame or None
        self.tail_frame_image = raw_tail_frame or None
        if self.first_frame_image:
            self.image_url = self.first_frame_image
        if self.tail_frame_image:
            self.image_tail_url = self.tail_frame_image

        if capability.get("image_modes_conflict") and reference_urls and frame_urls:
            raise ValueError("当前模型不支持同时使用参考图和首尾帧")

        if capability.get("disallow_reference_mode") and len(reference_urls) >= 3:
            raise ValueError("当前模型不支持参考图模式")

        max_image_inputs = capability.get("max_image_inputs")
        if max_image_inputs and len(reference_urls) > max_image_inputs:
            raise ValueError(f"当前模型最多支持 {max_image_inputs} 张参考图")

        resolved_resolution = normalize_video_resolution(self.resolution or self.quality)
        audio_enabled = bool(self.audio or is_audio_resolution(resolved_resolution))
        has_first_frame = bool(self.first_frame_image)
        has_tail_frame = bool(self.tail_frame_image)

        if (
            has_tail_frame
            and capability.get("requires_first_frame_for_tail_frame")
            and not has_first_frame
        ):
            raise ValueError("当前模型使用尾帧时必须同时提供首帧")

        if audio_enabled and capability.get("supports_audio") is False:
            raise ValueError("当前模型不支持音频生成")

        audio_allowed_sizes = {
            normalize_video_resolution(value)
            for value in (capability.get("audio_allowed_sizes") or [])
            if value
        }
        if audio_enabled and audio_allowed_sizes and resolved_resolution not in audio_allowed_sizes:
            raise ValueError("当前模型仅在 pro 模式下支持音频生成")

        tail_frame_allowed_sizes = {
            normalize_video_resolution(value)
            for value in (capability.get("tail_frame_allowed_sizes") or [])
            if value
        }
        if has_tail_frame and audio_enabled and capability.get("audio_tail_frame_mutually_exclusive"):
            raise ValueError("当前模型的尾帧控制与音频生成互斥")

        if has_tail_frame and tail_frame_allowed_sizes and resolved_resolution not in tail_frame_allowed_sizes:
            raise ValueError("当前模型仅在 pro 模式下支持尾帧控制")

        if (
            normalized_urls
            and capability.get("disallow_manual_aspect_ratio_with_images")
            and "aspect_ratio" in self.model_fields_set
        ):
            raise ValueError("当前模型在使用图片时不支持手动设置画幅比例")

        allowed_durations = get_allowed_video_durations(self.model_name, normalized_urls, self.provider_code)
        if allowed_durations and self.duration not in allowed_durations:
            duration_text = ", ".join(f"{duration}s" for duration in allowed_durations)
            raise ValueError(f"当前模型仅支持以下时长: {duration_text}")
        return self


class RetryGenerationTaskRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt: str | None = None
    model_name: str | None = None
    provider_code: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None
    quality: str | None = None
    audio: bool | None = None
    image_url: str | None = None
    image_urls: list[str] | None = None
    first_frame_image: str | None = None
    tail_frame_image: str | None = None


class GenerateContentRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    messages: list[dict]
    temperature: float = 1.0
    max_tokens: int = 0


class TextRedrawSegment(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    text: str
    order: int


class TextRedrawExtractRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_url: str


class TextRedrawExtractResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    segments: list[TextRedrawSegment]


class TextRedrawSubmitRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_image_url: str
    original_segments: list[TextRedrawSegment]
    edited_segments: list[TextRedrawSegment]
    source_width: int | None = None
    source_height: int | None = None

    @model_validator(mode="after")
    def validate_matching_segments(self):
        original_ids = [segment.id for segment in self.original_segments]
        edited_ids = [segment.id for segment in self.edited_segments]
        if original_ids != edited_ids:
            raise ValueError("text redraw segment ids must match")
        return self


class GenerateImageEraseRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_image_url: str
    source_width: int
    source_height: int


class GenerateContentResponse(BaseModel):
    choices: list[dict] | None = None
    usage: dict | None = None


class GenerationTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    project_id: int | None
    task_type: str
    provider_code: str
    model_name: str
    model_label: str | None = None
    prompt: str
    status: str
    progress: int = 0
    client_request_id: str | None = None
    external_task_id: str | None = None
    builtin_provider_code: str | None = None
    provider_request_id: str | None = None
    provider_trace_id: str | None = None
    result_url: str | None = None
    result_urls: list[str] | None = None
    error_message: str | None = None
    params: dict | None = None
    created_at: datetime
    updated_at: datetime


class RecoverGenerationTaskItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    client_request_id: str
    task_type: str


class RecoverGenerationTasksRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    items: list[RecoverGenerationTaskItem]


class RecoverGenerationTasksResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    tasks: dict[str, GenerationTaskRead]


class GenerateSpatialAngleRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_image_url: str
    source_width: int
    source_height: int
    x: int
    y: int
    scale: str


class GenerateHDUpscaleRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    source_image_url: str
    source_width: int
    source_height: int


class GenerateHDUpscaleResponse(BaseModel):
    task: GenerationTaskRead
    calculated_width: int
    calculated_height: int
