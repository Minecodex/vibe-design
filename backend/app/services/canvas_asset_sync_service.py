from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.services.canvas_media_rehost_service import CanvasMediaRehostService
from app.services.project_canvas_service import ProjectCanvasService


CANVAS_MEDIA_TYPES = {"image", "video"}
ASSET_ORIGIN_KINDS = {"ai_generated", "local_upload", "legacy"}


class CanvasAssetSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.canvas_service = ProjectCanvasService(db)

    async def sync_user_canvas_assets(
        self,
        project: Project,
        canvas_owner_user_id: int,
        canvas_payload: Any,
        actor_user_id: int,
    ) -> None:
        del actor_user_id

        normalized_payload = await CanvasMediaRehostService(self.db).rehost_canvas_payload(
            canvas_payload,
            target_project_id=project.id,
            user_id=canvas_owner_user_id,
        )
        canvas_items = self._extract_canvas_media_items(normalized_payload)
        canvas_item_ids = set(canvas_items)

        result = await self.db.execute(
            select(ProjectAsset).where(
                ProjectAsset.project_id == project.id,
                ProjectAsset.user_id == canvas_owner_user_id,
            )
        )
        existing_assets = list(result.scalars().all())
        existing_by_canvas_item_id = {
            asset.canvas_item_id: asset
            for asset in existing_assets
            if asset.canvas_item_id
        }

        for canvas_item_id, item in canvas_items.items():
            asset = existing_by_canvas_item_id.get(canvas_item_id)
            origin_kind = self._normalize_origin(
                item.get("asset_origin"),
                existing_origin=asset.origin_kind if asset is not None else None,
            )
            source_asset_id = self._normalize_source_asset_id(item.get("source_asset_id"))
            asset_type = item["type"]
            url = item["url"]

            if asset is None:
                self.db.add(
                    ProjectAsset(
                        project_id=project.id,
                        user_id=canvas_owner_user_id,
                        asset_type=asset_type,
                        url=url,
                        canvas_item_id=canvas_item_id,
                        origin_kind=origin_kind,
                        source_asset_id=source_asset_id,
                    )
                )
                continue

            asset.asset_type = asset_type
            asset.url = url
            asset.origin_kind = origin_kind
            asset.source_asset_id = source_asset_id

        for asset in existing_assets:
            if asset.canvas_item_id and asset.canvas_item_id not in canvas_item_ids:
                await self.db.delete(asset)

        await self.db.flush()

    async def remove_canvas_items_for_assets(self, assets: list[ProjectAsset]) -> None:
        project_asset_ids: dict[tuple[int, int], list[str]] = defaultdict(list)

        for asset in assets:
            if asset.canvas_item_id:
                project_asset_ids[(asset.project_id, asset.user_id)].append(asset.canvas_item_id)

        if not project_asset_ids:
            return

        project_ids = sorted({project_id for project_id, _ in project_asset_ids.keys()})
        result = await self.db.execute(
            select(Project).where(Project.id.in_(project_ids)).order_by(Project.id).with_for_update()
        )
        project_map = {project.id: project for project in result.scalars().all()}

        for (project_id, user_id), canvas_item_id_list in project_asset_ids.items():
            project = project_map.get(project_id)
            if not project:
                continue

            def remove_items(
                canvas_items: list[dict[str, Any]],
                canvas_meta: dict[str, Any] | None,
            ) -> tuple[list[dict[str, Any]], dict[str, Any] | None] | None:
                next_canvas_items = self._remove_canvas_items(
                    canvas_items,
                    set(canvas_item_id_list),
                )
                if next_canvas_items == canvas_items:
                    return None
                return next_canvas_items, canvas_meta

            await self.canvas_service.mutate_user_canvas(
                project,
                user_id,
                remove_items,
                create_if_missing=False,
            )

        await self.db.flush()

    def _extract_canvas_media_items(self, canvas_data: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(canvas_data, list):
            return {}

        media_items: dict[str, dict[str, Any]] = {}
        for item in canvas_data:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not item_id or item.get("type") not in CANVAS_MEDIA_TYPES or not item.get("url"):
                continue
            media_items[str(item_id)] = item
        return media_items

    def _normalize_origin(self, value: Any, *, existing_origin: str | None = None) -> str:
        if isinstance(value, str) and value in ASSET_ORIGIN_KINDS:
            return value
        if existing_origin in ASSET_ORIGIN_KINDS:
            return existing_origin
        return "legacy"

    def _normalize_source_asset_id(self, value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _remove_canvas_items(self, canvas_data: Any, canvas_item_ids: set[str]) -> list[dict[str, Any]]:
        if not isinstance(canvas_data, list):
            return []

        remaining_items = [
            item
            for item in canvas_data
            if not (isinstance(item, dict) and str(item.get("id")) in canvas_item_ids)
        ]
        return self._remove_empty_groups(remaining_items)

    def _remove_empty_groups(self, canvas_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current_items = list(canvas_data)

        while True:
            group_ids = {
                str(item.get("id"))
                for item in current_items
                if isinstance(item, dict) and item.get("type") == "group" and item.get("id") is not None
            }
            if not group_ids:
                return current_items

            non_empty_group_ids = {
                str(item.get("groupId"))
                for item in current_items
                if isinstance(item, dict) and item.get("groupId") is not None
            }
            empty_group_ids = group_ids - non_empty_group_ids
            if not empty_group_ids:
                return current_items

            current_items = [
                item
                for item in current_items
                if not (isinstance(item, dict) and item.get("type") == "group" and str(item.get("id")) in empty_group_ids)
            ]
