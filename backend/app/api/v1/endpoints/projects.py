from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import PaginatedData, ResponseBase
from app.schemas.project import ProjectCreate, ProjectListItemRead, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead)
async def create_project(
    data: ProjectCreate,
    db: DbSession,
    user: CurrentUser,
):
    svc = ProjectService(db)
    return await svc.create(user.id, data)


@router.get("", response_model=ResponseBase[PaginatedData[ProjectListItemRead]])
async def list_projects(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    svc = ProjectService(db)
    is_admin = user.role == "admin"
    total, projects = await svc.list_by_user(user.id, page, page_size, is_admin=is_admin)
    return ResponseBase(
        data=PaginatedData(
            items=projects,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )
    )


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
):
    svc = ProjectService(db)
    is_admin = user.role == "admin"
    return await svc.get(project_id, user.id, is_admin=is_admin)


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: DbSession,
    user: CurrentUser,
):
    svc = ProjectService(db)
    return await svc.update(project_id, user.id, data)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
):
    svc = ProjectService(db)
    await svc.delete(project_id, user.id, is_admin=user.role == "admin")
    return {"message": "项目已删除"}
