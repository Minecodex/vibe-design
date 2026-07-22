from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.services.local_media_dimensions import read_local_image_dimensions
from app.services.project_canvas_service import ProjectCanvasService


AGENT_MEDIA_TYPES = {"image", "video", "image_generator", "video_generator"}
AGENT_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
AGENT_GROUP_COLUMNS = 10
AGENT_GROUP_GAP = 20
AGENT_GROUP_PADDING = 80
DEFAULT_AGENT_ITEM_WIDTH = 500
DEFAULT_AGENT_ITEM_HEIGHT = 500
VERIFIED_INTRINSIC_SIZE_KEY = "_verified_intrinsic_size"


@dataclass
class AgentCanvasUpsertResult:
    canvas_revision: int
    canvas_item: dict[str, Any] | None


class CanvasAgentItemService:
    """Persist agent generated media as local canvas item patches."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.canvas_service = ProjectCanvasService(db)

    async def upsert_agent_generation_item(
        self,
        project: Project,
        user_id: int,
        canvas_item: dict[str, Any] | None,
        status: str,
        *,
        result_url: str | None = None,
        deleted_keys: list[str] | None = None,
        workspace_root: Path | None = None,
    ) -> AgentCanvasUpsertResult:
        if not isinstance(canvas_item, dict):
            return AgentCanvasUpsertResult(
                canvas_revision=await self.canvas_service.get_canvas_revision(project, user_id),
                canvas_item=None,
            )

        incoming = self._normalize_incoming_item(canvas_item, status, result_url=result_url)
        incoming = self._apply_completed_intrinsic_size(
            incoming,
            status,
            workspace_root=workspace_root,
        )
        incoming_key = _first_text(incoming.get("agent_media_key"), incoming.get("artifact_ref"), incoming.get("task_id"), incoming.get("id"))
        if not incoming_key or _has_deleted_agent_media_key(deleted_keys, incoming_key):
            return AgentCanvasUpsertResult(
                canvas_revision=await self.canvas_service.get_canvas_revision(project, user_id),
                canvas_item=None,
            )

        final_item: dict[str, Any] | None = None

        def mutate(
            canvas_items: list[dict[str, Any]],
            canvas_meta: dict[str, Any] | None,
        ) -> tuple[list[dict[str, Any]], dict[str, Any] | None] | None:
            nonlocal final_item
            meta_deleted_keys = (
                canvas_meta.get("deletedAgentMediaKeys")
                if isinstance(canvas_meta, dict)
                else None
            )
            if _has_deleted_agent_media_key(meta_deleted_keys, incoming_key):
                final_item = None
                return None

            next_items = [dict(item) for item in canvas_items]
            existing_index = _find_existing_agent_item_index(next_items, incoming)
            is_terminal = _normalize_status(status) in AGENT_TERMINAL_STATUSES

            if existing_index >= 0:
                existing = next_items[existing_index]
                next_item = self._merge_existing_item(existing, incoming, terminal=is_terminal)
                next_items[existing_index] = next_item
                final_item = dict(next_item)
                if next_item.get("groupId"):
                    next_items = _layout_agent_group(next_items, str(next_item["groupId"]))
                    final_item = _find_item_by_id(next_items, next_item.get("id")) or final_item
                return (next_items, canvas_meta) if next_items != canvas_items else None

            if is_terminal and _has_deleted_agent_media_key(meta_deleted_keys, incoming_key):
                final_item = None
                return None

            new_item = self._build_new_item(next_items, incoming)
            next_items = _insert_with_agent_group(next_items, new_item)
            final_item = dict(new_item)
            if new_item.get("groupId"):
                next_items = _layout_agent_group(next_items, str(new_item["groupId"]))
                final_item = _find_item_by_id(next_items, new_item.get("id")) or final_item
            return (next_items, canvas_meta) if next_items != canvas_items else None

        canvas = await self.canvas_service.mutate_user_canvas(
            project,
            user_id,
            mutate,
            create_if_missing=True,
        )
        await self._sync_completed_project_asset(project, user_id, final_item)
        return AgentCanvasUpsertResult(
            canvas_revision=int(canvas.canvas_revision or 0) if canvas else 0,
            canvas_item=final_item,
        )

    def _normalize_incoming_item(
        self,
        canvas_item: dict[str, Any],
        status: str,
        *,
        result_url: str | None,
    ) -> dict[str, Any]:
        incoming = dict(canvas_item)
        normalized_status = _normalize_canvas_status(status or incoming.get("status"))
        incoming["status"] = normalized_status
        if result_url:
            incoming["url"] = result_url
        kind = _infer_kind(incoming)
        if normalized_status == "completed":
            incoming["type"] = "video" if kind == "video" else "image"
        elif incoming.get("type") not in AGENT_MEDIA_TYPES:
            incoming["type"] = "video_generator" if kind == "video" else "image_generator"
        incoming_key = _first_text(
            incoming.get("agent_media_key"),
            incoming.get("agentMediaKey"),
            incoming.get("artifact_ref"),
            incoming.get("task_id"),
            incoming.get("id"),
        )
        if incoming_key:
            incoming["agent_media_key"] = incoming_key
        if not _text(incoming.get("id")):
            incoming["id"] = _stable_canvas_item_id(incoming_key)
        if incoming.get("artifact_ref") is not None:
            incoming["artifact_ref"] = _text(incoming.get("artifact_ref")) or None
        if incoming.get("task_id") is not None:
            incoming["task_id"] = _text(incoming.get("task_id")) or incoming.get("task_id")
        if incoming.get("agent_group_key") is not None:
            incoming["agent_group_key"] = _text(incoming.get("agent_group_key")) or None
        if incoming.get("agent_conversation_id") is None and incoming.get("conversationId") is not None:
            incoming["agent_conversation_id"] = incoming.get("conversationId")
        return incoming

    def _apply_completed_intrinsic_size(
        self,
        incoming: dict[str, Any],
        status: str,
        *,
        workspace_root: Path | None,
    ) -> dict[str, Any]:
        if _normalize_status(status) != "completed":
            return incoming
        if _infer_kind(incoming) != "image":
            return incoming
        if incoming.get("media_display_size_source") == "user":
            return incoming

        dimensions = read_local_image_dimensions(
            incoming.get("url"),
            workspace_root=workspace_root,
        )
        if dimensions is None:
            return incoming

        width, height = dimensions
        next_item = dict(incoming)
        next_item["width"] = width
        next_item["height"] = height
        next_item["media_display_size_source"] = "intrinsic"
        next_item[VERIFIED_INTRINSIC_SIZE_KEY] = True
        return next_item

    def _merge_existing_item(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
        *,
        terminal: bool,
    ) -> dict[str, Any]:
        next_item = dict(existing)
        agent_fields = (
            "type",
            "url",
            "status",
            "artifact_ref",
            "task_id",
            "progress",
            "model_name",
            "model_label",
            "provider_code",
            "aspect_ratio",
            "resolution",
            "duration",
            "error_message",
            "failure_kind",
            "prompt",
            "agent_conversation_id",
            "agent_message_id",
            "agent_media_key",
            "agent_group_key",
            "asset_origin",
            "suppressCompletionToast",
        )
        for field in agent_fields:
            if field in incoming and incoming[field] is not None:
                next_item[field] = incoming[field]
        if _should_apply_incoming_media_size(existing, incoming):
            next_item["width"] = incoming["width"]
            next_item["height"] = incoming["height"]
            next_item["media_display_size_source"] = incoming.get("media_display_size_source") or "intrinsic"
        if "agent_media_key" not in next_item or not next_item.get("agent_media_key"):
            next_item["agent_media_key"] = _first_text(incoming.get("agent_media_key"), incoming.get("artifact_ref"), incoming.get("task_id"), incoming.get("id"))
        if not terminal:
            next_item.setdefault("media_display_size_source", existing.get("media_display_size_source") or "placeholder")
        next_item.setdefault("asset_origin", "ai_generated")
        next_item["suppressCompletionToast"] = incoming.get("suppressCompletionToast", existing.get("suppressCompletionToast", True))
        next_item.pop(VERIFIED_INTRINSIC_SIZE_KEY, None)
        return next_item

    def _build_new_item(
        self,
        items: list[dict[str, Any]],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        width = _number(incoming.get("width"), DEFAULT_AGENT_ITEM_WIDTH)
        height = _number(incoming.get("height"), DEFAULT_AGENT_ITEM_HEIGHT)
        x = _number(incoming.get("x"), 0)
        y = _number(incoming.get("y"), 0)
        if x == 0 and y == 0:
            x, y = _find_empty_position(items, width, height)

        final_item = {
            **incoming,
            "id": _text(incoming.get("id")) or _stable_canvas_item_id(_text(incoming.get("agent_media_key"))),
            "url": incoming.get("url") or "",
            "name": incoming.get("name") or incoming.get("_agentLabel") or "agent",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "z_index": incoming.get("z_index") or _next_z_index(items),
            "asset_origin": incoming.get("asset_origin") or "ai_generated",
            "media_display_size_source": _initial_media_display_size_source(incoming),
            "suppressCompletionToast": incoming.get("suppressCompletionToast", True),
        }
        final_item.pop(VERIFIED_INTRINSIC_SIZE_KEY, None)
        return final_item

    async def _sync_completed_project_asset(
        self,
        project: Project,
        user_id: int,
        item: dict[str, Any] | None,
    ) -> None:
        if not item or item.get("type") not in {"image", "video"} or not item.get("url"):
            return
        result = await self.db.execute(
            select(ProjectAsset).where(
                ProjectAsset.project_id == project.id,
                ProjectAsset.user_id == user_id,
                ProjectAsset.canvas_item_id == item.get("id"),
            )
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            self.db.add(
                ProjectAsset(
                    project_id=project.id,
                    user_id=user_id,
                    asset_type=item["type"],
                    url=item["url"],
                    canvas_item_id=item["id"],
                    origin_kind="ai_generated",
                    source_asset_id=_optional_int(item.get("source_asset_id")),
                )
            )
            await self.db.flush()
            return
        asset.asset_type = item["type"]
        asset.url = item["url"]
        asset.origin_kind = "ai_generated"
        asset.source_asset_id = _optional_int(item.get("source_asset_id"))
        await self.db.flush()


def _insert_with_agent_group(items: list[dict[str, Any]], new_item: dict[str, Any]) -> list[dict[str, Any]]:
    group_key = _text(new_item.get("agent_group_key"))
    session_items = _agent_session_items(items, new_item, group_key=group_key)
    order = _next_agent_group_order(session_items)
    new_item["agent_group_order"] = new_item.get("agent_group_order") if isinstance(new_item.get("agent_group_order"), int) else order

    group_id = _resolve_agent_group_id(items, session_items, group_key=group_key)
    should_group = bool(group_id) or (len(session_items) + 1 >= 2)
    if not should_group:
        return [*items, new_item]

    if not group_id:
        group_id = f"group-{uuid.uuid4().hex[:12]}"
        group = _build_agent_group(group_id, new_item, session_items)
        items = [*items, group]

    new_item["groupId"] = group_id
    next_items = []
    for item in items:
        if _belongs_to_agent_session(item, new_item, group_key=group_key) and item.get("type") != "group":
            next = dict(item)
            next["groupId"] = group_id
            next.setdefault("agent_group_key", group_key or new_item.get("agent_group_key"))
            next_items.append(next)
        else:
            next_items.append(item)
    return [*next_items, new_item]


def _layout_agent_group(items: list[dict[str, Any]], group_id: str) -> list[dict[str, Any]]:
    group = next((item for item in items if item.get("id") == group_id and item.get("type") == "group"), None)
    if not group or group.get("group_layout_mode") == "manual":
        return items

    members = [
        item
        for item in items
        if item.get("groupId") == group_id and item.get("type") != "group"
    ]
    if not members:
        return items
    members = sorted(members, key=lambda item: (_number(item.get("agent_group_order"), 0), _text(item.get("id"))))
    x = _number(group.get("x"), 0) + AGENT_GROUP_PADDING
    y = _number(group.get("y"), 0) + AGENT_GROUP_PADDING
    col_widths: dict[int, float] = {}
    row_heights: dict[int, float] = {}
    for index, member in enumerate(members):
        col = index % AGENT_GROUP_COLUMNS
        row = index // AGENT_GROUP_COLUMNS
        col_widths[col] = max(col_widths.get(col, 0), _number(member.get("width"), DEFAULT_AGENT_ITEM_WIDTH))
        row_heights[row] = max(row_heights.get(row, 0), _number(member.get("height"), DEFAULT_AGENT_ITEM_HEIGHT))

    col_offsets: dict[int, float] = {}
    running_x = x
    for col in range(max(col_widths.keys(), default=-1) + 1):
        col_offsets[col] = running_x
        running_x += col_widths.get(col, DEFAULT_AGENT_ITEM_WIDTH) + AGENT_GROUP_GAP

    row_offsets: dict[int, float] = {}
    running_y = y
    for row in range(max(row_heights.keys(), default=-1) + 1):
        row_offsets[row] = running_y
        running_y += row_heights.get(row, DEFAULT_AGENT_ITEM_HEIGHT) + AGENT_GROUP_GAP

    positions: dict[str, tuple[float, float]] = {}
    for index, member in enumerate(members):
        positions[_text(member.get("id"))] = (
            col_offsets[index % AGENT_GROUP_COLUMNS],
            row_offsets[index // AGENT_GROUP_COLUMNS],
        )

    group_width = (
        sum(col_widths.values())
        + AGENT_GROUP_GAP * max(len(col_widths) - 1, 0)
        + AGENT_GROUP_PADDING * 2
    )
    group_height = (
        sum(row_heights.values())
        + AGENT_GROUP_GAP * max(len(row_heights) - 1, 0)
        + AGENT_GROUP_PADDING * 2
    )

    next_items: list[dict[str, Any]] = []
    for item in items:
        item_id = _text(item.get("id"))
        if item is group:
            next_group = dict(item)
            next_group["width"] = group_width
            next_group["height"] = group_height
            next_items.append(next_group)
        elif item_id in positions:
            next_member = dict(item)
            next_member["x"], next_member["y"] = positions[item_id]
            next_items.append(next_member)
        else:
            next_items.append(item)
    return next_items


def _agent_session_items(items: list[dict[str, Any]], incoming: dict[str, Any], *, group_key: str) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if _belongs_to_agent_session(item, incoming, group_key=group_key)
        and item.get("type") != "group"
    ]


def _belongs_to_agent_session(item: dict[str, Any], incoming: dict[str, Any], *, group_key: str) -> bool:
    if item.get("type") not in AGENT_MEDIA_TYPES:
        return False
    if group_key:
        return _text(item.get("agent_group_key")) == group_key
    if _text(item.get("agent_group_key")):
        return False
    incoming_conv = _text(incoming.get("agent_conversation_id") or incoming.get("conversationId"))
    item_conv = _text(item.get("agent_conversation_id") or item.get("conversationId"))
    incoming_message = _text(incoming.get("agent_message_id") or incoming.get("messageId"))
    item_message = _text(item.get("agent_message_id") or item.get("messageId"))
    if incoming_message or item_message:
        return incoming_conv == item_conv and incoming_message == item_message
    return bool(incoming_conv and incoming_conv == item_conv)


def _resolve_agent_group_id(items: list[dict[str, Any]], session_items: list[dict[str, Any]], *, group_key: str) -> str | None:
    if group_key:
        for group in items:
            if group.get("type") == "group" and group.get("group_layout_mode") in {"agent_grid", "manual"}:
                members = [item for item in items if item.get("groupId") == group.get("id")]
                if any(_text(member.get("agent_group_key")) == group_key for member in members):
                    return _text(group.get("id")) or None
    for item in session_items:
        group_id = _text(item.get("groupId"))
        if group_id:
            return group_id
    return None


def _build_agent_group(group_id: str, incoming: dict[str, Any], session_items: list[dict[str, Any]]) -> dict[str, Any]:
    anchor = session_items[0] if session_items else incoming
    width = _number(anchor.get("width"), DEFAULT_AGENT_ITEM_WIDTH)
    height = _number(anchor.get("height"), DEFAULT_AGENT_ITEM_HEIGHT)
    return {
        "id": group_id,
        "type": "group",
        "url": "",
        "name": incoming.get("name") or incoming.get("_agentLabel") or "agent",
        "x": _number(anchor.get("x"), 0) - AGENT_GROUP_PADDING,
        "y": _number(anchor.get("y"), 0) - AGENT_GROUP_PADDING,
        "width": width + AGENT_GROUP_PADDING * 2,
        "height": height + AGENT_GROUP_PADDING * 2,
        "z_index": -999,
        "background_color": "rgba(22, 119, 255, 0.2)",
        "group_layout_mode": "agent_grid",
        "agent_message_id": incoming.get("agent_message_id") or incoming.get("messageId"),
        "agent_conversation_id": incoming.get("agent_conversation_id") or incoming.get("conversationId"),
    }


def _find_existing_agent_item_index(items: list[dict[str, Any]], incoming: dict[str, Any]) -> int:
    matchers = [
        ("agent_media_key", _text(incoming.get("agent_media_key") or incoming.get("agentMediaKey"))),
        ("artifact_ref", _text(incoming.get("artifact_ref"))),
        ("task_id", _text(incoming.get("task_id"))),
        ("id", _text(incoming.get("id"))),
    ]
    for field, value in matchers:
        if not value:
            continue
        for index, item in enumerate(items):
            if _text(item.get(field)) == value:
                return index
    return -1


def _find_item_by_id(items: list[dict[str, Any]], item_id: Any) -> dict[str, Any] | None:
    normalized_id = _text(item_id)
    if not normalized_id:
        return None
    for item in items:
        if _text(item.get("id")) == normalized_id:
            return dict(item)
    return None


def _next_agent_group_order(items: list[dict[str, Any]]) -> int:
    orders = [
        int(item.get("agent_group_order"))
        for item in items
        if isinstance(item.get("agent_group_order"), int)
    ]
    return max(orders, default=-1) + 1


def _find_empty_position(items: list[dict[str, Any]], width: float, height: float) -> tuple[float, float]:
    x = 0
    y = 0
    for _ in range(200):
        if not _collides(items, x, y, width, height):
            return x, y
        x += width + AGENT_GROUP_GAP
        if x > 5000:
            x = 0
            y += height + AGENT_GROUP_GAP
    return x, y


def _collides(items: list[dict[str, Any]], x: float, y: float, width: float, height: float) -> bool:
    for item in items:
        if item.get("type") == "group":
            continue
        ix = _number(item.get("x"), 0)
        iy = _number(item.get("y"), 0)
        iw = _number(item.get("width"), DEFAULT_AGENT_ITEM_WIDTH)
        ih = _number(item.get("height"), DEFAULT_AGENT_ITEM_HEIGHT)
        if x < ix + iw + AGENT_GROUP_GAP and x + width + AGENT_GROUP_GAP > ix and y < iy + ih + AGENT_GROUP_GAP and y + height + AGENT_GROUP_GAP > iy:
            return True
    return False


def _next_z_index(items: list[dict[str, Any]]) -> int:
    values = [_number(item.get("z_index"), 0) for item in items]
    return int(max(values, default=0) + 1)


def _infer_kind(item: dict[str, Any]) -> str:
    raw_type = _text(item.get("type")).lower()
    if raw_type in {"video", "video_generator"}:
        return "video"
    duration = item.get("duration")
    return "video" if duration not in {None, "", 0} else "image"


def _normalize_status(value: Any) -> str:
    raw = _text(value).lower()
    if raw in {"running", "processing", "pending", "generating"}:
        return "generating"
    return raw or "generating"


def _normalize_canvas_status(value: Any) -> str:
    raw = _normalize_status(value)
    if raw in {"completed", "failed", "cancelled"}:
        return raw
    return "generating"


def _has_deleted_agent_media_key(keys: Any, key: str) -> bool:
    normalized_key = _text(key)
    if not normalized_key or not isinstance(keys, list):
        return False
    return normalized_key in {_text(item) for item in keys}


def _should_apply_incoming_media_size(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    if existing.get("media_display_size_source") == "user":
        return False
    if incoming.get(VERIFIED_INTRINSIC_SIZE_KEY) is not True:
        return False
    if incoming.get("media_display_size_source") != "intrinsic":
        return False
    return _number(incoming.get("width"), 0) > 0 and _number(incoming.get("height"), 0) > 0


def _initial_media_display_size_source(incoming: dict[str, Any]) -> str:
    source = _text(incoming.get("media_display_size_source"))
    if source == "user":
        return "user"
    if source == "intrinsic" and incoming.get(VERIFIED_INTRINSIC_SIZE_KEY) is True:
        return "intrinsic"
    return "placeholder"


def _stable_canvas_item_id(agent_media_key: str) -> str:
    normalized = _text(agent_media_key)
    if not normalized:
        return f"agent-generated-{uuid.uuid4().hex}"
    stable = (
        normalized
        .replace("artifact_ref:", "")
        .replace(":", "-")
        .replace("/", "-")
        .replace("\\", "-")
    )
    stable = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in stable).strip("-")
    return f"agent-generated-{stable or uuid.uuid4().hex}"


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
