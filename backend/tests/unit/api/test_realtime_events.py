from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
async def test_realtime_events_rejects_unauthorized_project_scope(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = User(
        email="realtime-owner@example.com",
        username="realtime_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    project = Project(user_id=owner.id, title="Private realtime scope")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    response = await auth_client.get(
        "/api/v1/realtime/events",
        params={"project_id": project.id},
    )

    assert response.status_code == 403
