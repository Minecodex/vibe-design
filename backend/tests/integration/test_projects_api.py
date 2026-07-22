from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.security import create_access_token
from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
async def test_list_projects_returns_paginated_results_sorted_by_updated_at_desc(client, db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, 'DEPLOY_TYPE', 'saas')

    user = User(email="projects@example.com", username="projects_user", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    base_time = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    projects = [
        Project(user_id=user.id, title="Oldest Project"),
        Project(user_id=user.id, title="Newest Project"),
        Project(user_id=user.id, title="Middle Project"),
    ]
    db_session.add_all(projects)
    await db_session.commit()

    for project, updated_at in zip(
        projects,
        [base_time, base_time + timedelta(days=2), base_time + timedelta(days=1)],
        strict=True,
    ):
        project.updated_at = updated_at

    await db_session.commit()

    headers = {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}
    response = await client.get("/api/v1/projects?page=1&page_size=2", headers=headers)

    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "ok"
    assert payload["data"]["total"] == 3
    assert payload["data"]["page"] == 1
    assert payload["data"]["page_size"] == 2
    assert payload["data"]["total_pages"] == 2
    assert [item["title"] for item in payload["data"]["items"]] == ["Newest Project", "Middle Project"]
    assert all("canvas_data" not in item for item in payload["data"]["items"])


@pytest.mark.asyncio
async def test_list_projects_uses_project_id_tiebreaker_for_stable_pagination(client, db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, 'DEPLOY_TYPE', 'saas')

    user = User(email="stable-projects@example.com", username="stable_projects_user", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    same_updated_at = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    projects = [
        Project(user_id=user.id, title="First Project"),
        Project(user_id=user.id, title="Second Project"),
        Project(user_id=user.id, title="Third Project"),
    ]
    db_session.add_all(projects)
    await db_session.commit()

    for project in projects:
        project.updated_at = same_updated_at

    await db_session.commit()

    headers = {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}
    first_page = await client.get("/api/v1/projects?page=1&page_size=2", headers=headers)
    second_page = await client.get("/api/v1/projects?page=2&page_size=2", headers=headers)

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_page_items = first_page.json()["data"]["items"]
    second_page_items = second_page.json()["data"]["items"]

    assert [item["id"] for item in first_page_items] == [projects[2].id, projects[1].id]
    assert [item["id"] for item in second_page_items] == [projects[0].id]
    assert {item["id"] for item in first_page_items}.isdisjoint(
        {item["id"] for item in second_page_items}
    )


@pytest.mark.asyncio
async def test_list_projects_includes_project_preview_items(client, db_session, monkeypatch):
    from app.core.config import settings
    from app.services.asset_preview_service import asset_preview_service
    from app.services.project_canvas_service import ProjectCanvasService

    monkeypatch.setattr(settings, 'DEPLOY_TYPE', 'saas')

    user = User(email="project-previews@example.com", username="project_previews_user", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    project = Project(user_id=user.id, title="Project Preview")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    async def fake_effective_canvas_payloads(self, project_ids, user_id):
        assert project_ids == [project.id]
        assert user_id == user.id
        return {
            project.id: [
                {"id": "image-1", "type": "image", "url": "/api/v1/uploads/generated/project-preview.png"},
                {"id": "video-1", "type": "video", "url": "/api/v1/uploads/generated/project-preview.mp4"},
            ]
        }

    async def fake_get_list_preview(**kwargs):
        asset_type = kwargs["asset_type"]
        assert asset_type == "image"
        return SimpleNamespace(
            url="/api/v1/uploads/generated/project-preview__list_320.webp?v=123",
            status="ready",
            target_path=None,
        )

    monkeypatch.setattr(ProjectCanvasService, "get_effective_canvas_payloads", fake_effective_canvas_payloads)
    monkeypatch.setattr(asset_preview_service, "get_list_preview", fake_get_list_preview)

    headers = {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}
    response = await client.get("/api/v1/projects?page=1&page_size=20", headers=headers)

    assert response.status_code == 200
    payload = response.json()["data"]["items"][0]
    assert payload["project_preview_items"] == [
        {
            "asset_type": "image",
            "url": "/api/v1/uploads/generated/project-preview.png",
            "list_preview_url": "/api/v1/uploads/generated/project-preview__list_320.webp?v=123",
            "list_preview_status": "ready",
        }
    ]
