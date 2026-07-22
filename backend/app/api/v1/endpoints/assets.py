import asyncio
from datetime import datetime
from typing import List, Optional, Literal
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException, Query
from app.api.deps import DbSession, CurrentUser
from app.core.config import API_V1_STR
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy import case, desc, false, func, or_
from app.models.project_asset import ProjectAsset, UserAssetFavorite
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services.asset_preview_contract import CANVAS_PREVIEW_WIDTHS, CANVAS_TILE_SIZE
from app.services.asset_preview_service import asset_preview_service
from app.services.asset_canvas_group_service import CanvasAssetGroupAsset, CanvasAssetGroupIndex
from app.services.canvas_asset_sync_service import CanvasAssetSyncService
from app.services.canvas_media_rehost_service import CanvasMediaRehostService
from app.services.project_canvas_service import ProjectCanvasService

router = APIRouter(tags=["assets"])

DELETE_ASSET_FORBIDDEN_DETAIL = "不能删除其他成员添加的素材，除非您是项目创建者"

# ------------- Schemas -------------

class AssetCreate(BaseModel):
    asset_type: str # image | video
    url: str
    canvas_item_id: Optional[str] = None
    origin_kind: Literal["ai_generated", "local_upload"]
    source_asset_id: Optional[int] = None

class AssetRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    asset_type: str
    url: str
    created_at: str
    updated_at: str
    adder_avatar: Optional[str] = None
    adder_nickname: Optional[str] = None
    is_favorite: bool = False
    project_name: Optional[str] = None
    canvas_item_id: Optional[str] = None
    origin_kind: str
    source_asset_id: Optional[int] = None
    list_preview_url: Optional[str] = None
    list_preview_status: Optional[str] = None
    canvas_group_id: Optional[str] = None
    canvas_group_name: Optional[str] = None

class AssetBatchRequest(BaseModel):
    asset_ids: List[int]
    action: str # delete | favorite | unfavorite

class AssetBatchResponse(BaseModel):
    success: bool
    message: str


class AssetProjectSummaryRead(BaseModel):
    project_id: int
    project_name: Optional[str] = None
    asset_count: int
    image_count: int
    video_count: int
    latest_asset_updated_at: Optional[str] = None


class AssetGroupSummaryRead(BaseModel):
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    asset_count: int
    image_count: int
    video_count: int
    is_ungrouped: bool = False


class CanvasAssetPreviewRead(BaseModel):
    url: Optional[str] = None
    status: Optional[Literal["ready", "pending", "missing"]] = None


class CanvasAssetTileRead(BaseModel):
    url: Optional[str] = None
    status: Optional[Literal["ready", "pending", "missing"]] = None
    tile_size: int
    source_width: Optional[int] = None
    source_height: Optional[int] = None
    level_width: Optional[int] = None
    level_height: Optional[int] = None
    columns: Optional[int] = None
    rows: Optional[int] = None

# ------------- Helpers -------------

async def _check_project_access(db, project_id: int, user_id: int, read_only: bool = False, username: str = None) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project.user_id != user_id:
        # Admin can view anything
        if read_only and username == "admin":
            return project
            
        member_stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        )
        member_res = await db.execute(member_stmt)
        if not member_res.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="无权访问该项目")
            
    return project

async def _is_project_creator(db, project_id: int, user_id: int) -> bool:
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    return project and project.user_id == user_id


def _stringify_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _get_asset_access_clause(user):
    user_projects = select(Project.id).where(Project.user_id == user.id)
    member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return or_(
        ProjectAsset.project_id.in_(user_projects),
        ProjectAsset.project_id.in_(member_projects),
    )


async def _load_canvas_asset_group_index(db, project: Project, user_id: int) -> CanvasAssetGroupIndex:
    canvas_payload = await ProjectCanvasService(db).get_effective_canvas_payload(project, user_id)
    return CanvasAssetGroupIndex.from_canvas_payload(canvas_payload)


def _apply_canvas_group_filter(
    query,
    group_index: CanvasAssetGroupIndex,
    canvas_group_id: str | None,
    ungrouped_only: bool,
    *,
    canvas_user_id: int,
):
    scoped_query = query.where(ProjectAsset.user_id == canvas_user_id)

    if canvas_group_id:
        canvas_item_ids = group_index.item_ids_for_group(canvas_group_id)
        if not canvas_item_ids:
            return scoped_query.where(false())
        return scoped_query.where(ProjectAsset.canvas_item_id.in_(canvas_item_ids))

    if ungrouped_only and group_index.grouped_item_ids:
        return scoped_query.where(
            or_(
                ProjectAsset.canvas_item_id.is_(None),
                ProjectAsset.canvas_item_id.notin_(group_index.grouped_item_ids),
            )
        )

    if ungrouped_only:
        return scoped_query

    return query


def _build_asset_read(
    asset: ProjectAsset,
    project_title: str | None,
    u: User | None,
    fav_user_id: int | None,
    *,
    group_index: CanvasAssetGroupIndex | None = None,
) -> AssetRead:
    canvas_group = group_index.group_for_canvas_item(asset.canvas_item_id) if group_index else None
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        user_id=asset.user_id,
        asset_type=asset.asset_type,
        url=asset.url,
        created_at=str(asset.created_at),
        updated_at=str(asset.updated_at),
        adder_avatar=u.avatar_url if u else None,
        adder_nickname=u.nickname if u else None,
        is_favorite=(fav_user_id is not None),
        project_name=project_title,
        canvas_item_id=asset.canvas_item_id,
        origin_kind=asset.origin_kind,
        source_asset_id=asset.source_asset_id,
        canvas_group_id=canvas_group.group_id if canvas_group else None,
        canvas_group_name=canvas_group.group_name if canvas_group else None,
    )


async def _enrich_asset_read_preview(asset_read: AssetRead) -> AssetRead:
    preview = await asset_preview_service.get_list_preview(
        asset_id=asset_read.id,
        project_id=asset_read.project_id,
        user_id=asset_read.user_id,
        asset_type=asset_read.asset_type,
        asset_url=asset_read.url,
    )
    asset_read.list_preview_url = preview.url
    asset_read.list_preview_status = preview.status
    return asset_read


async def _enrich_asset_reads_with_previews(asset_reads: list[AssetRead]) -> list[AssetRead]:
    if not asset_reads:
        return asset_reads
    return list(await asyncio.gather(*[_enrich_asset_read_preview(asset_read) for asset_read in asset_reads]))


async def _canvas_preview_url_belongs_to_project(db, *, project_id: int, asset_url: str) -> bool:
    path = unquote(urlsplit(asset_url).path or "")
    if path.startswith(f"{API_V1_STR}/uploads/canvas/{project_id}/"):
        return True

    stmt = select(ProjectAsset.id).where(
        ProjectAsset.project_id == project_id,
        or_(ProjectAsset.url == asset_url, ProjectAsset.url == path),
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None

# ------------- Endpoints -------------

@router.post("/projects/{project_id}/assets", response_model=AssetRead)
async def create_asset(
    project_id: int,
    data: AssetCreate,
    db: DbSession,
    user: CurrentUser,
):
    await _check_project_access(db, project_id, user.id, read_only=False, username=user.username)
    asset_url = await CanvasMediaRehostService(db).rehost_url(
        data.url,
        target_project_id=project_id,
        user_id=user.id,
    ) or data.url

    asset = ProjectAsset(
        project_id=project_id,
        user_id=user.id,
        asset_type=data.asset_type,
        url=asset_url,
        canvas_item_id=data.canvas_item_id,
        origin_kind=data.origin_kind,
        source_asset_id=data.source_asset_id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    
    # Get user details for return
    stmt = select(User.avatar_url, User.nickname).where(User.id == user.id)
    u_res = await db.execute(stmt)
    u_data = u_res.first()

    return _build_asset_read(asset, None, u_data, None)

@router.get("/projects/{project_id}/assets", response_model=List[AssetRead])
async def list_assets(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    asset_type: Optional[str] = None,
    favorite_only: bool = False,
    user_id: Optional[int] = None,
    origin_kind: Optional[str] = None,
    canvas_group_id: Optional[str] = None,
    ungrouped_only: bool = False,
    skip: int = 0,
    limit: int = 50
):
    if canvas_group_id and ungrouped_only:
        raise HTTPException(status_code=400, detail="canvas_group_id and ungrouped_only cannot be used together")

    project = await _check_project_access(db, project_id, user.id, read_only=True, username=user.username)
    group_index = await _load_canvas_asset_group_index(db, project, user.id)

    query = (
        select(ProjectAsset, User, UserAssetFavorite.user_id.label('fav_user_id'), Project.title)
        .join(User, ProjectAsset.user_id == User.id)
        .join(Project, ProjectAsset.project_id == Project.id)
        .outerjoin(UserAssetFavorite, 
            (ProjectAsset.id == UserAssetFavorite.asset_id) & 
            (UserAssetFavorite.user_id == user.id)
        )
        .where(ProjectAsset.project_id == project_id)
        .order_by(desc(ProjectAsset.updated_at), desc(ProjectAsset.created_at))
    )

    if asset_type:
        query = query.where(ProjectAsset.asset_type == asset_type)

    if favorite_only:
        query = query.where(UserAssetFavorite.user_id == user.id)

    if user_id:
        query = query.where(ProjectAsset.user_id == user_id)

    if origin_kind:
        query = query.where(ProjectAsset.origin_kind == origin_kind)

    query = _apply_canvas_group_filter(
        query,
        group_index,
        canvas_group_id,
        ungrouped_only,
        canvas_user_id=user.id,
    )
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    assets = []
    for asset, u, fav_user_id, project_title in rows:
        assets.append(_build_asset_read(asset, project_title, u, fav_user_id, group_index=group_index))

    return await _enrich_asset_reads_with_previews(assets)


@router.get("/projects/{project_id}/assets/groups", response_model=List[AssetGroupSummaryRead])
async def list_asset_groups(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    asset_type: Optional[str] = None,
    favorite_only: bool = False,
    origin_kind: Optional[str] = None,
):
    project = await _check_project_access(db, project_id, user.id, read_only=True, username=user.username)
    group_index = await _load_canvas_asset_group_index(db, project, user.id)

    query = (
        select(ProjectAsset.canvas_item_id, ProjectAsset.asset_type)
        .outerjoin(
            UserAssetFavorite,
            (ProjectAsset.id == UserAssetFavorite.asset_id) &
            (UserAssetFavorite.user_id == user.id)
        )
        .where(ProjectAsset.project_id == project_id)
        .where(ProjectAsset.user_id == user.id)
    )

    if asset_type:
        query = query.where(ProjectAsset.asset_type == asset_type)

    if favorite_only:
        query = query.where(UserAssetFavorite.user_id == user.id)

    if origin_kind:
        query = query.where(ProjectAsset.origin_kind == origin_kind)

    rows = (await db.execute(query)).all()
    summaries = group_index.summarize_assets(
        CanvasAssetGroupAsset(
            canvas_item_id=canvas_item_id,
            asset_type=row_asset_type,
        )
        for canvas_item_id, row_asset_type in rows
    )

    return [
        AssetGroupSummaryRead(
            group_id=summary.group_id,
            group_name=summary.group_name,
            asset_count=summary.asset_count,
            image_count=summary.image_count,
            video_count=summary.video_count,
            is_ungrouped=summary.is_ungrouped,
        )
        for summary in summaries
    ]


@router.get("/projects/{project_id}/assets/canvas-preview", response_model=CanvasAssetPreviewRead)
async def get_canvas_asset_preview(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    url: str = Query(..., min_length=1),
    width: int = Query(...),
):
    if width not in CANVAS_PREVIEW_WIDTHS:
        raise HTTPException(status_code=422, detail="Unsupported canvas preview width")

    await _check_project_access(db, project_id, user.id, read_only=True, username=user.username)
    if not await _canvas_preview_url_belongs_to_project(db, project_id=project_id, asset_url=url):
        return CanvasAssetPreviewRead(url=None, status=None)

    preview = await asset_preview_service.get_canvas_preview(
        project_id=project_id,
        user_id=user.id,
        asset_url=url,
        width=width,
    )
    return CanvasAssetPreviewRead(url=preview.url, status=preview.status)


@router.get("/projects/{project_id}/assets/canvas-tile", response_model=CanvasAssetTileRead)
async def get_canvas_asset_tile(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    url: str = Query(..., min_length=1),
    z: int = Query(..., ge=0, le=12),
    x: int = Query(..., ge=0),
    y: int = Query(..., ge=0),
):
    await _check_project_access(db, project_id, user.id, read_only=True, username=user.username)
    if not await _canvas_preview_url_belongs_to_project(db, project_id=project_id, asset_url=url):
        return CanvasAssetTileRead(url=None, status=None, tile_size=CANVAS_TILE_SIZE)

    tile = await asset_preview_service.get_canvas_tile(
        project_id=project_id,
        asset_url=url,
        z=z,
        x=x,
        y=y,
    )
    return CanvasAssetTileRead(
        url=tile.url,
        status=tile.status,
        tile_size=tile.tile_size,
        source_width=tile.source_width,
        source_height=tile.source_height,
        level_width=tile.level_width,
        level_height=tile.level_height,
        columns=tile.columns,
        rows=tile.rows,
    )

@router.get("/assets", response_model=List[AssetRead])
async def list_all_assets(
    db: DbSession,
    user: CurrentUser,
    asset_type: Optional[str] = None,
    favorite_only: bool = False,
    origin_kind: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    query = (
        select(ProjectAsset, User, UserAssetFavorite.user_id.label('fav_user_id'), Project.title)
        .join(User, ProjectAsset.user_id == User.id)
        .join(Project, ProjectAsset.project_id == Project.id)
        .outerjoin(UserAssetFavorite, 
            (ProjectAsset.id == UserAssetFavorite.asset_id) & 
            (UserAssetFavorite.user_id == user.id)
        )
    )
    
    if user.username == "admin":
        query = query.where(Project.deleted_at.is_(None))
    else:
        query = query.where(_get_asset_access_clause(user))
        
    query = query.order_by(desc(ProjectAsset.updated_at), desc(ProjectAsset.created_at))

    if asset_type:
        query = query.where(ProjectAsset.asset_type == asset_type)

    if favorite_only:
        query = query.where(UserAssetFavorite.user_id == user.id)

    if origin_kind:
        query = query.where(ProjectAsset.origin_kind == origin_kind)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    assets = []
    for asset, u, fav_user_id, project_title in rows:
        assets.append(_build_asset_read(asset, project_title, u, fav_user_id))

    return await _enrich_asset_reads_with_previews(assets)


@router.get("/assets/projects", response_model=List[AssetProjectSummaryRead])
async def list_asset_projects(
    db: DbSession,
    user: CurrentUser,
    asset_type: Optional[str] = None,
    favorite_only: bool = False,
    origin_kind: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    image_count = func.sum(case((ProjectAsset.asset_type == "image", 1), else_=0))
    video_count = func.sum(case((ProjectAsset.asset_type == "video", 1), else_=0))
    latest_asset_updated_at = func.max(ProjectAsset.updated_at)

    query = (
        select(
            Project.id.label("project_id"),
            Project.title.label("project_name"),
            func.count(ProjectAsset.id).label("asset_count"),
            image_count.label("image_count"),
            video_count.label("video_count"),
            latest_asset_updated_at.label("latest_asset_updated_at"),
        )
        .join(Project, ProjectAsset.project_id == Project.id)
        .outerjoin(
            UserAssetFavorite,
            (ProjectAsset.id == UserAssetFavorite.asset_id)
            & (UserAssetFavorite.user_id == user.id),
        )
    )

    if user.username == "admin":
        query = query.where(Project.deleted_at.is_(None))
    else:
        query = query.where(_get_asset_access_clause(user))

    if asset_type:
        query = query.where(ProjectAsset.asset_type == asset_type)

    if favorite_only:
        query = query.where(UserAssetFavorite.user_id == user.id)

    if origin_kind:
        query = query.where(ProjectAsset.origin_kind == origin_kind)

    query = (
        query.group_by(Project.id, Project.title)
        .order_by(desc(latest_asset_updated_at), desc(Project.id))
        .offset(skip)
        .limit(limit)
    )

    rows = (await db.execute(query)).all()
    return [
        AssetProjectSummaryRead(
            project_id=row.project_id,
            project_name=row.project_name,
            asset_count=row.asset_count,
            image_count=row.image_count,
            video_count=row.video_count,
            latest_asset_updated_at=_stringify_datetime(row.latest_asset_updated_at),
        )
        for row in rows
    ]

@router.post("/projects/{project_id}/assets/batch", response_model=AssetBatchResponse)
async def batch_operations(
    project_id: int,
    data: AssetBatchRequest,
    db: DbSession,
    user: CurrentUser,
):
    await _check_project_access(db, project_id, user.id, read_only=False, username=user.username)
    is_creator = await _is_project_creator(db, project_id, user.id)

    if not data.asset_ids:
        return AssetBatchResponse(success=True, message="No assets provided")

    if data.action == "delete":
        stmt = select(ProjectAsset).where(
            ProjectAsset.id.in_(data.asset_ids),
            ProjectAsset.project_id == project_id
        )
        result = await db.execute(stmt)
        assets_to_delete = result.scalars().all()

        for asset in assets_to_delete:
            if not is_creator and asset.user_id != user.id:
                raise HTTPException(status_code=403, detail=DELETE_ASSET_FORBIDDEN_DETAIL)

        sync_service = CanvasAssetSyncService(db)
        await sync_service.remove_canvas_items_for_assets(assets_to_delete)
        for asset in assets_to_delete:
            await db.delete(asset)
        await db.commit()
        return AssetBatchResponse(success=True, message=f"Deleted {len(assets_to_delete)} assets")

    elif data.action == "favorite":
        for a_id in data.asset_ids:
            # Check if already favorited
            check_stmt = select(UserAssetFavorite).where(
                UserAssetFavorite.user_id == user.id,
                UserAssetFavorite.asset_id == a_id
            )
            res = await db.execute(check_stmt)
            if not res.scalar_one_or_none():
                fav = UserAssetFavorite(user_id=user.id, asset_id=a_id)
                db.add(fav)
        await db.commit()
        return AssetBatchResponse(success=True, message="Favorited assets")

    elif data.action == "unfavorite":
        stmt = select(UserAssetFavorite).where(
            UserAssetFavorite.user_id == user.id,
            UserAssetFavorite.asset_id.in_(data.asset_ids)
        )
        res = await db.execute(stmt)
        favs = res.scalars().all()
        for f in favs:
            await db.delete(f)
        await db.commit()
        return AssetBatchResponse(success=True, message="Unfavorited assets")

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@router.post("/assets/batch", response_model=AssetBatchResponse)
async def global_batch_operations(
    data: AssetBatchRequest,
    db: DbSession,
    user: CurrentUser,
):
    if not data.asset_ids:
        return AssetBatchResponse(success=True, message="No assets provided")

    if data.action == "delete":
        stmt = (
            select(ProjectAsset, Project)
            .join(Project, ProjectAsset.project_id == Project.id)
            .where(ProjectAsset.id.in_(data.asset_ids))
        )
        result = await db.execute(stmt)
        asset_project_pairs = result.all()
        
        assets_to_delete = []
        for asset, project in asset_project_pairs:
            is_creator = project.user_id == user.id
            if not is_creator and asset.user_id != user.id:
                raise HTTPException(status_code=403, detail=DELETE_ASSET_FORBIDDEN_DETAIL)
            assets_to_delete.append(asset)

        sync_service = CanvasAssetSyncService(db)
        await sync_service.remove_canvas_items_for_assets(assets_to_delete)
        for asset in assets_to_delete:
            await db.delete(asset)
        await db.commit()
        return AssetBatchResponse(success=True, message=f"Deleted {len(assets_to_delete)} assets")

    elif data.action == "favorite":
        for a_id in data.asset_ids:
            check_stmt = select(UserAssetFavorite).where(
                UserAssetFavorite.user_id == user.id,
                UserAssetFavorite.asset_id == a_id
            )
            res = await db.execute(check_stmt)
            if not res.scalar_one_or_none():
                fav = UserAssetFavorite(user_id=user.id, asset_id=a_id)
                db.add(fav)
        await db.commit()
        return AssetBatchResponse(success=True, message="Favorited assets")

    elif data.action == "unfavorite":
        stmt = select(UserAssetFavorite).where(
            UserAssetFavorite.user_id == user.id,
            UserAssetFavorite.asset_id.in_(data.asset_ids)
        )
        res = await db.execute(stmt)
        favs = res.scalars().all()
        for f in favs:
            await db.delete(f)
        await db.commit()
        return AssetBatchResponse(success=True, message="Unfavorited assets")

    else:
        raise HTTPException(status_code=400, detail="Invalid action")
