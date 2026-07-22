from __future__ import annotations

from typing import Any

from app.models.project import Project
from app.services.canvas_media_rehost_service import CanvasMediaRehostService
from app.services.project_canvas_service import ProjectCanvasService


async def load_canvas_items(
    db,
    *,
    project: Project,
    user_id: int,
) -> list[dict[str, Any]]:
    payload = await ProjectCanvasService(db).get_effective_canvas_payload(project, user_id)
    payload = await CanvasMediaRehostService(db).rehost_canvas_payload(
        payload,
        target_project_id=project.id,
        user_id=user_id,
    )
    return [
        item
        for item in payload
        if isinstance(item, dict) and item.get("id") != "global_state"
    ]
