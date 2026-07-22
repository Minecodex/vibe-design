import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import CurrentUser, DbSession, OptionalCurrentUser
from app.api.v1.endpoints.assets import AssetRead, _build_asset_read, _enrich_asset_reads_with_previews
from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.project_member import ProjectMember
from app.models.user import User
from app.repositories.project_member_repository import ProjectMemberRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.common import ResponseBase
from app.schemas.project import ProjectRead
from app.schemas.share import ShareAccess, ShareInfo, ShareUpdate

router = APIRouter(prefix="/share", tags=["share"])

FOURTEEN_DAYS = 14 * 24 * 60 * 60


async def _get_shared_project_or_404(db: DbSession, token: str) -> Project:
    result = await db.execute(select(Project).where(Project.share_token == token))
    project = result.scalar_one_or_none()

    if not project or not project.share_permission:
        raise HTTPException(status_code=404, detail="分享链接无效或已关闭")

    if project.share_expiration and int(time.time()) > project.share_expiration:
        raise HTTPException(status_code=410, detail="分享链接已过期")

    return project


@router.post("/projects/{project_id}/generate")
async def generate_share_link(
    project_id: int,
    data: ShareUpdate,
    db: DbSession,
    user: CurrentUser,
):
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限修改分享设置")

    new_token = str(uuid.uuid4()).replace("-", "")
    expiration = int(time.time()) + FOURTEEN_DAYS

    update_data = {
        "share_token": new_token,
        "share_permission": data.share_permission or "viewer",
        "share_expiration": expiration,
        "share_password": None,
    }

    updated = await proj_repo.update(project, update_data)
    return ResponseBase(data=ProjectRead.model_validate(updated))


@router.post("/{token}/access", response_model=ResponseBase[ShareInfo])
async def access_shared_project(
    token: str,
    db: DbSession,
    access_data: ShareAccess,
    user: OptionalCurrentUser,
):
    project = await _get_shared_project_or_404(db, token)

    if project.share_password and access_data.password != project.share_password:
        raise HTTPException(status_code=403, detail="密码错误")

    is_member = False
    if user:
        if project.user_id == user.id:
            is_member = True
        else:
            mem_repo = ProjectMemberRepository(db)
            existing = await mem_repo.get_by_project_and_user(project.id, user.id)
            is_member = existing is not None

    res = ShareInfo(
        project=ProjectRead.model_validate(project),
        permission=project.share_permission,
        require_password=bool(project.share_password),
        is_member=is_member,
    )
    return ResponseBase(data=res)


@router.post("/{token}/join")
async def join_shared_project(
    token: str,
    db: DbSession,
    user: CurrentUser,
):
    project = await _get_shared_project_or_404(db, token)

    if project.share_permission != "editor":
        raise HTTPException(status_code=403, detail="该链接不支持加入项目编辑")

    if project.user_id == user.id:
        return ResponseBase(data={"message": "您已经是项目所有者", "project_id": project.id})

    mem_repo = ProjectMemberRepository(db)
    existing = await mem_repo.get_by_project_and_user(project.id, user.id)
    if not existing:
        new_member = ProjectMember(project_id=project.id, user_id=user.id, role="editor")
        await mem_repo.create(new_member)

    return ResponseBase(data={"message": "成功加入项目", "project_id": project.id})


@router.post("/{token}/info")
async def get_share_info(
    token: str,
    db: DbSession,
):
    project = await _get_shared_project_or_404(db, token)

    return ResponseBase(
        data={
            "require_password": bool(project.share_password),
            "permission": project.share_permission,
        }
    )


@router.get("/{token}/assets", response_model=ResponseBase[list[AssetRead]])
async def list_shared_assets(
    token: str,
    db: DbSession,
    asset_type: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    project = await _get_shared_project_or_404(db, token)

    query = (
        select(ProjectAsset, User)
        .join(User, ProjectAsset.user_id == User.id)
        .where(ProjectAsset.project_id == project.id)
        .order_by(desc(ProjectAsset.updated_at), desc(ProjectAsset.created_at))
    )

    if asset_type:
        query = query.where(ProjectAsset.asset_type == asset_type)

    result = await db.execute(query.offset(skip).limit(limit))
    assets = [_build_asset_read(asset, project.title, asset_user, None) for asset, asset_user in result.all()]
    return ResponseBase(data=await _enrich_asset_reads_with_previews(assets))
