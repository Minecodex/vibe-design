from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.reference_gallery_repository import ReferenceTaxonomyRepository
from app.services.agent_harness.runtime.state.store_core import utc_now

from .contracts import MessageSpec

logger = logging.getLogger(__name__)

ECOMMERCE_GENERATION_OPTIONS_KIND = "ecommerce_generation_options"
ECOMMERCE_INTERACTION_KINDS = {ECOMMERCE_GENERATION_OPTIONS_KIND}


def ecommerce_text(value: Any) -> str:
    return str(value or "").strip()


def _truthy_ecommerce_option(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = ecommerce_text(value).lower()
    return text in {"1", "true", "yes", "y", "on", "开启", "是"}


def _ecommerce_reference_urls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = ecommerce_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        urls.append(text)
    return urls


def _ecommerce_generation_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 4
    return min(max(count, 1), 6)


def _ecommerce_reference_block(title: str, urls: list[str]) -> str:
    if not urls:
        return ""
    lines = [title]
    lines.extend(f"- {url}" for url in urls)
    return "\n".join(lines)


def compose_ecommerce_generation_context(answers: dict[str, Any]) -> str | None:
    action = ecommerce_text(answers.get("action")).lower()
    if action and action != "confirm":
        return None

    category_prompt = ecommerce_text(answers.get("category_prompt"))
    style_prompt = ecommerce_text(answers.get("style_prompt"))
    category_name = ecommerce_text(answers.get("category_name"))
    style_name = ecommerce_text(answers.get("style_name"))
    generation_count = _ecommerce_generation_count(answers.get("generation_count"))

    background_urls = (
        _ecommerce_reference_urls(answers.get("background_reference_image_urls"))
        if _truthy_ecommerce_option(answers.get("enable_background_reference"))
        else []
    )
    model_urls = (
        _ecommerce_reference_urls(answers.get("model_reference_image_urls"))
        if _truthy_ecommerce_option(answers.get("enable_model_reference"))
        else []
    )
    other_main_urls = (
        _ecommerce_reference_urls(answers.get("other_main_image_reference_image_urls"))
        if _truthy_ecommerce_option(answers.get("enable_other_main_image_reference"))
        else []
    )

    model_reference_prompt = ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_MODEL_REFERENCE_PROMPT) if model_urls else ""
    background_reference_prompt = (
        ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_BACKGROUND_REFERENCE_PROMPT)
        if background_urls
        else ""
    )
    other_main_reference_prompt = (
        ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_OTHER_MAIN_IMAGE_REFERENCE_PROMPT)
        if other_main_urls
        else ""
    )

    values = {
        "图片分类提示词": category_prompt,
        "图片风格提示词": style_prompt,
        "平台规则提示词": ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_PLATFORM_RULE_PROMPT),
        "人物参考图提示词": model_reference_prompt,
        "人物参考图": _ecommerce_reference_block("人物参考图：", model_urls),
        "背景参考图提示词": background_reference_prompt,
        "背景参考图": _ecommerce_reference_block("背景参考图：", background_urls),
        "其他商品主图参考图提示词": other_main_reference_prompt,
        "其他商品参考图": _ecommerce_reference_block("其他商品主图参考图：", other_main_urls),
        "负面约束提示词": ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_NEGATIVE_PROMPT),
        "生成商品图数量": str(generation_count),
        "用户需求": (
            "请基于以上已确认的商品细节锁定卡、白底基准图和本次配置，"
            "自行组织 generate_image 的 prompt 与 reference_image_urls，生成对应数量的男装电商商品图。"
        ),
    }
    template = ecommerce_text(settings.ECOMMERCE_PRODUCT_IMAGE_CONTEXT_TEMPLATE)
    try:
        content = template.format_map(values)
    except Exception:
        content = "\n\n".join(
            part
            for part in [
                "你需要参考上面实拍图图片分析内容、实拍图和对应的基准生成对应的图片。",
                category_prompt,
                style_prompt,
                values["平台规则提示词"],
                model_reference_prompt,
                values["人物参考图"],
                background_reference_prompt,
                values["背景参考图"],
                other_main_reference_prompt,
                values["其他商品参考图"],
                values["负面约束提示词"],
                f"生成商品图数量：{generation_count}",
                values["用户需求"],
            ]
            if part
        )
    header = "\n".join(
        part
        for part in [
            "【商品图生成确认上下文】",
            f"参考图库图片分类：{category_name}" if category_name else "",
            f"图片风格：{style_name}" if style_name else "",
            f"生成商品图数量：{generation_count}",
        ]
        if part
    )
    return f"{header}\n\n{content.strip()}".strip()


def ecommerce_generation_context_message_spec(
    *,
    run_id: str,
    step_id: str,
    request_id: str,
    answers: dict[str, Any],
) -> MessageSpec | None:
    content = compose_ecommerce_generation_context(answers)
    if not content:
        return None
    stable_part = request_id or str(step_id or "").strip() or "unknown"
    return MessageSpec(
        role="user",
        content=content,
        idempotency_key=f"run:{run_id}:ecommerce-generation-context:{stable_part}",
        metadata={
            "message_kind": "agent_context",
            "agent_context_kind": "ecommerce_generation_context",
            "interaction_kind": ECOMMERCE_GENERATION_OPTIONS_KIND,
            "request_id": request_id or None,
            "model_visible": True,
            "ui_visible": False,
        },
    )


def record_ecommerce_submission_in_contract(
    runtime_contract: dict[str, Any],
    *,
    request_id: str,
    pending_interaction: dict[str, Any] | None,
    payload: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    pending = pending_interaction if isinstance(pending_interaction, dict) else {}
    kind = str(pending.get("kind") or "").strip()
    action = str(answers.get("action") or payload.get("action") or "").strip() or None
    record = {
        "request_id": request_id or None,
        "kind": kind or None,
        "action": action,
        "answers": dict(answers or {}),
        "answer": str(payload.get("answer") or ""),
        "submitted_at": utc_now(),
    }
    record = {key: value for key, value in record.items() if value not in (None, "", [])}
    updated_contract = dict(runtime_contract or {})
    workflow = (
        dict(updated_contract.get("ecommerce_product_workflow"))
        if isinstance(updated_contract.get("ecommerce_product_workflow"), dict)
        else {}
    )
    submissions = [
        dict(item)
        for item in workflow.get("submissions", [])
        if isinstance(item, dict)
    ]
    if request_id:
        submissions = [
            item for item in submissions if str(item.get("request_id") or "").strip() != request_id
        ]
    submissions.append(record)
    workflow.update(
        {
            "last_interaction_kind": kind or None,
            "last_action": action,
            "last_request_id": request_id or None,
            "submissions": submissions[-25:],
            "updated_at": utc_now(),
        }
    )
    updated_contract["ecommerce_product_workflow"] = workflow
    return updated_contract


def _taxonomy_id(value: Any) -> int | None:
    try:
        taxonomy_id = int(value)
    except (TypeError, ValueError):
        return None
    return taxonomy_id if taxonomy_id > 0 else None


async def resolve_ecommerce_taxonomy_prompts(answers: dict[str, Any]) -> dict[str, Any]:
    """Resolve selected taxonomy prompt text from the reference gallery.

    The card submits the selected ids plus display data for UI bookkeeping. The
    model-visible generation context should prefer the server-side taxonomy row
    so prompt text changes stay centralized in the reference gallery.
    """
    resolved = dict(answers or {})
    selected = [
        ("category", "category", _taxonomy_id(resolved.get("category_id"))),
        ("style", "style", _taxonomy_id(resolved.get("style_id"))),
    ]
    if not any(taxonomy_id for _prefix, _kind, taxonomy_id in selected):
        return resolved

    try:
        async with AsyncSessionLocal() as db:
            repo = ReferenceTaxonomyRepository(db)
            for prefix, kind, taxonomy_id in selected:
                if taxonomy_id is None:
                    continue
                taxonomy = await repo.get(taxonomy_id)
                if taxonomy is None or taxonomy.kind != kind:
                    resolved[f"{prefix}_name"] = ""
                    resolved[f"{prefix}_prompt"] = ""
                    continue
                resolved[f"{prefix}_name"] = taxonomy.name or ""
                resolved[f"{prefix}_prompt"] = taxonomy.prompt or ""
    except Exception:
        logger.warning(
            "[harness] failed to resolve ecommerce reference taxonomy prompts",
            exc_info=True,
        )
    return resolved
