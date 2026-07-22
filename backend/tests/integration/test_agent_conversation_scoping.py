import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.config import settings
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation


async def _create_user(
    db_session: AsyncSession,
    *,
    email: str,
    username: str,
    role: str = "user",
) -> User:
    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash("Test1234!"),
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_conversation_history_is_scoped_to_current_user_even_for_admin_username(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "cloud")
    monkeypatch.setattr(settings, "HARNESS_WORKSPACE_ROOT", str(tmp_path))

    owner = await _create_user(
        db_session,
        email="conversation-owner@example.com",
        username="conversation_owner",
    )
    admin_user = await _create_user(
        db_session,
        email="conversation-admin@example.com",
        username="admin",
    )

    project = Project(user_id=owner.id, title="Conversation Scope Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    db_session.add(ProjectMember(project_id=project.id, user_id=admin_user.id, role="editor"))
    owner_conversation = create_conversation(
        owner.id,
        title="Owner conversation",
        runtime_profile="canvas",
        project_id=project.id,
        mode="fast",
    )
    _admin_conversation = create_conversation(
        admin_user.id,
        title="Admin conversation",
        runtime_profile="canvas",
        project_id=project.id,
        mode="fast",
    )

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=admin_user.id)}"

    list_response = await client.get(
        "/api/v1/agent/harness/conversations",
        params={"project_id": project.id, "runtime_profile": "canvas"},
    )
    assert list_response.status_code == 200
    assert [item["title"] for item in list_response.json()["items"]] == ["Admin conversation"]

    detail_response = await client.get(f"/api/v1/agent/harness/conversations/{owner_conversation['id']}")
    assert detail_response.status_code == 404
