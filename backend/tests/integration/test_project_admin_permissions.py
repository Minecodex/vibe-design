
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_generate_share_link_for_other_users_project(client: AsyncClient, db_session):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.user import User


    owner = User(
        email="project-owner@example.com",
        username="project_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="project-admin@example.com",
        username="project_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    db_session.add_all([owner, admin])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)

    project = Project(user_id=owner.id, title="Owner Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.post(
        f"/api/v1/share/projects/{project.id}/generate",
        headers=headers,
        json={"share_permission": "viewer"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["id"] == project.id
    assert payload["share_permission"] == "viewer"
    assert payload["share_token"]


@pytest.mark.asyncio
async def test_admin_can_delete_other_users_project(client: AsyncClient, db_session):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.user import User


    owner = User(
        email="delete-owner@example.com",
        username="delete_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="delete-admin@example.com",
        username="delete_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    db_session.add_all([owner, admin])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)

    project = Project(user_id=owner.id, title="Delete Me")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.delete(f"/api/v1/projects/{project.id}", headers=headers)

    assert response.status_code == 200

    await db_session.refresh(project)
    assert project.deleted_at is not None


@pytest.mark.asyncio
async def test_admin_can_add_project_member_for_other_users_project(client: AsyncClient, db_session):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.project_member import ProjectMember
    from app.models.user import User
    from sqlalchemy import select


    owner = User(
        email="member-owner@example.com",
        username="member_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="member-admin@example.com",
        username="member_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    new_member = User(
        email="new-member@example.com",
        username="new_member",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add_all([owner, admin, new_member])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)
    await db_session.refresh(new_member)

    project = Project(user_id=owner.id, title="Member Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=headers,
        json={"user_id": new_member.id, "role": "editor"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project_id"] == project.id
    assert payload["user_id"] == new_member.id
    assert payload["role"] == "editor"

    member_result = await db_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == new_member.id,
        )
    )
    assert member_result.scalar_one_or_none() is not None
