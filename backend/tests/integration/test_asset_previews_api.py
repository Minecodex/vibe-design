from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.core.config import settings
from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.user import User


async def _create_user(client: AsyncClient, db_session: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"asset-preview-{suffix}@example.com",
        username=f"asset_preview_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return user


async def _create_project(db_session: AsyncSession, owner: User, title: str) -> Project:
    project = Project(user_id=owner.id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture(autouse=True)
def _public_deploy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "public")


@pytest.mark.asyncio
async def test_project_and_global_asset_lists_include_preview_fields(client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "owner")
    project = await _create_project(db_session, owner, "Preview Project")
    db_session.add(
        ProjectAsset(
            project_id=project.id,
            user_id=owner.id,
            asset_type="image",
            url="/api/v1/uploads/generated/demo.png",
            origin_kind="ai_generated",
        )
    )
    await db_session.commit()

    async def fake_get_list_preview(**kwargs):
        asset_id = kwargs["asset_id"]
        return SimpleNamespace(
            url=f"/api/v1/uploads/generated/{asset_id}__list_320.webp",
            status="ready",
            target_path=None,
        )

    monkeypatch.setattr(asset_preview_service, "get_list_preview", fake_get_list_preview)

    project_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    global_response = await client.get("/api/v1/assets")

    assert project_response.status_code == 200
    assert global_response.status_code == 200
    assert project_response.json()[0]["list_preview_url"] == "/api/v1/uploads/generated/1__list_320.webp"
    assert project_response.json()[0]["list_preview_status"] == "ready"
    assert global_response.json()[0]["list_preview_url"] == "/api/v1/uploads/generated/1__list_320.webp"
    assert global_response.json()[0]["list_preview_status"] == "ready"


@pytest.mark.asyncio
async def test_generated_preview_static_file_uses_immutable_cache_headers(client: AsyncClient):
    preview_path = Path("uploads") / "generated" / "tests" / "preview__list_320.webp"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview-bytes")

    try:
        response = await client.get("/api/v1/uploads/generated/tests/preview__list_320.webp?v=123")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    finally:
        preview_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_canvas_preview_endpoint_returns_tier_preview_for_project_upload(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-owner")
    project = await _create_project(db_session, owner, "Canvas Preview Project")
    calls: list[dict[str, object]] = []

    async def fake_get_canvas_preview(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            url="/api/v1/uploads/canvas/1/source__canvas_2048.webp?v=123",
            status="ready",
            target_path=None,
        )

    monkeypatch.setattr(asset_preview_service, "get_canvas_preview", fake_get_canvas_preview)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-preview",
        params={
            "url": f"/api/v1/uploads/canvas/{project.id}/source.png",
            "width": 2048,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "url": "/api/v1/uploads/canvas/1/source__canvas_2048.webp?v=123",
        "status": "ready",
    }
    assert calls == [{
        "project_id": project.id,
        "user_id": owner.id,
        "asset_url": f"/api/v1/uploads/canvas/{project.id}/source.png",
        "width": 2048,
    }]


@pytest.mark.asyncio
async def test_canvas_preview_endpoint_does_not_generate_for_foreign_project_url(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-foreign")
    project = await _create_project(db_session, owner, "Canvas Preview Project")

    async def fail_get_canvas_preview(**_kwargs):
        pytest.fail("foreign project preview URL should not be generated")

    monkeypatch.setattr(asset_preview_service, "get_canvas_preview", fail_get_canvas_preview)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-preview",
        params={
            "url": "/api/v1/uploads/canvas/999/source.png",
            "width": 512,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"url": None, "status": None}


@pytest.mark.asyncio
async def test_canvas_preview_endpoint_rejects_unknown_preview_width_without_generation(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-width")
    project = await _create_project(db_session, owner, "Canvas Preview Project")

    async def fail_get_canvas_preview(**_kwargs):
        pytest.fail("unsupported preview widths must not enqueue generation")

    monkeypatch.setattr(asset_preview_service, "get_canvas_preview", fail_get_canvas_preview)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-preview",
        params={
            "url": f"/api/v1/uploads/canvas/{project.id}/source.png",
            "width": 768,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported canvas preview width"


@pytest.mark.asyncio
async def test_canvas_preview_endpoint_allows_project_asset_url(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-asset")
    project = await _create_project(db_session, owner, "Canvas Preview Project")
    db_session.add(
        ProjectAsset(
            project_id=project.id,
            user_id=owner.id,
            asset_type="image",
            url="/api/v1/uploads/generated/project-asset.png",
            origin_kind="ai_generated",
        )
    )
    await db_session.commit()
    calls: list[dict[str, object]] = []

    async def fake_get_canvas_preview(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(url=None, status="pending", target_path=None)

    monkeypatch.setattr(asset_preview_service, "get_canvas_preview", fake_get_canvas_preview)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-preview",
        params={
            "url": "/api/v1/uploads/generated/project-asset.png",
            "width": 256,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"url": None, "status": "pending"}
    assert calls[0]["asset_url"] == "/api/v1/uploads/generated/project-asset.png"


@pytest.mark.asyncio
async def test_canvas_preview_static_file_uses_immutable_cache_headers(client: AsyncClient):
    preview_path = Path("uploads") / "canvas" / "tests" / "preview__canvas_512.webp"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview-bytes")

    try:
        response = await client.get("/api/v1/uploads/canvas/tests/preview__canvas_512.webp?v=123")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    finally:
        preview_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_canvas_tile_endpoint_returns_tile_metadata_for_project_upload(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-tile-owner")
    project = await _create_project(db_session, owner, "Canvas Tile Project")
    calls: list[dict[str, object]] = []

    async def fake_get_canvas_tile(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            url="/api/v1/uploads/canvas/1/source__tile_256_2_3_1.webp?v=123",
            status="ready",
            target_path=None,
            tile_size=256,
            source_width=1024,
            source_height=512,
            level_width=1024,
            level_height=512,
            columns=4,
            rows=2,
        )

    monkeypatch.setattr(asset_preview_service, "get_canvas_tile", fake_get_canvas_tile)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-tile",
        params={
            "url": f"/api/v1/uploads/canvas/{project.id}/source.png",
            "z": 2,
            "x": 3,
            "y": 1,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "url": "/api/v1/uploads/canvas/1/source__tile_256_2_3_1.webp?v=123",
        "status": "ready",
        "tile_size": 256,
        "source_width": 1024,
        "source_height": 512,
        "level_width": 1024,
        "level_height": 512,
        "columns": 4,
        "rows": 2,
    }
    assert calls == [{
        "project_id": project.id,
        "asset_url": f"/api/v1/uploads/canvas/{project.id}/source.png",
        "z": 2,
        "x": 3,
        "y": 1,
    }]


@pytest.mark.asyncio
async def test_canvas_tile_endpoint_does_not_generate_for_foreign_project_url(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.asset_preview_service import asset_preview_service

    owner = await _create_user(client, db_session, "canvas-tile-foreign")
    project = await _create_project(db_session, owner, "Canvas Tile Project")

    async def fail_get_canvas_tile(**_kwargs):
        pytest.fail("foreign project tile URL should not be generated")

    monkeypatch.setattr(asset_preview_service, "get_canvas_tile", fail_get_canvas_tile)

    response = await client.get(
        f"/api/v1/projects/{project.id}/assets/canvas-tile",
        params={
            "url": "/api/v1/uploads/canvas/999/source.png",
            "z": 0,
            "x": 0,
            "y": 0,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "url": None,
        "status": None,
        "tile_size": 256,
        "source_width": None,
        "source_height": None,
        "level_width": None,
        "level_height": None,
        "columns": None,
        "rows": None,
    }


@pytest.mark.asyncio
async def test_canvas_tile_static_file_uses_immutable_cache_headers(client: AsyncClient):
    preview_path = Path("uploads") / "canvas" / "tests" / "preview__tile_256_2_3_1.webp"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"tile-bytes")

    try:
        response = await client.get("/api/v1/uploads/canvas/tests/preview__tile_256_2_3_1.webp?v=123")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    finally:
        preview_path.unlink(missing_ok=True)
