"""Web search tool for the Harness agent."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.services.search_runtime import format_search_result_message, search_web
from app.services.web_search_payloads import build_web_search_payloads

from ._internal.base import BaseTool, ToolResult
from app.services.agent_harness.core.utils.media_download import download_media_to_workspace

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

logger = logging.getLogger(__name__)


async def _cache_image_results(ctx: "HarnessContext", results: list[dict]) -> list[dict]:
    cached_results: list[dict] = []
    for item in results:
        normalized_item = dict(item)
        network_image_url = str(
            normalized_item.get("image_url")
            or normalized_item.get("thumbnail_url")
            or ""
        ).strip()
        if network_image_url:
            normalized_item["network_image_url"] = network_image_url
            try:
                normalized_item["local_image_path"] = await download_media_to_workspace(
                    ctx,
                    network_image_url,
                    ext_hint="jpg",
                    media_kind="web_search_image",
                )
            except Exception:
                logger.warning(
                    "Failed to cache web search image: %s",
                    network_image_url,
                    exc_info=True,
                )
                continue
        if result_is_image_reference(normalized_item):
            cached_results.append(normalized_item)
            continue
        if not network_image_url:
            cached_results.append(normalized_item)
    return cached_results


def result_is_image_reference(item: dict) -> bool:
    return bool(str(item.get("local_image_path") or "").strip())


class WebSearchParams(BaseModel):
    query: str = Field(..., description="搜索关键词")
    num_results: int = Field(3, description="返回结果数量（默认 3，最多 5）", ge=1, le=5)
    search_type: str = Field(
        "text",
        description=(
            "搜索类型：text 表示网页/文本搜索，适合新闻、事实、网页资料；"
            "image 表示图片搜索，适合画像、照片、海报、封面、商品图、截图和视觉参考图。"
        ),
    )


class WebSearchTool(BaseTool):
    """搜索网络获取实时信息。"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "统一的联网搜索工具，可执行网页/文本搜索或图片搜索。"
            "查看近期事件、查找具体事实、网页资料时优先使用 text；"
            "检索人物画像、照片、海报、封面、商品图、截图、视觉参考图时优先使用 image。"
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return WebSearchParams

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    async def execute(self, params: WebSearchParams, ctx: "HarnessContext") -> ToolResult:
        query = params.query
        num_results = min(params.num_results, 10)
        search_type = params.search_type

        logger.info("Harness agent searching web for: %s", query)
        result = await search_web(query, num_results=num_results, search_type=search_type)
        normalized_results = result["results"]
        if result["search_type"] == "image":
            normalized_results = await _cache_image_results(ctx, result["results"])

        message = format_search_result_message(
            search_type=result["search_type"],
            query=result["query"],
            result_count=len(normalized_results),
        )

        result_data, ui_result_data = build_web_search_payloads(
            provider=result["provider"],
            search_type=result["search_type"],
            query=result["query"],
            results=normalized_results,
            message=message,
        )

        return ToolResult(
            output=json.dumps(result_data, ensure_ascii=False),
            metadata=ui_result_data,
        )
