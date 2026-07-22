from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


CANVAS_ASSET_MEDIA_TYPES = {"image", "video"}


@dataclass(frozen=True)
class CanvasAssetGroup:
    group_id: str
    group_name: str | None


@dataclass(frozen=True)
class CanvasAssetGroupAsset:
    canvas_item_id: str | None
    asset_type: str


@dataclass
class CanvasAssetGroupSummary:
    group_id: str | None
    group_name: str | None
    asset_count: int = 0
    image_count: int = 0
    video_count: int = 0
    is_ungrouped: bool = False

    def add_asset(self, asset_type: str) -> None:
        self.asset_count += 1
        if asset_type == "image":
            self.image_count += 1
        elif asset_type == "video":
            self.video_count += 1


class CanvasAssetGroupIndex:
    def __init__(
        self,
        *,
        group_names: dict[str, str | None],
        group_order: list[str],
        item_group_ids: dict[str, str],
    ) -> None:
        self.group_names = group_names
        self.group_order = group_order
        self.item_group_ids = item_group_ids
        self.grouped_item_ids = set(item_group_ids)

    @classmethod
    def from_canvas_payload(cls, canvas_payload: Any) -> "CanvasAssetGroupIndex":
        if not isinstance(canvas_payload, list):
            return cls(group_names={}, group_order=[], item_group_ids={})

        group_names: dict[str, str | None] = {}
        group_order: list[str] = []
        for item in canvas_payload:
            if not isinstance(item, dict) or item.get("type") != "group":
                continue
            group_id = _coerce_id(item.get("id"))
            if not group_id or group_id in group_names:
                continue
            group_names[group_id] = _coerce_name(item.get("name"))
            group_order.append(group_id)

        item_group_ids: dict[str, str] = {}
        for item in canvas_payload:
            if not isinstance(item, dict) or item.get("type") not in CANVAS_ASSET_MEDIA_TYPES:
                continue
            item_id = _coerce_id(item.get("id"))
            group_id = _coerce_id(item.get("groupId"))
            if not item_id or not group_id or group_id not in group_names:
                continue
            item_group_ids[item_id] = group_id

        return cls(
            group_names=group_names,
            group_order=group_order,
            item_group_ids=item_group_ids,
        )

    def item_ids_for_group(self, group_id: str) -> set[str]:
        return {
            item_id
            for item_id, item_group_id in self.item_group_ids.items()
            if item_group_id == group_id
        }

    def group_for_canvas_item(self, canvas_item_id: str | None) -> CanvasAssetGroup | None:
        item_id = _coerce_id(canvas_item_id)
        if not item_id:
            return None
        group_id = self.item_group_ids.get(item_id)
        if not group_id:
            return None
        return CanvasAssetGroup(group_id=group_id, group_name=self.group_names.get(group_id))

    def summarize_assets(self, assets: Iterable[CanvasAssetGroupAsset]) -> list[CanvasAssetGroupSummary]:
        grouped_summaries = {
            group_id: CanvasAssetGroupSummary(
                group_id=group_id,
                group_name=self.group_names.get(group_id),
            )
            for group_id in self.group_order
        }
        ungrouped_summary = CanvasAssetGroupSummary(
            group_id=None,
            group_name=None,
            is_ungrouped=True,
        )

        for asset in assets:
            group = self.group_for_canvas_item(asset.canvas_item_id)
            if group:
                grouped_summaries.setdefault(
                    group.group_id,
                    CanvasAssetGroupSummary(
                        group_id=group.group_id,
                        group_name=group.group_name,
                    ),
                ).add_asset(asset.asset_type)
                continue

            ungrouped_summary.add_asset(asset.asset_type)

        summaries = [
            grouped_summaries[group_id]
            for group_id in self.group_order
            if grouped_summaries[group_id].asset_count > 0
        ]
        if ungrouped_summary.asset_count > 0:
            summaries.append(ungrouped_summary)
        return summaries


def _coerce_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
