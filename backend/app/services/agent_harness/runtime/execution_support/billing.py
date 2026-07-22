"""Helpers for simplified homepage harness billing."""

from __future__ import annotations

import logging
from typing import Final

from app.services.agent_harness.capabilities.skills.runtime_profiles import is_canvas_only_skill


logger = logging.getLogger(__name__)

_CANVAS_SMART_DESIGNER_BILLING_LABEL = "billing.labels.smart_designer"
_CANVAS_SMART_DESIGNER_MODE_LABEL = "智能设计师"


_MODE_TO_BILLING_LABEL: Final[dict[str, str]] = {
    "web": "billing.labels.web_generate",
    "document": "billing.labels.document_generate",
    "spreadsheet": "billing.labels.spreadsheet_generate",
    "slides": "billing.labels.ppt_generate",
    "image": "billing.labels.image_generate",
    "video": "billing.labels.video_generate",
}

_MODE_TO_DISPLAY_LABEL: Final[dict[str, str]] = {
    "web": "网页生成",
    "document": "文档生成",
    "slides": "幻灯片生成",
    "spreadsheet": "表格生成",
    "image": "图片生成",
    "video": "视频生成",
}

_SKILL_TO_MODE: Final[dict[str, str]] = {
    "docx": "document",
    "pptx": "slides",
    "xlsx": "spreadsheet",
    "web": "web",
}


def resolve_harness_mode(mode: str | None = None, skill_id: str | None = None) -> str:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode in _MODE_TO_BILLING_LABEL:
        return normalized_mode

    normalized_skill = str(skill_id or "").strip().lower()
    if normalized_skill in _SKILL_TO_MODE:
        return _SKILL_TO_MODE[normalized_skill]

    return "web"


def resolve_harness_billing_label(mode: str | None = None, skill_id: str | None = None) -> str:
    if is_canvas_only_skill(skill_id):
        return _CANVAS_SMART_DESIGNER_BILLING_LABEL
    resolved_mode = resolve_harness_mode(mode=mode, skill_id=skill_id)
    return _MODE_TO_BILLING_LABEL[resolved_mode]


def resolve_harness_mode_label(mode: str | None = None, skill_id: str | None = None) -> str:
    if is_canvas_only_skill(skill_id):
        return _CANVAS_SMART_DESIGNER_MODE_LABEL
    resolved_mode = resolve_harness_mode(mode=mode, skill_id=skill_id)
    return _MODE_TO_DISPLAY_LABEL[resolved_mode]


def get_harness_db_session_factory():
    from app.db.session import AsyncSessionLocal, LoopSafeAsyncSessionLocal
    from app.main import app

    state = getattr(app, "state", None)
    override = getattr(state, "db_session_factory", None)
    # Honor an explicit override that targets a different database (tests inject one
    # here). The default override is the pooled AsyncSessionLocal, which is NOT safe
    # to use from the harness worker event loops — fall back to the NullPool-backed
    # loop-safe factory in that case so pooled connections never cross event loops.
    if override is not None and override is not AsyncSessionLocal:
        return override
    return LoopSafeAsyncSessionLocal


async def charge_harness_amount(
    user_id: int,
    *,
    model_name: str,
    resolution: str | None = None,
    duration: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    task_type: str | None = None,
    audio: bool | None = None,
) -> int:
    from app.services.billing_service import BillingService
    from app.core.provider_balance_mode import is_provider_balance_sync_enabled

    amount_cents = int(
        BillingService.calculate_amount(
            model_name,
            resolution=resolution,
            duration=duration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task_type=task_type,
            audio=audio,
        )
        or 0
    )
    if amount_cents <= 0:
        return 0

    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        ok = await BillingService(db).deduct_balance(user_id, amount_cents)

    if not ok:
        logger.warning(
            "User %s could not be charged %s cents for harness model %s",
            user_id,
            amount_cents,
            model_name,
        )
        return 0

    if is_provider_balance_sync_enabled():
        return 0

    return amount_cents
