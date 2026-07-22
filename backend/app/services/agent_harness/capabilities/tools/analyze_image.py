"""Image analysis tool for the Harness agent."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from app.core.config import (
    HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_CHARS,
    HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_INTERVAL_SECONDS,
)
from app.core.default_models import (
    get_default_image_analysis_model,
    get_default_image_analysis_provider,
)
from app.services.multimodal_service import MultimodalService

from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory
from app.services.agent_harness.runtime.eventing.event_writer import append_harness_event, enrich_harness_event_payload
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.core.utils.media_utils import (
    local_path_to_base64,
    resolve_safe_local_media_path,
    resolve_url_for_api,
)
from app.services.agent_harness.agent_resources.file_io import run_file_io
from ._internal.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

logger = logging.getLogger(__name__)


DEFAULT_ANALYSIS_QUESTION = "请详细描述这张图片的内容。"
_IMAGE_ATTACHMENT_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
}


def _stream_delta_flush_interval() -> float:
    return max(float(HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_INTERVAL_SECONDS), 0.1)


def _stream_delta_flush_chars() -> int:
    return max(int(HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_CHARS), 64)


class AnalyzeImageParams(BaseModel):
    image_url: str = Field(
        ...,
        description=(
            "要分析的图片。支持 HTTP(S) URL、data URI、references/inputs/...、"
            "references/generated/...，以及当前会话工作区中的相对路径。"
        ),
    )
    question: str | None = Field(
        None,
        description="可选分析问题。默认为详细描述图片内容。",
    )


def _looks_like_image_reference(value: str) -> bool:
    normalized = str(value or "").strip().split("?", 1)[0].split("#", 1)[0]
    suffix = Path(normalized).suffix.lower()
    return suffix in _IMAGE_ATTACHMENT_SUFFIXES


def _attachment_is_user_image(attachment: Any) -> bool:
    if not isinstance(attachment, dict):
        return False
    attachment_type = str(attachment.get("type") or "").strip().lower()
    if attachment_type == "image":
        return True
    mime_type = str(attachment.get("mime_type") or attachment.get("mime") or "").strip().lower()
    if mime_type.startswith("image/"):
        return True
    for candidate in (
        attachment.get("url"),
        attachment.get("path"),
        attachment.get("name"),
        attachment.get("filename"),
    ):
        if _looks_like_image_reference(str(candidate or "")):
            return True
    return False


def _conversation_has_user_image_input(ctx: "HarnessContext", *, max_messages: int = 120) -> bool:
    from app.services.agent_harness.workspace.conversation.conversation_service import iter_messages_reverse

    try:
        for message in iter_messages_reverse(
            int(ctx.user_id),
            str(ctx.conversation_id),
            page_size=40,
            max_messages=max_messages,
        ):
            if str(message.get("role") or "").strip().lower() != "user":
                continue
            attachments = message.get("attachments")
            if not isinstance(attachments, list):
                continue
            if any(_attachment_is_user_image(attachment) for attachment in attachments):
                return True
    except Exception:
        logger.warning("[harness] Failed to inspect conversation attachments for analyze_image provenance", exc_info=True)
    return False


def _conversation_has_generated_image_artifact(ctx: "HarnessContext") -> bool:
    artifact_dir = ctx.meta_dir / "generation_artifacts"
    if not artifact_dir.exists():
        return False
    for artifact_path in artifact_dir.glob("*.json"):
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("[harness] Failed to read generation artifact metadata: %s", artifact_path, exc_info=True)
            continue
        if str(artifact.get("kind") or "").strip().lower() == "image":
            return True
    return False


def _is_public_remote_image_url(image_url: str) -> bool:
    normalized = str(image_url or "").replace("\\", "/").strip().lower()
    return normalized.startswith(("http://", "https://")) and "/uploads/" not in normalized


def _should_block_public_image_analysis(image_url: str, ctx: "HarnessContext") -> bool:
    if not _is_public_remote_image_url(image_url):
        return False
    if _conversation_has_user_image_input(ctx):
        return False
    if _conversation_has_generated_image_artifact(ctx):
        return False
    return True


def _workspace_path_to_data_uri(relative: str, ctx: "HarnessContext") -> str | None:
    if Path(relative).is_absolute():
        return None
    normalized = str(relative or "").replace("\\", "/").lstrip("/")
    conversation_root = ctx.conversation_dir.resolve()
    scoped_candidates: list[Path] = []
    for prefix in ("project/", "workspace/"):
        if not normalized.startswith(prefix):
            continue
        stripped = normalized[len(prefix):].lstrip("/")
        if stripped.startswith("critique/"):
            scoped_candidates.append(conversation_root / stripped)
    candidates = [
        ctx.resolve_workspace_path(relative, default_scope="code", allow_fallback_to_files=False),
        ctx.code_dir / normalized,
        ctx.conversation_dir / "code" / normalized,
        ctx.conversation_dir / "files" / normalized,
        ctx.conversation_dir / relative,
        *scoped_candidates,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
            resolved.relative_to(conversation_root)
        except ValueError:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        compressed = local_path_to_base64(str(resolved))
        if compressed:
            b64, mime, _debug = compressed
            return f"data:{mime};base64,{b64}"
        return None
    return None


def _resolve_image_for_api(image_url: str, ctx: "HarnessContext") -> str | None:
    """Resolve the image input in this order:
    1. data URI
    2. safe local path inside the current Harness conversation/workspace roots
    3. upload API or uploads/... path resolved inside allowed upload roots
    4. HTTP(S) URL
    5. workspace-relative project/... or references/... path
    """
    if not image_url:
        return None
    if image_url.startswith("data:"):
        return image_url

    safe_local_path = resolve_safe_local_media_path(image_url, ctx)
    if safe_local_path is not None:
        compressed = local_path_to_base64(str(safe_local_path))
        if compressed:
            b64, mime, _debug = compressed
            return f"data:{mime};base64,{b64}"
        return None

    normalized = image_url.replace("\\", "/")
    if "/uploads/" in normalized or normalized.startswith("uploads/"):
        resolved = resolve_url_for_api(image_url, prefer="base64")
        if resolved and resolved.get("type") == "base64":
            return f"data:{resolved['mime_type']};base64,{resolved['data']}"
        if resolved and resolved.get("type") == "url":
            return resolved["url"]
        data_uri = _workspace_path_to_data_uri(image_url, ctx)
        if data_uri:
            return data_uri
        return None

    if Path(image_url).is_absolute():
        logger.warning("[harness] Rejected absolute image input outside allowed roots: %s", image_url)
        return None

    if image_url.startswith(("http://", "https://")):
        return image_url

    data_uri = _workspace_path_to_data_uri(image_url, ctx)
    if data_uri:
        return data_uri

    logger.warning("[harness] Could not resolve image input: %s", image_url)
    return None


def _conversation_metadata_exists(ctx: "HarnessContext") -> bool:
    from app.services.agent_harness.workspace.conversation.conversation_service import get_conversation

    return get_conversation(int(ctx.user_id), str(ctx.conversation_id)) is not None


async def _record_image_analysis_usage_log(
    *,
    ctx: "HarnessContext",
    model_name: str,
    provider_code: str,
    cost: int,
    elapsed_ms: int,
    input_tokens: int,
    output_tokens: int,
    usage: dict[str, Any] | None = None,
) -> None:
    if ctx.parent_usage_log_id is None:
        return
    if cost <= 0 and input_tokens <= 0 and output_tokens <= 0:
        return

    scope = ctx.get_tool_stream_scope() or {}
    tool_call_id = str(scope.get("tool_call_id") or "").strip() or None
    usage = usage if isinstance(usage, dict) else {}
    usage_provider_code = str(usage.get("provider_code") or "").strip()
    resolved_provider_code = usage_provider_code or ("apimart" if provider_code == "builtin" else provider_code)
    billing_key = ":".join(
        [
            "harness",
            "image_analysis",
            str(ctx.conversation_id),
            str(ctx.run_id),
            str(tool_call_id or "no-tool-call"),
        ]
    )
    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        from app.services.billing_service import BillingService

        billing_svc = BillingService(db)
        if resolved_provider_code == "lingyaai":
            await billing_svc.create_provider_reconcile_usage_log(
                user_id=ctx.user_id,
                parent_id=ctx.parent_usage_log_id,
                task_id=None,
                model_name=model_name,
                task_type="image_analysis",
                provider_code="lingyaai",
                provider_request_id=usage.get("oneapi_request_id"),
                provider_trace_id=usage.get("request_id"),
                billing_key=billing_key,
                params={
                    "kind": "analyze_image",
                    "agent_run_id": ctx.run_id,
                    "conversation_id": ctx.conversation_id,
                    "tool_call_id": tool_call_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "billing_key": billing_key,
                },
                billing_label="billing.labels.image_analysis",
                elapsed_ms=elapsed_ms,
            )
            return
        await billing_svc.create_usage_log(
            user_id=ctx.user_id,
            parent_id=ctx.parent_usage_log_id,
            task_id=None,
            model_name=model_name,
            task_type="image_analysis",
            billing_key=billing_key,
            amount_cents=max(int(cost or 0), 0),
            params={
                "kind": "analyze_image",
                "agent_run_id": ctx.run_id,
                "conversation_id": ctx.conversation_id,
                "tool_call_id": tool_call_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "billing_key": billing_key,
            },
            task_status="success",
            billing_label="billing.labels.image_analysis",
            elapsed_ms=elapsed_ms,
            provider_code=resolved_provider_code,
            billing_mode="local_price" if resolved_provider_code == "apimart" else None,
        )
        await billing_svc.refresh_parent_usage_log(ctx.parent_usage_log_id)


async def _emit_stream_event(
    *,
    ctx: "HarnessContext",
    event_type: str,
    payload: dict[str, Any],
    block_id: str | None = None,
    parent_block_id: str | None = None,
) -> None:
    scope = ctx.get_tool_stream_scope() or {}
    tool_call_id = scope.get("tool_call_id")
    tool_name = str(scope.get("tool_name") or "analyze_image")
    enriched_payload = enrich_harness_event_payload(
        ctx=ctx,
        payload=payload,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
    )

    if ctx.runtime_gateway is None and _conversation_metadata_exists(ctx):
        record = append_harness_event(
            ctx=ctx,
            event_type=event_type,
            data=enriched_payload,
            run_id=ctx.run_id,
            block_id=block_id,
            tool_call_id=tool_call_id,
            parent_block_id=parent_block_id,
            tool_name=tool_name,
        )
        if record is not None and ctx.event_queue is not None:
            try:
                await ctx.event_queue.put(record)
            except Exception:
                logger.warning(
                    "[harness] failed to enqueue analyze_image stream record %s",
                    event_type,
                    exc_info=True,
                )

    try:
        await ctx.emit_tool_stream_event(event_type, enriched_payload)
    except Exception:
        logger.warning(
            "[harness] failed to invoke analyze_image stream callback %s",
            event_type,
            exc_info=True,
        )


async def _safe_emit_stream_event(
    *,
    ctx: "HarnessContext",
    event_type: str,
    payload: dict[str, Any],
    block_id: str | None = None,
    parent_block_id: str | None = None,
) -> None:
    try:
        await _emit_stream_event(
            ctx=ctx,
            event_type=event_type,
            payload=payload,
            block_id=block_id,
            parent_block_id=parent_block_id,
        )
    except Exception:
        logger.warning(
            "[harness] failed to emit analyze_image stream event %s",
            event_type,
            exc_info=True,
        )


class AnalyzeImageTool(BaseTool):
    @property
    def name(self) -> str:
        return "analyze_image"

    @property
    def description(self) -> str:
        return (
            "Analyze an image with the configured default image-analysis model. Supports HTTP(S), data URIs, "
            "upload URLs, absolute local paths, and workspace-relative paths. When a user message includes "
            "structured media references, copy the exact tool_reference for the relevant image into image_url; "
            "do not invent reference_ids or new tool fields."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return AnalyzeImageParams

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    async def execute(self, params: AnalyzeImageParams, ctx: "HarnessContext") -> ToolResult:
        question = params.question or DEFAULT_ANALYSIS_QUESTION
        if await run_file_io(_should_block_public_image_analysis, params.image_url, ctx):
            return ToolResult(
                output=json.dumps(
                    {
                        "error": (
                            "禁止直接分析公网图片：当前会话未检测到用户提供的图片，"
                            "也没有已有的图片生成产物。请先让用户上传或引用图片，"
                            "或先调用 generate_image 再使用返回的 artifact_ref 继续分析。"
                        ),
                        "image_url": params.image_url,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                metadata={"image_url": params.image_url, "kind": "analyze_image"},
            )
        img_url = await run_file_io(_resolve_image_for_api, params.image_url, ctx)
        if not img_url:
            return ToolResult(
                output=json.dumps(
                    {
                        "error": "无法解析本地图像，请确认文件路径存在且位于上传目录或当前会话工作区内。",
                        "image_url": params.image_url,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                metadata={"image_url": params.image_url, "kind": "analyze_image"},
            )

        model_name = get_default_image_analysis_model()
        provider_code = get_default_image_analysis_provider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img_url}},
                    {"type": "text", "text": question},
                ],
            }
        ]

        t0 = time.monotonic()
        scope = ctx.get_tool_stream_scope() or {}
        scoped_tool_call_id = scope.get("tool_call_id")
        tool_call_id = str(scoped_tool_call_id or f"{ctx.run_id}-{uuid.uuid4().hex[:8]}")
        block_id = f"analyze-image-text-{tool_call_id}"
        scoped_parent_block_id = str(scope.get("parent_block_key") or "").strip()
        parent_block_id = scoped_parent_block_id or (f"media-{tool_call_id}" if scoped_tool_call_id else None)
        message_key = str(scope.get("message_key") or "").strip() or presentation_v2.message_key_for_run(ctx.conversation_id, ctx.run_id)

        try:
            await _emit_stream_event(
                ctx=ctx,
                event_type="tool_started",
                payload={
                    "kind": "analyze_image",
                    "model_name": model_name,
                    "provider_code": provider_code,
                    "question": question,
                    "image_url": params.image_url,
                },
            )
            await _emit_stream_event(
                ctx=ctx,
                event_type="presentation.block.upsert",
                payload=presentation_v2.text_block_start(
                    conversation_id=ctx.conversation_id,
                    run_id=ctx.run_id,
                    block_key=block_id,
                    message_key=message_key,
                    parent_block_key=parent_block_id,
                    payload_extra={
                        "toolName": "analyze_image",
                        "tool_name": "analyze_image",
                        "callId": tool_call_id,
                        "call_id": tool_call_id,
                    },
                ),
                block_id=block_id,
                parent_block_id=parent_block_id,
            )
            analysis_parts: list[str] = []
            stream_delta_buffer: list[str] = []
            stream_delta_buffer_chars = 0
            stream_delta_last_flush = time.monotonic()

            async def _flush_analysis_delta(*, force: bool = False) -> None:
                nonlocal stream_delta_buffer_chars, stream_delta_last_flush
                if not stream_delta_buffer:
                    return
                elapsed = time.monotonic() - stream_delta_last_flush
                if (
                    not force
                    and stream_delta_buffer_chars < _stream_delta_flush_chars()
                    and elapsed < _stream_delta_flush_interval()
                ):
                    return
                flushed_delta = "".join(stream_delta_buffer)
                stream_delta_buffer.clear()
                stream_delta_buffer_chars = 0
                stream_delta_last_flush = time.monotonic()
                await _emit_stream_event(
                    ctx=ctx,
                    event_type="presentation.block.delta",
                    payload=presentation_v2.block_delta(
                        conversation_id=ctx.conversation_id,
                        run_id=ctx.run_id,
                        block_key=block_id,
                        message_key=message_key,
                        parent_block_key=parent_block_id,
                        field="text",
                        delta=flushed_delta,
                    ),
                    block_id=block_id,
                    parent_block_id=parent_block_id,
                )

            session_factory = get_harness_db_session_factory()
            async with session_factory() as db:
                svc = MultimodalService(db)
                async for delta in svc.chat_stream(
                    user_id=ctx.user_id,
                    model_name=model_name,
                    provider_code=provider_code,
                    messages=messages,
                    skip_usage_log=True,
                    billing_label="billing.labels.image_analysis",
                ):
                    if not delta:
                        continue
                    analysis_parts.append(delta)
                    if not stream_delta_buffer:
                        stream_delta_last_flush = time.monotonic()
                    stream_delta_buffer.append(delta)
                    stream_delta_buffer_chars += len(delta)
                    await _flush_analysis_delta()

                await _flush_analysis_delta(force=True)

                usage = svc.last_stream_usage or {}
                input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                cost = int(getattr(svc, "last_stream_amount_cents", 0) or 0)
                analysis = "".join(analysis_parts).strip()
        except Exception as e:
            logger.exception("[harness] Image analysis failed")
            error_message = f"图片分析失败: {e}"
            await _safe_emit_stream_event(
                ctx=ctx,
                event_type="presentation.block.complete",
                payload=presentation_v2.text_block_complete(
                    conversation_id=ctx.conversation_id,
                    run_id=ctx.run_id,
                    block_key=block_id,
                    message_key=message_key,
                    parent_block_key=parent_block_id,
                    text=error_message,
                    status="failed",
                    payload_extra={
                        "toolName": "analyze_image",
                        "tool_name": "analyze_image",
                        "callId": tool_call_id,
                        "call_id": tool_call_id,
                    },
                ),
                block_id=block_id,
                parent_block_id=parent_block_id,
            )
            await _safe_emit_stream_event(
                ctx=ctx,
                event_type="tool_completed",
                payload={
                    "status": "failed",
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "result": {
                        "error": error_message,
                    },
                },
            )
            return ToolResult(
                output=json.dumps({"error": error_message}, ensure_ascii=False),
                is_error=True,
            )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if not analysis:
            analysis = "No analysis result returned."

        try:
            ctx.record_billing(
                category="image_analysis",
                amount=cost,
                detail={
                    "model_name": model_name,
                    "provider_code": provider_code,
                    "kind": "analyze_image",
                    "elapsed_ms": elapsed_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
        except Exception:
            pass
        try:
            await _record_image_analysis_usage_log(
                ctx=ctx,
                model_name=model_name,
                provider_code=provider_code,
                cost=cost,
                elapsed_ms=elapsed_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage=usage,
            )
        except Exception:
            logger.warning("[harness] failed to record analyze_image usage log", exc_info=True)

        result_data = {
            "analysis": analysis,
            "model_name": model_name,
            "provider_code": provider_code,
            "question": question,
            "elapsed_ms": elapsed_ms,
            "message": "图片分析完成。",
        }

        await _emit_stream_event(
            ctx=ctx,
            event_type="presentation.block.complete",
            payload=presentation_v2.text_block_complete(
                conversation_id=ctx.conversation_id,
                run_id=ctx.run_id,
                block_key=block_id,
                message_key=message_key,
                parent_block_key=parent_block_id,
                text=analysis,
                payload_extra={
                    "toolName": "analyze_image",
                    "tool_name": "analyze_image",
                    "callId": tool_call_id,
                    "call_id": tool_call_id,
                },
            ),
            block_id=block_id,
            parent_block_id=parent_block_id,
        )
        await _emit_stream_event(
            ctx=ctx,
            event_type="tool_completed",
            payload={
                "status": "completed",
                "elapsed_ms": elapsed_ms,
                "result": result_data,
            },
        )

        return ToolResult(
            output=json.dumps(result_data, ensure_ascii=False),
            metadata={
                "model_name": model_name,
                "provider_code": provider_code,
                "kind": "analyze_image",
                "question": question,
                "elapsed_ms": elapsed_ms,
                "analysis": analysis,
                "message": "图片分析完成。",
            },
        )

