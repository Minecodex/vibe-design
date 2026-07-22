"""Image generation tool for the Harness agent.

Uses the shared GenerationIntakeService so Harness media tasks are persisted in
the SQL ``generation_tasks`` table and scheduled through the same intake path as
canvas generation.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from app.models.user import User

from app.core.image_constraints import resolve_image_generation_selection
from app.core.media_capabilities import build_image_tool_schema
from app.core.providers import build_provider_registry
from app.services.agent_harness.canvas.agent_item_persistence import (
    persist_agent_canvas_item_patch,
)
from app.services.agent_harness.canvas.generation_mapper import build_canvas_generation_item
from app.services.agent_harness.core.utils.artifacts import build_artifact_metadata
from app.services.agent_harness.core.utils.media_utils import (
    resolve_safe_local_media_path,
)
from app.services.agent_harness.core.utils.media_generation_preferences import (
    resolve_image_generation_preferences,
)
from app.services.agent_harness.core.utils.model_labels import resolve_model_label
from app.services.agent_harness.workspace.generated_content.asset_store import (
    planned_reference_asset_path,
)
from app.services.agent_harness.workflow.tool_gating import normalize_presentation_scope
from app.services.generation_intake_service import GenerationIntakeRequest, GenerationIntakeService
from app.services.user_apimart_key_service import UserApimartKeyService

from ._internal.base import BaseTool, ToolResult
from ._internal.reference_diagnostics import message_reference_diagnostics

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic input model
# ---------------------------------------------------------------------------


class GenerateImageParams(BaseModel):
    prompt: str = Field(
        ...,
        description=(
            "图片生成提示词（请使用当前会话语言撰写）。忠实表达用户意图；当使用参考图时，不要添加用户未要求的颜色、材质、风格、"
            "光线、构图或对象细节，不要把参考图对象按常识改写成其他外观。"
        ),
    )
    aspect_ratio: str | None = Field(
        None,
        description="图片宽高比，如 1:1, 16:9, 9:16, 2:1, 1:2, 4:3, 3:4, 3:2, 2:3。部分模型在特定分辨率下仅支持部分比例，工具会自动调整到兼容比例。",
    )
    resolution: str | None = Field(
        None,
        description="输出分辨率等级，如 1K, 2K, 4K。省略时使用模型支持的最高分辨率。若与所选比例不兼容（例如 GPT-Image-2 的 4K），工具会自动切换到兼容比例。",
    )
    reference_image_urls: list[str] | None = Field(
        None,
        description="多张参考图片的 URL、相对路径或生成工具返回的 artifact_ref 列表，用于多参考图生成。当任务是在当前会话中继续细化、变体化、规范化或延展上一轮已确认图片时，优先继续沿用该图片的引用，而不是只复述它的风格。",
    )


# ---------------------------------------------------------------------------
# Reference URL resolution
# ---------------------------------------------------------------------------


def _resolve_reference_for_generation_params(
    url_or_path: str | None, ctx: "HarnessContext"
) -> str | None:
    """Resolve a reference image to a durable task parameter, without embedding base64."""
    if not url_or_path:
        return None

    normalized_input = str(url_or_path).replace("\\", "/")
    if normalized_input.startswith(("/api/v1/uploads/", "api/v1/uploads/", "/uploads/", "uploads/")):
        return normalized_input if normalized_input.startswith("/") else f"/{normalized_input}"

    if url_or_path.startswith(("http://", "https://")):
        return url_or_path

    if url_or_path.startswith("data:"):
        logger.warning("Skipping data URI reference for generation task params")
        return None

    safe_local_path = resolve_safe_local_media_path(url_or_path, ctx)
    if safe_local_path is not None:
        try:
            rel = safe_local_path.resolve().relative_to(ctx.conversation_dir.resolve())
            return rel.as_posix()
        except (OSError, ValueError):
            return url_or_path

    file_path = ctx.conversation_dir / url_or_path
    if not file_path.exists():
        logger.warning("Reference image not found: %s", url_or_path)
        return None

    return str(url_or_path).replace("\\", "/")


def _extract_external_id(result: dict) -> str | None:
    data = result.get("data")
    if isinstance(data, list) and data:
        return data[0].get("task_id") or data[0].get("id")
    if isinstance(data, dict):
        return data.get("task_id") or data.get("id")
    return result.get("task_id")


def _normalize_reference_inputs(reference_image_urls: list[str] | None) -> list[str]:
    return [reference for reference in (reference_image_urls or []) if reference]


def _unique_ordered_strings(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique



def _retry_metadata(task: dict | None, artifact: dict | None) -> dict[str, int]:
    base = artifact or task or {}
    return {
        "auto_retry_count": int(base.get("auto_retry_count") or 0),
        "auto_retry_max": int(base.get("auto_retry_max") or 3),
        "manual_retry_count": int(base.get("manual_retry_count") or 0),
    }


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
    retry_metadata = _retry_metadata(task, artifact)
    async_execution = status in {"processing", "running", "pending"}
    preview_url = artifact.get("planned_result_url") or task.get("planned_result_url")
    message = (
        "不要再用同一个 artifact_ref 重复创建。"
        "你可以直接执行下一步动作；在回复中嵌入这张图请使用 preview_url，写成 ![描述](preview_url)，"
        "不要编造文件名或使用可能为空的 result_url。"
        "如果后续工具需要依赖这张图，请把 artifact_ref 传给 reference_image_urls 或 analyze_image.image_url，运行时会自动等待。"
    )
    data = {
        "task_id": task_id,
        "artifact_ref": artifact.get("artifact_ref"),
        **retry_metadata,
        "status": status,
        "result_url": result_url,
        "planned_result_url": preview_url,
        "artifact": build_artifact_metadata(result_url, ctx),
        "model_name": task.get("model_name"),
        "model_label": task.get("model_label"),
        "prompt": task.get("prompt") or prompt,
        "aspect_ratio": task.get("aspect_ratio"),
        "resolution": task.get("resolution"),
        "async_execution": async_execution,
        "do_not_repeat_same_generation": True,
        "duplicate_generation_blocked": True,
        "emit_media_card": False,
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
            "media_type": "image",
            "status": status,
            "result_url": result_url,
            "planned_result_url": preview_url,
            "artifact": build_artifact_metadata(result_url, ctx),
            "prompt": data["prompt"],
            "model_name": data["model_name"],
            "model_label": data["model_label"],
            "aspect_ratio": data["aspect_ratio"],
            "resolution": data["resolution"],
            "async_execution": async_execution,
            "do_not_repeat_same_generation": True,
            "duplicate_generation_blocked": True,
            "emit_media_card": False,
            "preview_url": preview_url,
            "next_action_hint": message,
            "message": message,
            "canvas_item": data["canvas_item"],
        },
    )


def _find_builtin_image_model_config(model_name: str, provider_code: str | None) -> dict:
    provider = build_provider_registry().get(provider_code or "")
    if not provider:
        return {}
    for entry in provider.get("models", {}).get("text2image", []):
        if entry.get("model_name") == model_name:
            return dict(entry.get("config") or {})
    return {}


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
    artifact_ref: str | None,
    agent_group_key: str | None = None,
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
            "agent_group_key": next_item.get("agent_group_key") or agent_group_key,
            "prompt": prompt,
            "model_name": model_name,
            "model_label": model_label,
            "provider_code": provider_code,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "status": "generating",
            "url": "",
        })
        return next_item

    return build_canvas_generation_item(
        conversation_id=ctx.conversation_id,
        kind="image",
        task_id=task_id,
        prompt=prompt,
        model_name=model_name,
        model_label=model_label,
        provider_code=provider_code,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        duration=None,
        result_url="",
        status="processing",
        artifact_ref=artifact_ref,
        agent_group_key=agent_group_key,
        position={"x": 0, "y": 0},
    )


async def submit_image_generation(
    *,
    params: GenerateImageParams,
    ctx: "HarnessContext",
    artifact_ref: str | None = None,
    retry_source: str | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> ToolResult:
    from app.services.agent_harness.core.utils import generation_store
    from app.services.agent_harness.core.utils.generation_item_events import (
        emit_generation_item_completed,
        emit_generation_item_started,
    )
    from app.services.agent_harness.core.utils.media_defaults import resolve_harness_image_defaults

    model_name = ctx.image_model
    provider_code = ctx.image_provider or "builtin"

    if not model_name:
        return ToolResult(
            output=json.dumps(
                {
                    "error": (
                        "Missing harness image_model. "
                        "generate_image only uses the frontend-selected image model."
                    )
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )

    if provider_code not in {"builtin", "ollama"}:
        return ToolResult(
            output=json.dumps(
                {
                    "error": (
                        "The selected image provider is not supported in harness image generation."
                    )
                },
                ensure_ascii=False,
            ),
            is_error=True,
        )

    defaults = resolve_harness_image_defaults(model_name, provider_code)
    preferences = resolve_image_generation_preferences(
        ctx.model_preferences,
        provider_code=provider_code,
        model_name=model_name,
    )
    requested_aspect_ratio = (
        params.aspect_ratio
        if retry_source
        else preferences.aspect_ratio or params.aspect_ratio
    )
    requested_resolution = (
        params.resolution
        if retry_source
        else preferences.resolution or params.resolution
    )
    selection = resolve_image_generation_selection(
        config=_find_builtin_image_model_config(model_name, provider_code),
        aspect_ratio=requested_aspect_ratio or defaults["aspect_ratio"],
        resolution=requested_resolution or defaults["resolution"],
        preferred_aspect_ratio=defaults["aspect_ratio"],
        preferred_resolution=defaults["resolution"],
    )
    aspect_ratio = selection["aspect_ratio"]
    resolution = selection["resolution"]
    model_label = resolve_model_label(
        model_name,
        provider_code=provider_code,
        bucket="text2image",
    )

    reference_inputs = _normalize_reference_inputs(params.reference_image_urls)
    ref_urls = [
        resolved
        for reference in reference_inputs
        if (resolved := _resolve_reference_for_generation_params(reference, ctx))
    ]

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
        if current_status in {"processing", "running", "pending", "completed"}:
            return _existing_artifact_result(
                task=current_task or existing_artifact,
                artifact=existing_artifact,
                prompt=params.prompt,
                ctx=ctx,
            )
        artifact_ref = str(existing_artifact["artifact_ref"])
        planned_result_url = str(existing_artifact.get("planned_result_url") or "")
        asset_id = str(existing_artifact.get("asset_id") or "")
    else:
        artifact_ref = generation_store.new_artifact_ref()
        asset_id = f"generated_image_{artifact_ref.removeprefix('artifact_ref:')[:16]}"
        planned_result_url = planned_reference_asset_path(
            ctx.user_id,
            ctx.conversation_id,
            asset_id=asset_id,
            extension="png",
        )
        generation_store.create_or_read_artifact(
            ctx,
            kind="image",
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
    client_request_id = f"harness:image:{ctx.conversation_id}:{tool_call_id or artifact_ref}{retry_request_suffix}"
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
        "reference_image_urls": ref_urls or None,
        **retry_metadata,
    }
    if isinstance(metadata_overrides, dict):
        metadata_params.update(metadata_overrides)
    if presentation_scope:
        metadata_params["presentation_scope"] = presentation_scope
        metadata_params["presentation_message_key"] = presentation_scope.get("message_key")
        metadata_params["presentation_parent_block_key"] = presentation_scope.get("parent_block_key")
    if presentation_order > 0:
        metadata_params["presentation_order"] = presentation_order
    reference_diagnostics = message_reference_diagnostics(
        ctx,
        used_reference_image_count=len(ref_urls),
        used_reference_image_urls=ref_urls,
    )
    if reference_diagnostics:
        metadata_params["reference_diagnostics"] = reference_diagnostics

    from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory

    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        if provider_code == "builtin":
            user = await db.get(User, ctx.user_id)
            await UserApimartKeyService(db).resolve_key(
                ctx.user_id,
                user_role=getattr(user, "role", None),
            )
        intake_result = await GenerationIntakeService(db).submit_image(
            GenerationIntakeRequest(
                user_id=ctx.user_id,
                project_id=ctx.project_id if ctx.runtime_profile == "canvas" else None,
                prompt=params.prompt,
                model_name=model_name,
                provider_code=provider_code,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                image_urls=ref_urls or None,
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
        prompt=params.prompt,
        model_name=model_name,
        model_label=model_label,
        provider_code=provider_code,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        artifact_ref=artifact_ref,
        agent_group_key=None,
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
            "reference_diagnostics": (task.params or {}).get("reference_diagnostics") if isinstance(task.params, dict) else reference_diagnostics,
            **(dict(metadata_overrides) if isinstance(metadata_overrides, dict) else {}),
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
        kind="image",
        canvas_revision=canvas_revision,
        canvas_item_deleted=canvas_item_deleted,
    )
    if task.status == "failed":
        err_msg = task.error_message or "Image generation failed."
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
            kind="image",
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
            kind="image",
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
        "planned_result_url": planned_result_url,
        "artifact": build_artifact_metadata(result_url, ctx),
        "model_name": model_name,
        "model_label": model_label,
        "prompt": params.prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "async_execution": status == "processing",
        "do_not_repeat_same_generation": status == "processing",
        "preview_url": planned_result_url,
        "canvas_item": canvas_item,
        "canvas_revision": canvas_revision,
        "canvas_item_deleted": canvas_item_deleted,
        "reference_diagnostics": (task.params or {}).get("reference_diagnostics") if isinstance(task.params, dict) else reference_diagnostics,
        "tool_call_id": tool_call_id,
        "presentation_scope": presentation_scope or None,
        "presentation_message_key": presentation_scope.get("message_key") if presentation_scope else None,
        "presentation_parent_block_key": presentation_scope.get("parent_block_key") if presentation_scope else None,
        "presentation_order": presentation_order if presentation_order > 0 else None,
        "next_action_hint": (
            "在你给用户的回复中嵌入这张图片时，请直接使用 preview_url 字段的值，"
            "写成 ![描述](preview_url)。preview_url 是当前会话已分配的稳定路径，"
            "图片落盘前用户会看到占位图，落盘后自动显示真图。"
            "禁止根据 prompt 或场景编造文件名/路径，也不要使用 result_url（异步阶段它可能为空）。"
            "不要重复调用 generate_image 获取同一个结果；"
            "如果后续工具需要依赖这张图，请把 artifact_ref 传给 reference_image_urls 或 analyze_image.image_url，运行时会自动等待。"
        ),
        "message": (
            f"图片生成任务已提交成功，可继续使用 artifact_ref (ID: {task_id}, 状态: {status})。"
        ),
    }

    return ToolResult(
        output=json.dumps(result_data, ensure_ascii=False),
        metadata={
            "task_id": task_id,
            "artifact_ref": artifact_ref,
            **retry_metadata,
            **(dict(metadata_overrides) if isinstance(metadata_overrides, dict) else {}),
            "media_type": "image",
            "status": status,
            "result_url": result_url,
            "planned_result_url": planned_result_url,
            "artifact": build_artifact_metadata(result_url, ctx),
            "prompt": params.prompt,
            "model_name": model_name,
            "model_label": model_label,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "async_execution": result_data["async_execution"],
            "do_not_repeat_same_generation": result_data["do_not_repeat_same_generation"],
            "preview_url": planned_result_url,
            "canvas_item": canvas_item,
            "canvas_revision": canvas_revision,
            "canvas_item_deleted": canvas_item_deleted,
            "reference_diagnostics": result_data["reference_diagnostics"],
                "tool_call_id": tool_call_id,
            "presentation_scope": presentation_scope or None,
            "presentation_message_key": presentation_scope.get("message_key") if presentation_scope else None,
            "presentation_parent_block_key": presentation_scope.get("parent_block_key") if presentation_scope else None,
            "presentation_order": presentation_order if presentation_order > 0 else None,
            "next_action_hint": result_data["next_action_hint"],
            "message": result_data["message"],
        },
    )


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------


class GenerateImageTool(BaseTool):
    """根据文本提示词生成图片。"""

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        from app.services.agent_harness.core.context import get_current_context

        base = (
            "根据文本提示词生成图片。"
            "请使用当前会话语言撰写详细的描述性提示词。"
            "当用户上传了参考图片时，可以将其相对路径放入 reference_image_urls 进行图生图。"
            "When the latest user message includes structured media references, copy the exact tool_reference "
            "from each relevant image reference into reference_image_urls; for canvas marks, also reflect the mark label "
            "and normalized position in the prompt. Do not invent reference_ids or new tool fields."
            "当本工具成功返回 artifact_ref 后，就把它当作可继续使用的媒体句柄。"
            "当任务是在当前会话中继续细化、变体、规范化或延展一张已确认图片时，应优先沿用该图片的引用继续推进，而不是只根据文字总结重新生成一个平行版本。"
            "不要复制生成结果里的 URL；若后续工具需要依赖这张图，请把 artifact_ref 传给 "
            "reference_image_urls 或 analyze_image.image_url，运行时会在执行前自动等待。"
        )
        try:
            ctx = get_current_context()
            return base + build_image_tool_schema(ctx.image_provider or "builtin", ctx.image_model).get("description", "")
        except Exception:
            return base + "工具会根据当前模型自动选择兼容的分辨率、比例和限制条件，超出范围时自动收敛到接近的可用设置。"

    @property
    def input_model(self) -> type[BaseModel]:
        return GenerateImageParams

    def get_input_schema(self, language: str = "zh") -> dict:
        schema = super().get_input_schema(language)
        from app.services.agent_harness.core.context import get_current_context

        try:
            ctx = get_current_context()
            tool_schema = build_image_tool_schema(ctx.image_provider or "builtin", ctx.image_model)
        except Exception:
            tool_schema = {"aspect_ratios": [], "resolutions": [], "description": ""}

        properties = schema.get("properties", {})
        aspect_ratios = tool_schema.get("aspect_ratios") or []
        resolutions = tool_schema.get("resolutions") or []
        if "aspect_ratio" in properties:
            if aspect_ratios:
                properties["aspect_ratio"]["enum"] = aspect_ratios
            supported = ", ".join(aspect_ratios) if aspect_ratios else (
                "自动按模型处理" if language == "zh" else "handled automatically by the model"
            )
            properties["aspect_ratio"]["description"] = (
                f"图片宽高比。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用比例。"
                if language == "zh"
                else f"Image aspect ratio. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported ratio."
            )
        if "resolution" in properties:
            if resolutions:
                properties["resolution"]["enum"] = resolutions
            supported = ", ".join(resolutions) if resolutions else (
                "自动按模型处理" if language == "zh" else "handled automatically by the model"
            )
            properties["resolution"]["description"] = (
                f"输出分辨率等级。当前模型支持: {supported}。如果设置不兼容，工具会自动调整到接近的可用分辨率。"
                if language == "zh"
                else f"Output resolution tier. Current model supports: {supported}. If the setting is incompatible, the tool will adjust to a close supported resolution."
            )
        return schema

    async def execute(
        self, params: GenerateImageParams, ctx: "HarnessContext"
    ) -> ToolResult:
        return await submit_image_generation(params=params, ctx=ctx)

