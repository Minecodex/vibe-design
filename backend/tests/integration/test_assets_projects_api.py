from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.project import Project
from app.models.project_asset import ProjectAsset, UserAssetFavorite
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services.canvas_asset_sync_service import CanvasAssetSyncService


async def _create_user(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    suffix: str,
    username: str | None = None,
) -> User:
    user = User(
        email=f"assets-projects-{suffix}@example.com",
        username=username or f"assets_projects_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
        role="user" if username != "admin" else "admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(subject=user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return user


async def _create_project_for_user(
    db_session: AsyncSession,
    *,
    owner_id: int,
    title: str,
) -> Project:
    project = Project(user_id=owner_id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_asset(
    db_session: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    asset_type: str,
    origin_kind: str,
    url: str,
    updated_at: datetime,
    canvas_item_id: str | None = None,
    source_asset_id: int | None = None,
) -> ProjectAsset:
    asset = ProjectAsset(
        project_id=project_id,
        user_id=user_id,
        asset_type=asset_type,
        origin_kind=origin_kind,
        url=url,
        canvas_item_id=canvas_item_id,
        source_asset_id=source_asset_id,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    asset.updated_at = updated_at
    asset.created_at = updated_at
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


@pytest.mark.asyncio
async def test_assets_projects_returns_filtered_project_summaries(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await _create_user(client, db_session, suffix="owner")
    viewer = await _create_user(client, db_session, suffix="viewer")
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=viewer.id)}"

    owned_project = await _create_project_for_user(
        db_session,
        owner_id=owner.id,
        title="Brand Campaign",
    )
    shared_project = await _create_project_for_user(
        db_session,
        owner_id=owner.id,
        title="Shared Motion Pack",
    )
    hidden_project = await _create_project_for_user(
        db_session,
        owner_id=owner.id,
        title="Hidden Project",
    )

    db_session.add(ProjectMember(project_id=shared_project.id, user_id=viewer.id, role="editor"))
    await db_session.commit()

    now = datetime.now(timezone.utc)
    shared_image = await _create_asset(
        db_session,
        project_id=shared_project.id,
        user_id=owner.id,
        asset_type="image",
        origin_kind="ai_generated",
        url="https://example.com/shared-image.png",
        updated_at=now - timedelta(hours=1),
    )
    await _create_asset(
        db_session,
        project_id=shared_project.id,
        user_id=owner.id,
        asset_type="video",
        origin_kind="ai_generated",
        url="https://example.com/shared-video.mp4",
        updated_at=now - timedelta(hours=2),
    )
    await _create_asset(
        db_session,
        project_id=owned_project.id,
        user_id=viewer.id,
        asset_type="image",
        origin_kind="ai_generated",
        url="https://example.com/owned-image.png",
        updated_at=now - timedelta(hours=3),
    )
    await _create_asset(
        db_session,
        project_id=owned_project.id,
        user_id=viewer.id,
        asset_type="image",
        origin_kind="local_upload",
        url="https://example.com/owned-local.png",
        updated_at=now - timedelta(hours=4),
    )
    await _create_asset(
        db_session,
        project_id=hidden_project.id,
        user_id=owner.id,
        asset_type="image",
        origin_kind="ai_generated",
        url="https://example.com/hidden-image.png",
        updated_at=now - timedelta(hours=5),
    )

    db_session.add(UserAssetFavorite(user_id=viewer.id, asset_id=shared_image.id))
    await db_session.commit()

    response = await client.get(
        "/api/v1/assets/projects",
        params={
            "origin_kind": "ai_generated",
            "favorite_only": True,
            "skip": 0,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "project_id": shared_project.id,
            "project_name": "Shared Motion Pack",
            "asset_count": 1,
            "image_count": 1,
            "video_count": 0,
            "latest_asset_updated_at": shared_image.updated_at.isoformat().replace("+00:00", ""),
        }
    ]


@pytest.mark.asyncio
async def test_assets_projects_supports_pagination_and_latest_activity_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _create_user(client, db_session, suffix="pager")
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"

    newest = await _create_project_for_user(db_session, owner_id=user.id, title="Newest")
    middle = await _create_project_for_user(db_session, owner_id=user.id, title="Middle")
    oldest = await _create_project_for_user(db_session, owner_id=user.id, title="Oldest")

    now = datetime.now(timezone.utc)
    for project, hours in ((newest, 1), (middle, 2), (oldest, 3)):
        await _create_asset(
            db_session,
            project_id=project.id,
            user_id=user.id,
            asset_type="image",
            origin_kind="ai_generated",
            url=f"https://example.com/{project.title.lower()}.png",
            updated_at=now - timedelta(hours=hours),
        )

    response = await client.get(
        "/api/v1/assets/projects",
        params={"origin_kind": "ai_generated", "skip": 1, "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["project_id"] == middle.id
    assert payload[0]["project_name"] == "Middle"


@pytest.mark.asyncio
async def test_create_asset_requires_explicit_origin_kind(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _create_user(client, db_session, suffix="create-missing-origin")
    project = await _create_project_for_user(
        db_session,
        owner_id=user.id,
        title="Create Asset Project",
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/assets",
        json={
            "asset_type": "image",
            "url": "https://example.com/upload.png",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_asset_persists_explicit_origin_kind(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _create_user(client, db_session, suffix="create-local-origin")
    project = await _create_project_for_user(
        db_session,
        owner_id=user.id,
        title="Create Asset Project",
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/assets",
        json={
            "asset_type": "image",
            "url": "https://example.com/upload.png",
            "origin_kind": "local_upload",
        },
    )

    assert response.status_code == 200
    assert response.json()["origin_kind"] == "local_upload"


@pytest.mark.asyncio
async def test_canvas_asset_sync_preserves_historical_unknown_origin(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _create_user(client, db_session, suffix="canvas-legacy-origin")
    project = await _create_project_for_user(db_session, owner_id=user.id, title="Canvas Legacy Origin")
    asset = await _create_asset(
        db_session,
        project_id=project.id,
        user_id=user.id,
        asset_type="image",
        origin_kind="legacy",
        canvas_item_id="legacy-image-1",
        url="https://cdn.example.com/unknown-origin.png",
        updated_at=datetime.now(timezone.utc),
    )

    await CanvasAssetSyncService(db_session).sync_user_canvas_assets(
        project=project,
        canvas_owner_user_id=user.id,
        canvas_payload=[
            {
                "id": "legacy-image-1",
                "type": "image",
                "url": "https://cdn.example.com/unknown-origin.png",
            }
        ],
        actor_user_id=user.id,
    )
    await db_session.commit()
    await db_session.refresh(asset)

    assert asset.origin_kind == "legacy"
