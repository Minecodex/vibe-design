from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.default_models import get_default_multimodal_model
from app.services.agent_harness.authoring.planning.design_system_selection_resolver import (
    resolve_design_system_selection,
)
from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_payload
from app.services.agent_harness.capabilities.design_systems.resolver_registry import (
    DesignSystemResolverMetadata,
)
from app.services.agent_harness.catalog import (
    DesignSystemSummary,
    list_design_system_summaries_sync,
)
from app.services.agent_harness.prompt_runtime import Phase, PromptMode, PromptRuntime, TurnSpec
from app.services.agent_harness.prompt_runtime.tracing import persist_prompt_bundle_trace
from app.services.agent_harness.runtime.execution_support.harness_model_provider import (
    create_harness_model_provider,
)
from app.services.agent_harness.workspace.conversation.conversation_service import (
    iter_messages_reverse,
)
from app.services.llm_runtime.tool_calls import tool_call_arguments, tool_call_name
from app.services.multimodal_service import resolve_effective_max_tokens
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context

logger = logging.getLogger(__name__)
_PROMPT_RUNTIME = PromptRuntime()

DirectionOption = dict[str, Any]
QuickBriefSchema = dict[str, Any]
DiscoveryModelCallback = Callable[[str, dict[str, Any] | None, int], Awaitable[None]]


@dataclass(slots=True)
class _DiscoveryModelResult:
    payload: dict[str, Any] | None
    usage: dict[str, Any] | None
    elapsed_ms: int

_ALLOWED_DISCOVERY_FIELD_TYPES = {"text", "textarea", "select", "radio", "cards", "checkbox"}
_FIELD_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_OPTION_VALUE_RE = re.compile(r"^[A-Za-z0-9:_-]+$")
_MAX_DISCOVERY_FIELDS = 12
_MAX_DISCOVERY_OPTIONS = 8
_MAX_TITLE_LENGTH = 80
_MAX_DESCRIPTION_LENGTH = 400
_MAX_LABEL_LENGTH = 120
_MAX_PLACEHOLDER_LENGTH = 160
_MAX_CONTEXT_CHARS = 1200
_MAX_DISCOVERY_SCHEMA_ATTEMPTS = 3
_FALLBACK_DISCOVERY_SCHEMA_MAX_TOKENS = 1200


def _interaction_request_id(kind: str, conversation_id: str) -> str:
    return f"{kind}:{conversation_id}:{uuid4().hex[:12]}"


_DIRECTIONS: list[DirectionOption] = [
    {
        "id": "editorial-contrast",
        "label": "Editorial Contrast",
        "description": "高对比排版、克制配色、适合内容驱动与高端叙事。",
        "metadata": {
            "palette": ["#F6F1E8", "#D6BFA7", "#1E1D1A", "#7C5C3B"],
            "display_font": "Canela",
            "body_font": "Inter",
            "references": ["Aesop", "Kinfolk", "Linear editorial"],
            "mood": "Refined, calm, intelligent",
            "posture": "Editorial luxury",
        },
    },
    {
        "id": "product-clarity",
        "label": "Product Clarity",
        "description": "偏 SaaS 的清晰结构、信息层次明确，适合产品说明与功能演示。",
        "metadata": {
            "palette": ["#F7FAFC", "#DCE7F5", "#0F172A", "#2563EB"],
            "display_font": "Suisse Int'l",
            "body_font": "Inter",
            "references": ["Stripe", "Vercel", "Framer"],
            "mood": "Clear, capable, modern",
            "posture": "Product-led confidence",
        },
    },
    {
        "id": "warm-brand-story",
        "label": "Warm Brand Story",
        "description": "偏品牌故事与情绪表达，适合消费品牌、发布页与讲述型 deck。",
        "metadata": {
            "palette": ["#FCF7EE", "#E6C9A8", "#5B4636", "#C06C4E"],
            "display_font": "Recoleta",
            "body_font": "Avenir Next",
            "references": ["Notion campaign", "Cereal", "Airbnb stories"],
            "mood": "Warm, human, polished",
            "posture": "Brand-forward storytelling",
        },
    },
    {
        "id": "bold-launch",
        "label": "Bold Launch",
        "description": "强节奏、大标题、适合新品发布、活动页和需要冲击力的视觉呈现。",
        "metadata": {
            "palette": ["#FFF6E9", "#FF9B52", "#151515", "#FF5B2E"],
            "display_font": "Druk",
            "body_font": "Inter",
            "references": ["Apple launch", "Figma Config", "Nike campaigns"],
            "mood": "Bold, energetic, sharp",
            "posture": "Launch momentum",
        },
    },
    {
        "id": "calm-minimal-tech",
        "label": "Calm Minimal Tech",
        "description": "轻技术感、低噪音、适合 AI / 工具 / 专业服务类产品。",
        "metadata": {
            "palette": ["#F5F7FA", "#C8D1DE", "#101828", "#4B6B8A"],
            "display_font": "Manrope",
            "body_font": "IBM Plex Sans",
            "references": ["Anthropic", "Arc", "OpenAI product pages"],
            "mood": "Calm, precise, modern",
            "posture": "Minimal technical trust",
        },
    },
]


def _is_zh(language: str) -> bool:
    return str(language or "").lower().startswith("zh")


def _t(language: str, zh: str, en: str) -> str:
    return zh if _is_zh(language) else en


def _conversation_design_system_id(conversation: dict[str, Any]) -> str | None:
    design_system_id = str(conversation.get("design_system_id") or "").strip()
    if design_system_id:
        return design_system_id

    runtime_state = conversation.get("runtime_state")
    if isinstance(runtime_state, dict):
        runtime_contract = runtime_state.get("runtime_contract")
        if isinstance(runtime_contract, dict):
            design_system_id = str(runtime_contract.get("design_system_id") or "").strip()
            if design_system_id:
                return design_system_id
    return None


def resolve_artifact_family(*, conversation: dict[str, Any], skill: Any | None) -> str:
    artifact_mode = str(
        conversation.get("artifact_mode")
        or getattr(skill, "artifact_mode", None)
        or "web"
    ).strip().lower()
    return artifact_mode or "web"


def conversation_has_reference_attachments(*, user_id: int, conversation_id: str) -> bool:
    for message in iter_messages_reverse(user_id, conversation_id, page_size=40):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        attachments = message.get("attachments")
        if isinstance(attachments, list) and any(isinstance(item, dict) for item in attachments):
            return True
    return False


def build_quick_brief_schema(
    *,
    language: str,
    artifact_family: str,
    conversation: dict[str, Any],
    skill: Any | None,
    has_reference_attachments: bool,
) -> dict[str, Any]:
    skill_name = str(getattr(skill, "name_zh", None) or getattr(skill, "name", None) or getattr(skill, "id", ""))
    fields: list[dict[str, Any]] = [
        {
            "id": "output",
            "label": _t(language, "这次要产出什么", "What should we make"),
            "type": "text",
            "required": True,
            "placeholder": _t(language, f"例如：{skill_name or '产品落地页'}", f"e.g. {skill_name or 'product landing page'}"),
        },
        {
            "id": "platform",
            "label": _t(language, "发布平台 / 使用场景", "Platform / usage context"),
            "type": "select",
            "required": True,
            "options": _platform_options(language, artifact_family),
        },
        {
            "id": "audience",
            "label": _t(language, "目标受众", "Audience"),
            "type": "text",
            "required": True,
            "placeholder": _t(language, "例如：潜在客户 / 管理层 / 投资人", "e.g. prospects / leadership / investors"),
        },
        {
            "id": "tone",
            "label": _t(language, "希望的语气与气质", "Tone"),
            "type": "select",
            "required": True,
            "options": _tone_options(language),
        },
    ]

    if not _conversation_design_system_id(conversation) and not has_reference_attachments:
        fields.append(
            {
                "id": "brand_context",
                "label": _t(language, "品牌与参考情况", "Brand / reference context"),
                "type": "radio",
                "required": True,
                "options": [
                    {
                        "label": _t(language, "已有品牌规范", "I have brand guidelines"),
                        "value": "have_brand_system",
                        "description": _t(language, "已有品牌色、字体、组件或现成规范。", "I already have brand colors, type, or a design system."),
                    },
                    {
                        "label": _t(language, "已有参考站/参考图", "I have references"),
                        "value": "have_reference",
                        "description": _t(language, "会提供参考网站、截图或参考视觉。", "I can provide reference sites, screenshots, or visuals."),
                    },
                    {
                        "label": _t(language, "没有，帮我定方向", "No, help me choose"),
                        "value": "need_direction",
                        "description": _t(language, "没有品牌规范和参考，希望系统给出视觉方向。", "I want the system to propose a visual direction."),
                    },
                ],
            }
        )

    if artifact_family not in {"slides", "web", "document"}:
        fields.append(
            {
                "id": "scale",
                "label": _t(language, "范围 / 规模", "Scope"),
                "type": "select",
                "required": True,
                "options": _scale_options(language, artifact_family),
            }
        )
    fields.append(
        {
            "id": "constraints",
            "label": _t(language, "必须遵守的约束", "Constraints"),
            "type": "textarea",
            "required": False,
            "placeholder": _t(language, "例如：移动端优先、必须双语、要突出价格信息", "e.g. mobile first, bilingual, emphasize pricing"),
        }
    )

    if artifact_family == "slides":
        fields.extend(
            [
                {
                    "id": "speaker_notes",
                    "label": _t(language, "讲稿备注需要到什么程度", "Speaker notes"),
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"label": _t(language, "不需要", "No notes"), "value": "none"},
                        {"label": _t(language, "简要提示", "Light notes"), "value": "light"},
                        {"label": _t(language, "详细备注", "Detailed notes"), "value": "detailed"},
                    ],
                },
                {
                    "id": "slide_count",
                    "label": _t(language, "页数范围", "Slide count"),
                    "type": "select",
                    "required": True,
                    "options": [
                        {"label": "5-8", "value": "5_8"},
                        {"label": "10-15", "value": "10_15"},
                        {"label": "15+", "value": "15_plus"},
                    ],
                },
            ]
        )
    elif artifact_family == "web":
        fields.extend(
            [
                {
                    "id": "device_scope",
                    "label": _t(language, "设备范围", "Device scope"),
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"label": _t(language, "桌面优先", "Desktop first"), "value": "desktop_first"},
                        {"label": _t(language, "移动优先", "Mobile first"), "value": "mobile_first"},
                        {"label": _t(language, "响应式双端", "Responsive"), "value": "responsive"},
                    ],
                },
                {
                    "id": "page_or_screen_count",
                    "label": _t(language, "页数 / 屏数", "Page or screen count"),
                    "type": "select",
                    "required": True,
                    "options": [
                        {"label": _t(language, "单页", "Single surface"), "value": "single_surface"},
                        {"label": _t(language, "2-5 页/屏", "2-5 surfaces"), "value": "2_5_surfaces"},
                        {"label": _t(language, "多页流程", "Multi-step flow"), "value": "multi_step_flow"},
                    ],
                },
            ]
        )
    elif artifact_family == "document":
        fields.extend(
            [
                {
                    "id": "doc_depth",
                    "label": _t(language, "内容深度", "Document depth"),
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"label": _t(language, "简版概览", "Brief overview"), "value": "overview"},
                        {"label": _t(language, "中等深度", "Moderate depth"), "value": "moderate"},
                        {"label": _t(language, "深入完整", "Deep / comprehensive"), "value": "deep"},
                    ],
                },
                {
                    "id": "tone_of_writing",
                    "label": _t(language, "文风", "Writing tone"),
                    "type": "select",
                    "required": True,
                    "options": [
                        {"label": _t(language, "专业正式", "Formal"), "value": "formal"},
                        {"label": _t(language, "清晰直接", "Clear and direct"), "value": "clear_direct"},
                        {"label": _t(language, "偏叙事", "Narrative"), "value": "narrative"},
                    ],
                },
            ]
        )

    schema = {
        "title": _t(language, "Quick brief", "Quick brief"),
        "description": _t(
            language,
            "先锁定这次产出的关键约束，后面的大纲、方向和执行都会基于这里的答案。",
            "Lock the core constraints first. Planning and execution will use these answers as the baseline.",
        ),
        "submit_label": _t(language, "提交", "Submit"),
        "fields": fields,
    }
    return _normalize_fallback_quick_brief_schema(schema)


def _safe_text(value: Any, *, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if max_length is None:
        return text
    return text[:max_length].strip()


def _selected_design_system_id(conversation: dict[str, Any]) -> str:
    return _conversation_design_system_id(conversation) or ""


def _clean_design_system_title(title: Any) -> str:
    text = str(title or "").strip()
    for prefix in ("Design System Inspired by ", "Design System for "):
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip() or text
    return text


def _clean_design_system_description(description: Any, category: Any) -> str:
    category_text = str(category or "").strip()
    text = str(description or "").strip()
    if text.lower().startswith("category:"):
        text = text.split(":", 1)[1].strip()
    return text or category_text


def _recent_user_context(*, user_id: int | None, conversation_id: str | None) -> str:
    if user_id is None or not conversation_id:
        return ""
    snippets: list[str] = []
    for message in iter_messages_reverse(user_id, conversation_id, page_size=20):
        if not isinstance(message, dict) or str(message.get("role") or "") != "user":
            continue
        content = _safe_text(message.get("content"), max_length=400)
        if content:
            snippets.append(content)
        if len(snippets) >= 2:
            break
    snippets.reverse()
    return "\n".join(snippets)[:_MAX_CONTEXT_CHARS].strip()


def _attachments_summary(*, user_id: int | None, conversation_id: str | None) -> list[dict[str, str]]:
    if user_id is None or not conversation_id:
        return []
    attachments: list[dict[str, str]] = []
    for message in iter_messages_reverse(user_id, conversation_id, page_size=20):
        if not isinstance(message, dict) or str(message.get("role") or "") != "user":
            continue
        raw_attachments = message.get("attachments")
        if not isinstance(raw_attachments, list):
            continue
        for item in raw_attachments[:8]:
            if not isinstance(item, dict):
                continue
            attachments.append(
                {
                    "type": _safe_text(item.get("type") or "file", max_length=24) or "file",
                    "name": _safe_text(item.get("name") or item.get("filename"), max_length=120),
                }
            )
        if attachments:
            break
    return attachments


def _skill_discovery_summary(skill: Any | None) -> dict[str, Any]:
    if skill is None:
        return {}
    description = (
        getattr(skill, "description_en", None)
        or getattr(skill, "description", None)
        or getattr(skill, "name_en", None)
        or getattr(skill, "name", None)
        or ""
    )
    input_schema = getattr(skill, "input_schema", None)
    important_inputs: list[str] = []
    if isinstance(input_schema, list):
        for item in input_schema[:6]:
            if not isinstance(item, dict):
                continue
            field_id = _safe_text(item.get("id") or item.get("name"), max_length=60)
            if field_id:
                important_inputs.append(field_id)
    return {
        "id": getattr(skill, "id", None),
        "name": getattr(skill, "name_en", None) or getattr(skill, "name", None),
        "description": _safe_text(description, max_length=240),
        "primary_output": getattr(skill, "primary_output", None),
        "execution_strategy": getattr(skill, "execution_strategy", None),
        "important_inputs": important_inputs,
    }


def _build_discovery_schema_system_prompt(language: str, *, design_system_selected: bool) -> str:
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.PLANNING_SCHEMA_GENERATION,
            phase=Phase.PLANNING,
            language=language,
            side_payload={"design_system_selected": design_system_selected},
        )
    )
    return bundle.rendered_system


def _build_discovery_schema_user_prompt(
    *,
    conversation: dict[str, Any],
    language: str,
    artifact_family: str,
    skill: Any | None,
    has_reference_attachments: bool,
    user_id: int | None,
) -> str:
    conversation_id = str(conversation.get("id") or "").strip() or None
    design_system_id = _selected_design_system_id(conversation)
    payload = {
        "locale": language,
        "runtime_time": runtime_time_payload(),
        "artifact_family": artifact_family,
        "resolved_skill": _skill_discovery_summary(skill),
        "design_system_selected": bool(design_system_id),
        "selected_design_system_id": design_system_id or None,
        "has_reference_attachments": has_reference_attachments,
        "attachments_summary": _attachments_summary(user_id=user_id, conversation_id=conversation_id),
        "recent_user_context": _recent_user_context(user_id=user_id, conversation_id=conversation_id),
    }
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.PLANNING_SCHEMA_GENERATION,
            phase=Phase.PLANNING,
            language=language,
            side_payload=payload,
        )
    )
    return str((bundle.messages or [{}])[0].get("content") or "")


def _normalize_schema_option(raw: Any, *, fallback_value: str = "") -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"label": raw, "value": raw}
    if not isinstance(raw, dict):
        return None
    label = _safe_text(raw.get("label"))
    value = _safe_text(raw.get("value"))
    if label and (not value or not _OPTION_VALUE_RE.fullmatch(value)):
        value = _slug_value(label) or fallback_value
    if not label or not value or not _OPTION_VALUE_RE.fullmatch(value):
        return None
    option: dict[str, Any] = {
        "label": label,
        "value": value,
    }
    description = _safe_text(raw.get("description"))
    if description:
        option["description"] = description
    metadata = raw.get("metadata")
    if isinstance(metadata, dict) and metadata:
        option["metadata"] = metadata
    return option


def _slug_identifier(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if slug and slug[0].isdigit():
        slug = f"field_{slug}"
    return slug or fallback


def _slug_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9:_-]+", "_", text).strip("_")
    return re.sub(r"_+", "_", slug)


def _first_option_value(options: list[dict[str, Any]] | None) -> str | None:
    if not options:
        return None
    value = _safe_text(options[0].get("value"))
    return value or None


def _match_option_value(raw_default: Any, options: list[dict[str, Any]] | None) -> str | None:
    value = _safe_text(raw_default)
    if not value or not options:
        return None
    by_value = {_safe_text(option.get("value")): _safe_text(option.get("value")) for option in options}
    if value in by_value:
        return by_value[value]
    folded = value.lower()
    for option in options:
        option_value = _safe_text(option.get("value"))
        option_label = _safe_text(option.get("label"))
        candidates = {
            option_value.lower(),
            option_label.lower(),
            _slug_identifier(option_value),
            _slug_identifier(option_label),
            _slug_value(option_value),
            _slug_value(option_label),
        }
        if folded in candidates or _slug_identifier(value) in candidates or _slug_value(value) in candidates:
            return option_value
    return None


def _normalize_default_value(
    *,
    field_type: str,
    raw_default: Any,
    options: list[dict[str, Any]] | None,
) -> tuple[Any, list[str]]:
    errors: list[str] = []
    if raw_default is None:
        return None, errors
    if field_type in {"text", "textarea"}:
        text = str(raw_default).strip()
        if not text:
            return None, errors
        return text, errors
    if field_type in {"select", "radio", "cards"}:
        return _match_option_value(raw_default, options) or _first_option_value(options), errors
    if field_type == "checkbox":
        values = raw_default if isinstance(raw_default, list) else [raw_default]
        normalized = [
            matched
            for value in values
            if (matched := _match_option_value(value, options)) is not None
        ]
        if normalized:
            return normalized[:2], errors
        first_value = _first_option_value(options)
        return ([first_value] if first_value else None), errors
    return None, errors


def _fallback_text_default(field: dict[str, Any]) -> str:
    placeholder = str(field.get("placeholder") or "").strip()
    if placeholder:
        for prefix in ("例如：", "例如:", "e.g. ", "e.g.", "eg. "):
            if placeholder.lower().startswith(prefix.lower()):
                candidate = placeholder[len(prefix):].strip()
                if candidate:
                    return candidate
        return placeholder
    return str(field.get("label") or "").strip()


def _autofill_required_default_values(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    fields_raw = raw.get("fields")
    if not isinstance(fields_raw, list):
        return normalized

    next_fields: list[dict[str, Any]] = []
    for field_raw in fields_raw:
        if not isinstance(field_raw, dict):
            next_fields.append(field_raw)
            continue
        field = dict(field_raw)
        if field.get("required") and field.get("default_value", field.get("defaultValue")) is None:
            field_type = str(field.get("type") or "").strip()
            options = [
                option
                for option in (
                    _normalize_schema_option(item, fallback_value=f"option_{index + 1}")
                    for index, item in enumerate(
                        field.get("options") if isinstance(field.get("options"), list) else []
                    )
                )
                if option is not None
            ]
            default_value: Any | None = None
            if field_type in {"select", "radio", "cards"} and options:
                default_value = options[0].get("value")
            elif field_type == "checkbox" and options:
                first_value = options[0].get("value")
                default_value = [first_value] if first_value else None
            elif field.get("required") and field_type == "text":
                default_value = _fallback_text_default(field)
            if default_value is not None:
                field["default_value"] = default_value
        next_fields.append(field)

    normalized["fields"] = next_fields
    return normalized


def _normalize_fallback_quick_brief_schema(raw: Any) -> QuickBriefSchema:
    normalized, errors = _validate_generated_quick_brief_schema(_autofill_required_default_values(raw))
    if normalized is None:
        raise ValueError(f"Internal quick brief fallback schema is invalid: {errors}")
    return normalized


def _validate_generated_quick_brief_schema(raw: Any) -> tuple[QuickBriefSchema | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["schema must be a JSON object"]
    title = _safe_text(raw.get("title"))
    submit_label = _safe_text(raw.get("submit_label") or raw.get("submitLabel"))
    if not title or not submit_label:
        return None, ["title and submit_label are required"]
    description = _safe_text(raw.get("description"))
    fields_raw = raw.get("fields")
    if not isinstance(fields_raw, list) or len(fields_raw) < 2:
        return None, [f"fields must contain at least 2 items"]
    fields_raw = fields_raw[:_MAX_DISCOVERY_FIELDS]

    normalized_fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, field_raw in enumerate(fields_raw):
        if not isinstance(field_raw, dict):
            return None, [f"field[{index}] must be an object"]
        raw_field_id = _safe_text(field_raw.get("id"))
        label = _safe_text(field_raw.get("label"))
        field_type = _safe_text(field_raw.get("type"))
        if not label or field_type not in _ALLOWED_DISCOVERY_FIELD_TYPES:
            return None, [f"field[{index}] must include valid id, label, and supported type"]
        field_id = raw_field_id if _FIELD_ID_RE.fullmatch(raw_field_id) else _slug_identifier(
            raw_field_id or label,
            fallback=f"field_{index + 1}",
        )
        if not _FIELD_ID_RE.fullmatch(field_id) or field_id in seen_ids:
            return None, [f"field[{index}] id '{field_id}' must be unique snake_case"]
        seen_ids.add(field_id)

        field: dict[str, Any] = {
            "id": field_id,
            "label": label,
            "type": field_type,
            "required": bool(field_raw.get("required", False)),
        }
        placeholder = _safe_text(field_raw.get("placeholder"))
        if placeholder:
            field["placeholder"] = placeholder

        normalized_options: list[dict[str, Any]] | None = None
        if field_type in {"select", "radio", "cards", "checkbox"}:
            options_raw = field_raw.get("options")
            if not isinstance(options_raw, list) or not options_raw:
                return None, [f"field[{index}] type '{field_type}' requires non-empty options"]
            normalized_options = [
                option
                for option in (
                    _normalize_schema_option(item, fallback_value=f"option_{index + 1}")
                    for index, item in enumerate(options_raw[:_MAX_DISCOVERY_OPTIONS])
                )
                if option is not None
            ]
            if not normalized_options:
                return None, [f"field[{index}] options must include valid label/value pairs"]
            field["options"] = normalized_options

        default_value, default_errors = _normalize_default_value(
            field_type=field_type,
            raw_default=field_raw.get("default_value", field_raw.get("defaultValue")),
            options=normalized_options,
        )
        if field["required"] and default_value is None and field_type != "textarea":
            default_value = _normalize_default_value(
                field_type=field_type,
                raw_default=_fallback_text_default(field) if field_type == "text" else _first_option_value(normalized_options),
                options=normalized_options,
            )[0]
        if field["required"] and field_type == "checkbox" and not default_value:
            field["required"] = False
        if default_errors:
            return None, [f"field[{index}] {message}" for message in default_errors]
        if default_value is not None:
            field["default_value"] = default_value
        normalized_fields.append(field)

    return ({
        "title": title,
        "description": description,
        "submit_label": submit_label,
        "fields": normalized_fields,
    }, errors)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _quick_brief_schema_tool() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "submit_quick_brief_schema",
                "description": "Submit one complete Quick brief form schema.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "schema": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "submit_label": {"type": "string"},
                                "fields": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": _MAX_DISCOVERY_FIELDS,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": True,
                                        "properties": {
                                            "id": {"type": "string"},
                                            "label": {"type": "string"},
                                            "type": {
                                                "type": "string",
                                                "enum": sorted(_ALLOWED_DISCOVERY_FIELD_TYPES),
                                            },
                                            "required": {"type": "boolean"},
                                            "default_value": {},
                                            "placeholder": {"type": "string"},
                                            "options": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "additionalProperties": False,
                                                    "properties": {
                                                        "label": {
                                                            "type": "string",
                                                            "description": "User-visible option text. Use this key exactly; do not use name, text, title, or other aliases.",
                                                        },
                                                        "value": {
                                                            "type": "string",
                                                            "description": "Stable ASCII option id used for form submission, for example live_presentation. Must not be Chinese display text.",
                                                        },
                                                        "description": {
                                                            "type": "string",
                                                            "description": "Optional short helper text for this option.",
                                                        },
                                                    },
                                                    "required": ["label", "value"],
                                                },
                                            },
                                        },
                                        "required": ["id", "label", "type", "required"],
                                    },
                                },
                            },
                            "required": ["title", "submit_label", "fields"],
                        }
                    },
                    "required": ["schema"],
                },
            },
        }
    ]


def _parse_quick_brief_schema_tool_call(tool_calls: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for tool_call in tool_calls or []:
        if tool_call_name(tool_call) != "submit_quick_brief_schema":
            continue
        raw_args = tool_call_arguments(tool_call)
        if not isinstance(raw_args, dict):
            return None
        schema = raw_args.get("schema", raw_args)
        return schema if isinstance(schema, dict) else None
    return None


def _quick_brief_field_shapes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), list):
        return []
    shapes: list[dict[str, Any]] = []
    for field in raw.get("fields")[:_MAX_DISCOVERY_FIELDS]:
        if not isinstance(field, dict):
            shapes.append({"type": type(field).__name__})
            continue
        options = field.get("options")
        shapes.append(
            {
                "id": field.get("id"),
                "type": field.get("type"),
                "required": field.get("required"),
                "option_count": len(options) if isinstance(options, list) else None,
            }
        )
    return shapes


def _resolve_discovery_schema_max_tokens(model_name: str) -> int:
    max_tokens = int(resolve_effective_max_tokens(model_name, 0) or 0)
    return max_tokens if max_tokens > 0 else _FALLBACK_DISCOVERY_SCHEMA_MAX_TOKENS


async def _call_discovery_schema_model(
    *,
    system_prompt: str,
    user_prompt: str,
    model_name: str,
    api_key: str,
) -> _DiscoveryModelResult:
    provider = create_harness_model_provider(api_key=api_key)
    chunks: list[str] = []
    usage: dict[str, Any] | None = None
    tool_payload: dict[str, Any] | None = None
    started = time.monotonic()
    async for chunk in provider.chat_stream(
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
        tools=_quick_brief_schema_tool(),
        tool_choice={"type": "function", "function": {"name": "submit_quick_brief_schema"}},
        model=model_name,
        temperature=0.1,
        max_tokens=_resolve_discovery_schema_max_tokens(model_name),
    ):
        if chunk.usage:
            usage = chunk.usage
        if chunk.tool_calls:
            tool_payload = _parse_quick_brief_schema_tool_call(chunk.tool_calls) or tool_payload
        if chunk.content:
            chunks.append(str(chunk.content))
    return _DiscoveryModelResult(
        payload=tool_payload or _extract_json_object("".join(chunks)),
        usage=usage,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


async def generate_quick_brief_schema(
    *,
    conversation: dict[str, Any],
    language: str,
    artifact_family: str,
    skill: Any | None,
    has_reference_attachments: bool,
    user_id: int | None = None,
    run_id: str | None = None,
    on_model_call: DiscoveryModelCallback | None = None,
    retry_diagnostics: list[dict[str, Any]] | None = None,
) -> QuickBriefSchema:
    fallback = build_quick_brief_schema(
        language=language,
        artifact_family=artifact_family,
        conversation=conversation,
        skill=skill,
        has_reference_attachments=has_reference_attachments,
    )
    if skill is None:
        return fallback

    design_system_selected = bool(_selected_design_system_id(conversation))
    model_name = (
        ((conversation.get("model_preferences") or {}) if isinstance(conversation, dict) else {}).get("multimodal_model")
        or get_default_multimodal_model()
    )
    system_prompt = _build_discovery_schema_system_prompt(
        language,
        design_system_selected=design_system_selected,
    )
    user_prompt_bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.PLANNING_SCHEMA_GENERATION,
            phase=Phase.PLANNING,
            language=language,
            side_payload={
                "locale": language,
                "runtime_time": runtime_time_payload(),
                "artifact_family": artifact_family,
                "resolved_skill": _skill_discovery_summary(skill),
                "design_system_selected": design_system_selected,
                "selected_design_system_id": _selected_design_system_id(conversation) or None,
                "has_reference_attachments": has_reference_attachments,
                "attachments_summary": _attachments_summary(user_id=user_id, conversation_id=str(conversation.get("id") or "").strip() or None),
                "recent_user_context": _recent_user_context(user_id=user_id, conversation_id=str(conversation.get("id") or "").strip() or None),
            },
        )
    )
    persist_prompt_bundle_trace(
        user_id=user_id,
        conversation_id=str(conversation.get("id") or "").strip() or None,
        run_id=run_id,
        bundle=user_prompt_bundle,
        summary="Prompt bundle assembled (quick brief schema)",
    )
    user_prompt = str(user_prompt_bundle.messages[0]["content"])

    retry_feedback: list[str] = []
    retry_response: Any | None = None
    for attempt in range(1, _MAX_DISCOVERY_SCHEMA_ATTEMPTS + 1):
        request_payload = user_prompt
        if retry_feedback:
            retry_payload: dict[str, Any] = {
                "generation_request": json.loads(user_prompt),
                "validation_errors": retry_feedback,
                "retry_attempt": attempt,
                "instruction": "Regenerate the full schema and fix every validation error. Do not repeat the same mistake.",
            }
            if retry_response is not None:
                retry_payload["previous_response"] = retry_response
            request_payload = json.dumps(retry_payload, ensure_ascii=False)
        try:
            generated = await _call_discovery_schema_model(
                system_prompt=system_prompt,
                user_prompt=request_payload,
                model_name=model_name,
                api_key=(await resolve_user_apimart_key_for_context(user_id) if user_id is not None else ""),
            )
            if on_model_call is not None:
                await on_model_call(model_name, generated.usage, generated.elapsed_ms)
            retry_response = generated.payload
            validated, validation_errors = _validate_generated_quick_brief_schema(generated.payload)
            if validated is not None:
                return validated
            if retry_diagnostics is not None:
                retry_diagnostics.append(
                    {
                        "attempt": attempt,
                        "validation_errors": validation_errors or ["schema validation failed"],
                        "field_shapes": _quick_brief_field_shapes(generated.payload),
                    }
                )
            retry_feedback = validation_errors or ["schema validation failed"]
        except Exception as exc:
            logger.exception("Quick brief AI schema generation failed")
            retry_feedback = [f"schema generation raised an exception: {exc}"]
            retry_response = {
                "error": type(exc).__name__,
                "message": str(exc),
            }
            if retry_diagnostics is not None:
                retry_diagnostics.append(
                    {
                        "attempt": attempt,
                        "validation_errors": retry_feedback,
                        "field_shapes": [],
                    }
                )
    return fallback


def build_direction_schema(*, language: str) -> dict[str, Any]:
    return {
        "title": _t(language, "Pick a visual direction", "Pick a visual direction"),
        "description": _t(
            language,
            "当前没有品牌规范或参考视觉，先选一个方向作为临时视觉系统。",
            "There is no brand system or visual reference yet, so choose a direction to establish a temporary visual system.",
        ),
        "submit_label": _t(language, "锁定方向", "Lock direction"),
        "fields": [
            {
                "id": "direction",
                "label": _t(language, "视觉方向", "Visual direction"),
                "type": "cards",
                "required": True,
                "options": [
                    {
                        "label": option["label"],
                        "value": option["id"],
                        "description": option["description"],
                        "metadata": option["metadata"],
                    }
                    for option in _DIRECTIONS
                ],
            }
        ],
    }


def _brief_keywords(*values: Any) -> set[str]:
    keywords: set[str] = set()
    for value in values:
        if isinstance(value, list):
            keywords.update(_brief_keywords(*value))
            continue
        text = str(value or "").strip().lower()
        if not text:
            continue
        normalized = (
            text.replace("/", " ")
            .replace("_", " ")
            .replace("-", " ")
            .replace(",", " ")
        )
        keywords.update(part for part in normalized.split() if part)
    return keywords


def _score_design_system_candidate(
    *,
    metadata: DesignSystemResolverMetadata | None,
    artifact_family: str,
    discovery_brief: dict[str, Any],
    skill: Any | None,
) -> int:
    score = 30
    tone = str(discovery_brief.get("tone") or "").strip().lower()
    platform = str(discovery_brief.get("platform") or "").strip().lower()
    output = str(discovery_brief.get("output") or "").strip().lower()
    audience = str(discovery_brief.get("audience") or "").strip().lower()
    scale = str(discovery_brief.get("scale") or discovery_brief.get("page_or_screen_count") or "").strip().lower()
    keywords = _brief_keywords(
        tone,
        platform,
        output,
        audience,
        scale,
        getattr(skill, "id", None),
        getattr(skill, "name", None),
    )

    if metadata is None:
        return score

    preferred_map = {
        "web": {"landing-page", "company-site", "product-page", "dashboard"},
        "document": {"docs"},
        "slides": {"landing-page", "company-site", "product-page"},
    }
    for preferred in metadata.preferred_for:
        if preferred in preferred_map.get(artifact_family, set()):
            score += 12
            break

    tone_map = {
        "professional_restrained": {"professional", "balanced"},
        "confident_modern": {"modern", "product", "technical", "structured"},
        "warm_approachable": {"friendly", "creative", "marketing"},
        "premium_confident": {"premium", "luxury", "editorial", "brand-led"},
    }
    for tag in tone_map.get(tone, set()):
        if tag in {item.lower() for item in metadata.resolver_tags} or tag == metadata.tone.lower():
            score += 7

    keyword_bonus_map = {
        "dashboard": {"dashboard", "analytics", "data", "admin"},
        "docs": {"docs", "documentation", "knowledge", "report", "memo"},
        "product": {"product", "saas", "app", "application"},
        "marketing": {"marketing", "campaign", "launch", "landing"},
        "editorial": {"editorial", "story", "content", "narrative"},
        "creative": {"creative", "portfolio", "studio", "brand"},
        "enterprise": {"enterprise", "internal", "ops", "b2b"},
    }
    lowered_tags = {item.lower() for item in metadata.resolver_tags}
    for tag, tag_keywords in keyword_bonus_map.items():
        if tag in lowered_tags and keywords.intersection(tag_keywords):
            score += 6

    if artifact_family == "document" and metadata.density in {"dense", "balanced"}:
        score += 4
    if artifact_family == "slides" and metadata.tone in {"professional", "premium", "editorial"}:
        score += 4
    if artifact_family == "web" and metadata.category.lower() in {"product & saas", "commerce & marketing", "dashboard & data"}:
        score += 4

    penalty_keywords = _brief_keywords(metadata.avoid_for)
    if keywords.intersection(penalty_keywords):
        score -= 8
    if metadata.featured_priority is not None:
        score += max(0, 6 - min(metadata.featured_priority, 6))
    return score


def _score_direction_candidate(
    *,
    direction: DirectionOption,
    artifact_family: str,
    discovery_brief: dict[str, Any],
    skill: Any | None,
) -> int:
    score = 26
    tone = str(discovery_brief.get("tone") or "").strip().lower()
    platform = str(discovery_brief.get("platform") or "").strip().lower()
    output = str(discovery_brief.get("output") or "").strip().lower()
    audience = str(discovery_brief.get("audience") or "").strip().lower()
    keywords = _brief_keywords(
        tone,
        platform,
        output,
        audience,
        getattr(skill, "id", None),
        getattr(skill, "name", None),
        direction.get("label"),
        direction.get("description"),
        (direction.get("metadata") or {}).get("references"),
        (direction.get("metadata") or {}).get("mood"),
        (direction.get("metadata") or {}).get("posture"),
    )

    if tone == "premium_confident" and {"editorial", "luxury", "brand"}.intersection(keywords):
        score += 10
    if tone == "confident_modern" and {"product", "modern", "technical", "launch"}.intersection(keywords):
        score += 10
    if tone == "warm_approachable" and {"warm", "human", "story", "brand"}.intersection(keywords):
        score += 10
    if tone == "professional_restrained" and {"calm", "minimal", "clear", "editorial"}.intersection(keywords):
        score += 8

    if artifact_family == "slides" and {"launch", "story", "editorial"}.intersection(keywords):
        score += 4
    if artifact_family == "web" and {"product", "saas", "marketing", "launch"}.intersection(keywords):
        score += 4
    if artifact_family == "document" and {"editorial", "content", "calm"}.intersection(keywords):
        score += 4
    return score


def build_design_system_schema(
    *,
    language: str,
    artifact_family: str,
    discovery_brief: dict[str, Any],
    skill: Any | None,
) -> dict[str, Any]:
    options: list[dict[str, Any]] = []

    for system in list_design_system_summaries_sync():
        metadata = _metadata_from_design_system_summary(system)
        options.append(
            {
                "label": _clean_design_system_title(system.title),
                "value": system.id,
                "description": _clean_design_system_description(system.description, system.category),
                "metadata": {
                    "option_type": "design_system",
                    "category": system.category,
                    "palette": system.palette,
                    "mood": metadata.tone if metadata is not None else system.category,
                    "posture": metadata.resolver_summary if metadata is not None else system.description,
                    "references": metadata.preferred_for if metadata is not None else system.sections,
                    "display_font": None,
                    "body_font": None,
                    "score": _score_design_system_candidate(
                        metadata=metadata,
                        artifact_family=artifact_family,
                        discovery_brief=discovery_brief,
                        skill=skill,
                    ),
                },
            }
        )

    ranked_options = sorted(
        options,
        key=lambda item: (
            -int((item.get("metadata") or {}).get("score") or 0),
            str(item.get("label") or ""),
        ),
    )[:6]

    return {
        "title": _t(language, "选择设计体系", "Choose a design system"),
        "description": _t(
            language,
            "当前还没有锁定设计体系。先从推荐的设计体系里选一个，后续会基于它规划与执行。",
            "There is no locked design system yet. Choose one of the recommended design systems to guide planning and execution.",
        ),
        "submit_label": _t(language, "确认设计体系", "Confirm design system"),
        "fields": [
            {
                "id": "design_system_id",
                "label": _t(language, "设计体系", "Design system"),
                "type": "cards",
                "required": True,
                "options": ranked_options,
            }
        ],
    }


def _metadata_from_design_system_summary(system: DesignSystemSummary) -> DesignSystemResolverMetadata:
    return DesignSystemResolverMetadata(
        id=system.id,
        resolver_summary=system.resolver_summary,
        resolver_tags=list(system.resolver_tags),
        preferred_for=list(system.preferred_for),
        avoid_for=list(system.avoid_for),
        tone=system.tone,
        density=system.density,
        category=str(system.category or "Product & SaaS"),
        featured_priority=system.featured,
    )


async def build_quick_brief_interaction(
    *,
    conversation_id: str,
    language: str,
    artifact_family: str,
    conversation: dict[str, Any],
    skill: Any | None,
    has_reference_attachments: bool,
    user_id: int | None = None,
    run_id: str | None = None,
    on_model_call: DiscoveryModelCallback | None = None,
    retry_diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schema = await generate_quick_brief_schema(
        conversation=conversation,
        language=language,
        artifact_family=artifact_family,
        skill=skill,
        has_reference_attachments=has_reference_attachments,
        user_id=user_id,
        run_id=run_id,
        on_model_call=on_model_call,
        retry_diagnostics=retry_diagnostics,
    )
    return {
        "request_id": _interaction_request_id("quick-brief", conversation_id),
        "tool_call_id": None,
        "kind": "quick_brief",
        "question": schema["title"],
        "schema": schema,
        "status": "pending",
    }


def _build_design_system_schema_from_recommendations(
    *,
    language: str,
    recommendations: list[Any],
) -> dict[str, Any]:
    def _build_references(item: Any, title: str) -> list[str]:
        raw_references = getattr(item, "references", None)
        if isinstance(raw_references, list):
            references = [str(reference).strip() for reference in raw_references if str(reference).strip()]
            if references:
                return references[:3]
        return [title] if title else []

    options: list[dict[str, Any]] = []
    for item in recommendations[:6]:
        design_system_id = str(getattr(item, "id", "") or "").strip()
        if not design_system_id:
            continue
        title = str(getattr(item, "title", "") or "").strip() or design_system_id
        description = str(getattr(item, "description", "") or "").strip()
        category = str(getattr(item, "category", "") or "").strip()
        palette = list(getattr(item, "palette", []) or [])
        reasoning_summary = str(getattr(item, "reasoning_summary", "") or "").strip()
        references = _build_references(item, title)
        options.append(
            {
                "label": title,
                "value": design_system_id,
                "description": description or category or title,
                "metadata": {
                    "option_type": "design_system",
                    "category": category or None,
                    "palette": palette,
                    "mood": category or None,
                    "posture": reasoning_summary or description or title,
                    "references": references,
                    "display_font": None,
                    "body_font": None,
                    "confidence": float(getattr(item, "confidence", 0.0) or 0.0),
                    "rank": int(getattr(item, "rank", len(options) + 1) or len(options) + 1),
                },
            }
        )
    return {
        "title": _t(language, "选择设计体系", "Choose a design system"),
        "description": _t(
            language,
            "当前还没有锁定品牌规范或参考视觉。先从 AI 推荐的设计体系里选一个，后续会基于它规划与执行。",
            "There is no locked brand system or visual reference yet. Choose one of the AI-recommended design systems to guide planning and execution.",
        ),
        "submit_label": _t(language, "确认设计体系", "Confirm design system"),
        "fields": [
            {
                "id": "design_system_id",
                "label": _t(language, "设计体系", "Design system"),
                "type": "cards",
                "required": True,
                "options": options,
            }
        ],
    }


def build_direction_interaction(*, conversation_id: str, language: str) -> dict[str, Any]:
    schema = build_direction_schema(language=language)
    return {
        "request_id": _interaction_request_id("visual-direction", conversation_id),
        "tool_call_id": None,
        "kind": "visual_direction_picker",
        "question": schema["title"],
        "schema": schema,
        "status": "pending",
    }


async def build_design_system_interaction(
    *,
    conversation_id: str,
    language: str,
    artifact_family: str,
    conversation: dict[str, Any],
    discovery_brief: dict[str, Any],
    skill: Any | None,
    current_design_system_id: str | None = None,
    user_id: int | None = None,
    run_id: str | None = None,
    on_model_call: DiscoveryModelCallback | None = None,
) -> dict[str, Any]:
    prompt_summary = " | ".join(
        str(value).strip()
        for value in [
            discovery_brief.get("output"),
            discovery_brief.get("platform"),
            discovery_brief.get("audience"),
            discovery_brief.get("tone"),
            discovery_brief.get("scale") or discovery_brief.get("page_or_screen_count"),
            discovery_brief.get("constraints"),
        ]
        if str(value or "").strip()
    )
    resolution = await resolve_design_system_selection(
        artifact_mode=artifact_family,
        prompt=prompt_summary or json.dumps(discovery_brief or {}, ensure_ascii=False),
        attachments=None,
        current_design_system_id=current_design_system_id,
        discovery_brief=discovery_brief,
        skill_id=getattr(skill, "id", None),
        model_preferences=(conversation.get("model_preferences") or {}) if isinstance(conversation, dict) else None,
        user_id=user_id,
        conversation_id=str(conversation.get("id") or "").strip() or conversation_id,
        run_id=run_id,
    )
    if on_model_call is not None and resolution.model_name:
        await on_model_call(
            resolution.model_name,
            resolution.usage,
            int(resolution.elapsed_ms or 0),
        )
    schema = _build_design_system_schema_from_recommendations(
        language=language,
        recommendations=resolution.recommendations,
    )
    return {
        "request_id": _interaction_request_id("design-system", conversation_id),
        "tool_call_id": None,
        "kind": "design_system_picker",
        "question": schema["title"],
        "schema": schema,
        "status": "pending",
    }


def normalize_answers(raw_answers: Any, answer: str | None = None) -> dict[str, Any]:
    if isinstance(raw_answers, dict):
        return dict(raw_answers)
    if isinstance(raw_answers, str):
        try:
            parsed = json.loads(raw_answers)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    text = str(answer or "").strip()
    if not text:
        return {}
    return {"answer": text}


def _flatten_structured_choice_answer(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = str(value.get("value") or "").strip()
        if normalized:
            return normalized
        label = str(value.get("label") or "").strip()
        return label or ""
    if isinstance(value, list):
        flattened: list[Any] = []
        for entry in value:
            normalized_entry = _flatten_structured_choice_answer(entry)
            if normalized_entry in (None, "", []):
                continue
            flattened.append(normalized_entry)
        return flattened
    return value


def normalize_interaction_answers(
    *,
    raw_answers: Any,
    answer: str | None = None,
    display_label: str | None = None,
    pending_interaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_answers(raw_answers, answer)
    pending = pending_interaction if isinstance(pending_interaction, dict) else {}
    kind = str(pending.get("kind") or "").strip()
    if kind == "quick_brief":
        return {
            key: _flatten_structured_choice_answer(value)
            for key, value in normalized.items()
        }
    if kind != "design_system_picker":
        return normalized
    if str(normalized.get("design_system_id") or "").strip():
        return normalized

    candidates = [
        normalized.get("answer"),
        answer,
        display_label,
    ]
    candidate_texts = {
        str(candidate).strip().casefold()
        for candidate in candidates
        if str(candidate or "").strip()
    }
    if not candidate_texts:
        return normalized

    schema = pending.get("schema") if isinstance(pending.get("schema"), dict) else {}
    fields = schema.get("fields") if isinstance(schema.get("fields"), list) else []
    for field in fields:
        if not isinstance(field, dict) or str(field.get("id") or "") != "design_system_id":
            continue
        options = field.get("options") if isinstance(field.get("options"), list) else []
        for option in options:
            if not isinstance(option, dict):
                continue
            value = str(option.get("value") or "").strip()
            label = str(option.get("label") or "").strip()
            if not value:
                continue
            if value.casefold() in candidate_texts or label.casefold() in candidate_texts:
                return {
                    **normalized,
                    "design_system_id": value,
                }
    return normalized


def should_prompt_visual_direction(
    *,
    conversation: dict[str, Any],
    discovery_brief: dict[str, Any],
    has_reference_attachments: bool,
) -> bool:
    if _conversation_design_system_id(conversation):
        return False
    if has_reference_attachments:
        return False
    brand_context = str(discovery_brief.get("brand_context") or "").strip().lower()
    return brand_context in {"need_direction", "no_brand", "no_reference"}


def should_prompt_design_system_picker(
    *,
    conversation: dict[str, Any],
    discovery_brief: dict[str, Any],
    has_reference_attachments: bool,
) -> bool:
    if _conversation_design_system_id(conversation):
        return False
    return True


def resolve_design_system_id(
    *,
    conversation: dict[str, Any],
    discovery_brief: dict[str, Any],
    direction_answers: dict[str, Any] | None,
    has_reference_attachments: bool,
) -> str | None:
    raw_selection = str(
        (direction_answers or {}).get("design_system_id")
        or ""
    ).strip()
    del discovery_brief, has_reference_attachments
    return raw_selection or _conversation_design_system_id(conversation)


def resolve_subtemplate(
    *,
    artifact_family: str,
    skill: Any | None,
    discovery_brief: dict[str, Any],
    design_system_id: str | None,
) -> dict[str, Any]:
    family = artifact_family
    strategy = "single_surface"
    if family == "slides":
        slide_count = str(discovery_brief.get("slide_count") or "").strip().lower()
        strategy = "narrative_deck" if slide_count in {"10_15", "15_plus"} else "compact_deck"
    elif family == "document":
        doc_depth = str(discovery_brief.get("doc_depth") or "").strip().lower()
        strategy = "longform_document" if doc_depth == "deep" else "brief_document"
    elif family == "web":
        surfaces = str(discovery_brief.get("page_or_screen_count") or discovery_brief.get("scale") or "").strip().lower()
        strategy = "multi_surface_flow" if surfaces in {"2_5_surfaces", "multi_step_flow"} else "single_surface"
    return {
        "id": f"{getattr(skill, 'id', 'artifact')}::{strategy}",
        "family": family,
        "strategy": strategy,
        "design_system_id": design_system_id,
        "source": "auto",
    }


def build_plan_context(
    *,
    skill: Any | None,
    artifact_family: str,
    discovery_brief: dict[str, Any],
    design_system_id: str | None,
    resolved_subtemplate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "resolved_skill": {
            "id": getattr(skill, "id", None),
            "name": getattr(skill, "name", None),
            "artifact_family": artifact_family,
            "execution_strategy": getattr(skill, "execution_strategy", None),
            "primary_output": getattr(skill, "primary_output", None),
        },
        "discovery_brief": discovery_brief,
        "design_system_id": design_system_id,
        "resolved_subtemplate": resolved_subtemplate,
    }


def summarize_interaction_submission(kind: str, answers: dict[str, Any]) -> str:
    if kind == "design_system_picker":
        return str(answers.get("design_system_id") or "").strip() or "Design system selected"
    if kind == "visual_direction_picker":
        direction_id = str(answers.get("direction") or "").strip()
        direction = next((item for item in _DIRECTIONS if item["id"] == direction_id), None)
        return str((direction or {}).get("label") or direction_id or "Direction selected")
    output = str(answers.get("output") or "").strip()
    audience = str(answers.get("audience") or "").strip()
    if output and audience:
        return f"{output} / {audience}"
    return output or audience or "Brief submitted"


def direction_options() -> list[DirectionOption]:
    return list(_DIRECTIONS)


def _platform_options(language: str, artifact_family: str) -> list[dict[str, Any]]:
    if artifact_family == "slides":
        return [
            {"label": _t(language, "线下演讲", "Live presentation"), "value": "live_presentation"},
            {"label": _t(language, "销售提案", "Sales pitch"), "value": "sales_pitch"},
            {"label": _t(language, "内部汇报", "Internal review"), "value": "internal_review"},
        ]
    if artifact_family == "document":
        return [
            {"label": _t(language, "报告 / 提案文档", "Report / proposal"), "value": "report"},
            {"label": _t(language, "说明文档", "Explainer document"), "value": "explainer"},
            {"label": _t(language, "策略文档", "Strategy memo"), "value": "strategy_memo"},
        ]
    return [
        {"label": _t(language, "营销落地页", "Marketing site"), "value": "marketing_site"},
        {"label": _t(language, "产品页面", "Product page"), "value": "product_page"},
        {"label": _t(language, "应用原型", "App prototype"), "value": "app_prototype"},
    ]


def _tone_options(language: str) -> list[dict[str, Any]]:
    return [
        {"label": _t(language, "专业克制", "Professional / restrained"), "value": "professional_restrained"},
        {"label": _t(language, "自信现代", "Confident / modern"), "value": "confident_modern"},
        {"label": _t(language, "温暖亲和", "Warm / approachable"), "value": "warm_approachable"},
        {"label": _t(language, "高级品牌感", "Premium / brand-led"), "value": "premium_confident"},
    ]


def _scale_options(language: str, artifact_family: str) -> list[dict[str, Any]]:
    if artifact_family == "slides":
        return [
            {"label": "5-8", "value": "5_8"},
            {"label": "10-15", "value": "10_15"},
            {"label": "15+", "value": "15_plus"},
        ]
    if artifact_family == "document":
        return [
            {"label": _t(language, "1-2 页", "1-2 pages"), "value": "short"},
            {"label": _t(language, "3-6 页", "3-6 pages"), "value": "medium"},
            {"label": _t(language, "6+ 页", "6+ pages"), "value": "long"},
        ]
    return [
        {"label": _t(language, "单页/单屏", "Single surface"), "value": "single_surface"},
        {"label": _t(language, "中等范围", "Medium scope"), "value": "medium_scope"},
        {"label": _t(language, "完整流程", "Full flow"), "value": "full_flow"},
    ]

