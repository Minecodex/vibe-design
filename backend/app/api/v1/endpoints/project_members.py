from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.models.project_member import ProjectMember
from app.repositories.project_member_repository import ProjectMemberRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import ResponseBase
from app.schemas.project_member import ProjectMemberCreate, ProjectMemberRead
from app.schemas.user import UserRead

router = APIRouter(prefix="/projects", tags=["project_members"])


@router.get("/{project_id}/members", response_model=ResponseBase[list[ProjectMemberRead]])
async def list_project_members(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
):
    """获取项目成员列表。"""
    proj_repo = ProjectRepository(db)
    is_admin = user.role == "admin"
    project = await proj_repo.get_by_id_and_user(project_id, user.id, is_admin=is_admin)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在或无权限")

    mem_repo = ProjectMemberRepository(db)
    members = await mem_repo.get_by_project_id(project_id)

    user_repo = UserRepository(db)
    res_list = []

    owner = await user_repo.get(project.user_id)
    if owner:
        res_list.append(
            ProjectMemberRead(
                id=0,
                project_id=project_id,
                user_id=project.user_id,
                role="owner",
                created_at=project.created_at,
                updated_at=project.updated_at,
                user=UserRead.model_validate(owner),
            )
        )

    for member in members:
        if member.user_id == project.user_id:
            continue
        member_user = await user_repo.get(member.user_id)
        member_read = ProjectMemberRead.model_validate(member)
        if member_user:
            member_read.user = UserRead.model_validate(member_user)
        res_list.append(member_read)

    return ResponseBase(data=res_list)


@router.post("/{project_id}/members", response_model=ResponseBase[ProjectMemberRead])
async def add_project_member(
    project_id: int,
    data: ProjectMemberCreate,
    db: DbSession,
    user: CurrentUser,
):
    """添加项目成员，仅项目拥有者或管理员可操作。"""
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=403, detail="没有权限添加成员")

    mem_repo = ProjectMemberRepository(db)
    existing = await mem_repo.get_by_project_and_user(project_id, data.user_id)
    if existing:
        raise HTTPException(status_code=400, detail="该用户已经是项目成员")

    user_repo = UserRepository(db)
    target_user = await user_repo.get(data.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    new_member = ProjectMember(project_id=project_id, user_id=data.user_id, role=data.role)
    created = await mem_repo.create(new_member)

    res = ProjectMemberRead.model_validate(created)
    res.user = target_user
    return ResponseBase(data=res)


@router.delete("/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: int,
    user_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """移除项目成员，仅项目拥有者或管理员可操作。"""
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project or (project.user_id != current_user.id and current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="没有权限移除成员")

    mem_repo = ProjectMemberRepository(db)
    await mem_repo.remove_member(project_id, user_id)
    return {"message": "已移除成员"}
