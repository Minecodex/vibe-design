from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.runtime.context_recall.search import search_harness_history as _search_harness_history

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class SearchHarnessHistoryInput(BaseModel):
    query: str = Field(..., min_length=1)
    sources: list[Literal["conversation", "tool_results", "compactions", "collapse_commits"]] | None = Field(default=None)
    limit: int = Field(default=8, ge=1, le=20)
    before_seq: int | None = Field(default=None, ge=0)


class SearchHarnessHistoryTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_harness_history"

    @property
    def description(self) -> str:
        return "Search past harness conversation messages, compaction boundaries, collapse commits, and tool results within the current conversation."

    @property
    def input_model(self) -> type[BaseModel]:
        return SearchHarnessHistoryInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    async def execute(self, params: SearchHarnessHistoryInput, ctx: "HarnessContext") -> ToolResult:
        payload = _search_harness_history(
            ctx.user_id,
            ctx.conversation_id,
            query=params.query,
            sources=params.sources,
            limit=params.limit,
            before_seq=params.before_seq,
            meta_dir=ctx.meta_dir,
        )
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=payload)
