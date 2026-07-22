"""E-commerce option-card tool for the menswear-ecommerce-hero skill."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ._internal.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

ECOMMERCE_GENERATION_OPTIONS_KIND = "ecommerce_generation_options"


class PrepareEcommerceGenerationParams(BaseModel):
    """No-argument tool params.

    The tool only asks the frontend to render an options card. Product context is
    supplied by the conversation and by the user's card submission.
    """


def _json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _stable_request_id(ctx: "HarnessContext") -> str:
    digest_payload = {
        "conversation_id": str(ctx.conversation_id),
        "run_id": str(ctx.run_id),
        "kind": ECOMMERCE_GENERATION_OPTIONS_KIND,
    }
    digest = sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"ecommerce-options:{ctx.conversation_id}:{ctx.run_id}:{digest}"


def _interaction_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "interaction",
        "interaction": payload,
    }


class PrepareEcommerceGenerationTool(BaseTool):
    @property
    def name(self) -> str:
        return "prepare_ecommerce_generation"

    @property
    def description(self) -> str:
        return (
            "Show the menswear ecommerce product-image options card. This tool takes no parameters, "
            "does not draft prompts, and does not generate images. After the user confirms the card, "
            "the system sends a model-visible context message so the model can decide how to call generate_image."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return PrepareEcommerceGenerationParams

    async def execute(self, params: PrepareEcommerceGenerationParams, ctx: "HarnessContext") -> ToolResult:
        request_id = _stable_request_id(ctx)
        payload = {
            "kind": ECOMMERCE_GENERATION_OPTIONS_KIND,
            "request_id": request_id,
            "requestId": request_id,
            "tool_call_id": request_id,
            "toolCallId": request_id,
            "question": "请选择商品图生成选项",
            "content": "请选择参考图库分类、图片风格、可选参考图和生成数量。",
            "schema": {
                "title": "商品图生成配置",
                "submit_label": "提交",
                "cancel_label": "取消",
            },
            "defaults": {
                "enable_background_reference": False,
                "enable_model_reference": False,
                "enable_other_main_image_reference": False,
                "generation_count": 4,
                "generation_count_min": 1,
                "generation_count_max": 6,
            },
            "status": "pending",
        }
        return ToolResult(
            output=_json_output(
                {
                    "message": "请用户确认商品图生成配置。",
                    "kind": ECOMMERCE_GENERATION_OPTIONS_KIND,
                    "request_id": request_id,
                }
            ),
            metadata=_interaction_metadata(payload),
        )
