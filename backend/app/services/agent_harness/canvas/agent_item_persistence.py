from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.project_repository import ProjectRepository
from app.services.agent_harness.runtime.execution_support.billing import get_harness_db_session_factory
from app.services.canvas_agent_item_service import AgentCanvasUpsertResult, CanvasAgentItemService

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


async def persist_agent_canvas_item(
    ctx: "HarnessContext",
    canvas_item: dict | None,
    status: str,
    *,
    result_url: str | None = None,
) -> dict | None:
    result = await persist_agent_canvas_item_patch(
        ctx,
        canvas_item,
        status,
        result_url=result_url,
    )
    return result.canvas_item if result else canvas_item


async def persist_agent_canvas_item_patch(
    ctx: "HarnessContext",
    canvas_item: dict | None,
    status: str,
    *,
    result_url: str | None = None,
) -> AgentCanvasUpsertResult | None:
    if ctx.runtime_profile != "canvas" or ctx.project_id is None or not isinstance(canvas_item, dict):
        return None

    session_factory = get_harness_db_session_factory()
    async with session_factory() as db:
        project = await ProjectRepository(db).get_by_id_and_user(int(ctx.project_id), int(ctx.user_id))
        if project is None:
            return None
        result = await CanvasAgentItemService(db).upsert_agent_generation_item(
            project,
            int(ctx.user_id),
            canvas_item,
            status,
            result_url=result_url,
            workspace_root=ctx.conversation_dir,
        )
        await db.commit()
        return result
