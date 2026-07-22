from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.project_member import ProjectMember
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User


async def _authenticate_client(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str,
) -> User:
    user = User(
        email=f"ps-edit-{suffix}@example.com",
        username=f"ps_edit_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return user


@pytest.fixture(autouse=True)
def _force_public_deploy(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "public")


async def _create_project_for_user(
    db_session: AsyncSession,
    user: User,
    *,
    title: str = "Photoshop Edit Project",
) -> Project:
    project = Project(user_id=user.id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _seed_canvas(
    db_session: AsyncSession,
    project_id: int,
    user_id: int,
    item: dict | list[dict],
) -> None:
    canvas_items = item if isinstance(item, list) else [item]
    db_session.add(
        ProjectUserCanvas(
            project_id=project_id,
            user_id=user_id,
            canvas_data=canvas_items,
            canvas_meta=None,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_photoshop_edit_job_is_idempotent_for_same_canvas_item(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "create")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/source.svg",
        "x": 12,
        "y": 24,
        "width": 640,
        "height": 480,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)

    payload = {
        "source_canvas_item_id": "image-1",
        "svg_url": "/api/v1/uploads/canvas/1/source.svg",
    }
    first = await client.post(f"/api/v1/projects/{project.id}/photoshop-edit-jobs", json=payload)
    second = await client.post(f"/api/v1/projects/{project.id}/photoshop-edit-jobs", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_pending_photoshop_edit_jobs_only_return_current_users_jobs(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await _authenticate_client(client, db_session, "owner")
    project = await _create_project_for_user(db_session, owner)
    source_item = {
        "id": "image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/source.svg",
        "x": 0,
        "y": 0,
        "width": 512,
        "height": 512,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, owner.id, source_item)
    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-1",
            "svg_url": "/api/v1/uploads/canvas/1/source.svg",
        },
    )
    assert create_response.status_code == 200

    other_user = User(
        email="ps-edit-member@example.com",
        username="ps_edit_member",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    db_session.add(ProjectMember(project_id=project.id, user_id=other_user.id, role="editor"))
    await db_session.commit()

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=other_user.id)}"
    pending_for_other = await client.get("/api/v1/photoshop-edit-jobs/pending")

    assert pending_for_other.status_code == 200
    assert pending_for_other.json() == []


@pytest.mark.asyncio
async def test_claiming_same_photoshop_edit_job_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "claim")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-claim",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/claim.svg",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 200,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)
    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-claim",
            "svg_url": "/api/v1/uploads/canvas/1/claim.svg",
        },
    )
    job_id = create_response.json()["id"]

    first = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/claim")
    second = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/claim")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "claimed"
    assert second.json()["status"] == "claimed"
    assert first.json()["claimed_by_user_id"] == user.id
    assert second.json()["claimed_by_user_id"] == user.id


@pytest.mark.asyncio
async def test_cancel_photoshop_edit_job_removes_it_from_pending(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "cancel")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-cancel",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/cancel.svg",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 200,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)
    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-cancel",
            "svg_url": "/api/v1/uploads/canvas/1/cancel.svg",
        },
    )
    job_id = create_response.json()["id"]

    cancel_response = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/cancel")
    pending_response = await client.get("/api/v1/photoshop-edit-jobs/pending")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert pending_response.status_code == 200
    assert pending_response.json() == []


@pytest.mark.asyncio
async def test_claimed_photoshop_edit_job_is_not_listed_as_pending(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "claimed-pending")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-claimed-pending",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/claimed-pending.svg",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 200,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)
    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-claimed-pending",
            "svg_url": "/api/v1/uploads/canvas/1/claimed-pending.svg",
        },
    )
    job_id = create_response.json()["id"]

    claim_response = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/claim")
    pending_response = await client.get("/api/v1/photoshop-edit-jobs/pending")

    assert claim_response.status_code == 200
    assert claim_response.json()["status"] == "claimed"
    assert pending_response.status_code == 200
    assert pending_response.json() == []


@pytest.mark.asyncio
async def test_save_photoshop_edit_job_creates_asset_and_appends_canvas_item(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "save")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-save",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/original.svg",
        "x": 10,
        "y": 20,
        "width": 420,
        "height": 320,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)

    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-save",
            "svg_url": "/api/v1/uploads/canvas/1/original.svg",
        },
    )
    job_id = create_response.json()["id"]

    save_response = await client.post(
        f"/api/v1/photoshop-edit-jobs/{job_id}/save",
        json={
            "result_url": "/api/v1/uploads/canvas/1/result.svg",
            "width": 800,
            "height": 600,
            "name": "Edited SVG",
        },
    )

    assert save_response.status_code == 200
    payload = save_response.json()
    assert payload["status"] == "saved"
    assert payload["result_asset_id"] is not None
    assert payload["result_canvas_item_id"]

    asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.id == payload["result_asset_id"])
        )
    ).scalar_one()
    assert asset.project_id == project.id
    assert asset.user_id == user.id
    assert asset.url == "/api/v1/uploads/canvas/1/result.svg"
    assert asset.asset_type == "image"
    assert asset.origin_kind == "local_upload"

    canvas = (
        await db_session.execute(
            select(ProjectUserCanvas).where(
                ProjectUserCanvas.project_id == project.id,
                ProjectUserCanvas.user_id == user.id,
            )
        )
    ).scalar_one()
    result_item = next(item for item in canvas.canvas_data if item["id"] == payload["result_canvas_item_id"])
    assert result_item["url"] == "/api/v1/uploads/canvas/1/result.svg"
    assert result_item["source_asset_id"] == payload["result_asset_id"]
    assert result_item["width"] == 800
    assert result_item["height"] == 600
    assert canvas.canvas_revision == 1


@pytest.mark.asyncio
async def test_save_photoshop_edit_job_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "save-idempotent")
    project = await _create_project_for_user(db_session, user)
    source_item = {
        "id": "image-dup-save",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/source-save.svg",
        "x": 0,
        "y": 0,
        "width": 256,
        "height": 256,
        "asset_origin": "local_upload",
    }
    await _seed_canvas(db_session, project.id, user.id, source_item)
    create_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-dup-save",
            "svg_url": "/api/v1/uploads/canvas/1/source-save.svg",
        },
    )
    job_id = create_response.json()["id"]

    payload = {
        "result_url": "/api/v1/uploads/canvas/1/result-save.svg",
        "width": 900,
        "height": 900,
        "name": "Final SVG",
    }
    first = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/save", json=payload)
    second = await client.post(f"/api/v1/photoshop-edit-jobs/{job_id}/save", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result_asset_id"] == second.json()["result_asset_id"]
    assert first.json()["result_canvas_item_id"] == second.json()["result_canvas_item_id"]


@pytest.mark.asyncio
async def test_photoshop_plugin_save_creates_asset_and_canvas_item_named_ps_add(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "plugin-save")
    project = await _create_project_for_user(db_session, user)
    await _seed_canvas(
        db_session,
        project.id,
        user.id,
        {
            "id": "existing-image",
            "type": "image",
            "url": "/api/v1/uploads/canvas/1/existing.png",
            "x": 100,
            "y": 120,
            "width": 320,
            "height": 240,
            "asset_origin": "local_upload",
        },
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-plugin/save",
        json={
            "result_url": "/api/v1/uploads/canvas/1/ps-result.png",
            "width": 640,
            "height": 480,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project.id
    assert payload["asset_id"] is not None
    assert payload["canvas_item_id"].startswith("ps-plugin-save-")
    assert payload["url"] == "/api/v1/uploads/canvas/1/ps-result.png"

    asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.id == payload["asset_id"])
        )
    ).scalar_one()
    assert asset.project_id == project.id
    assert asset.user_id == user.id
    assert asset.asset_type == "image"
    assert asset.origin_kind == "local_upload"

    canvas = (
        await db_session.execute(
            select(ProjectUserCanvas).where(
                ProjectUserCanvas.project_id == project.id,
                ProjectUserCanvas.user_id == user.id,
            )
        )
    ).scalar_one()
    result_item = next(item for item in canvas.canvas_data if item["id"] == payload["canvas_item_id"])
    assert result_item["name"] == "PS添加"
    assert result_item["type"] == "image"
    assert result_item["url"] == "/api/v1/uploads/canvas/1/ps-result.png"
    assert result_item["width"] == 640
    assert result_item["height"] == 480
    assert result_item["asset_origin"] == "local_upload"
    assert result_item["source_asset_id"] == payload["asset_id"]
    assert canvas.canvas_revision == 1


@pytest.mark.asyncio
async def test_photoshop_plugin_save_rejects_project_without_access(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await _authenticate_client(client, db_session, "plugin-owner")
    project = await _create_project_for_user(db_session, owner)

    outsider = User(
        email="ps-edit-plugin-outsider@example.com",
        username="ps_edit_plugin_outsider",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(outsider)
    await db_session.commit()
    await db_session.refresh(outsider)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=outsider.id)}"

    response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-plugin/save",
        json={
            "result_url": "/api/v1/uploads/canvas/1/ps-result.png",
            "width": 640,
            "height": 480,
        },
    )

    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_photoshop_plugin_save_places_result_near_dense_area_without_overlap(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _authenticate_client(client, db_session, "plugin-placement")
    project = await _create_project_for_user(db_session, user)
    existing_items = [
        {
            "id": f"dense-{index}",
            "type": "image",
            "url": f"/api/v1/uploads/canvas/1/dense-{index}.png",
            "x": 100 + (index % 2) * 130,
            "y": 100 + (index // 2) * 130,
            "width": 120,
            "height": 120,
            "asset_origin": "local_upload",
        }
        for index in range(4)
    ]
    await _seed_canvas(db_session, project.id, user.id, existing_items)

    response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-plugin/save",
        json={
            "result_url": "/api/v1/uploads/canvas/1/ps-placement.png",
            "width": 120,
            "height": 120,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    canvas = (
        await db_session.execute(
            select(ProjectUserCanvas).where(
                ProjectUserCanvas.project_id == project.id,
                ProjectUserCanvas.user_id == user.id,
            )
        )
    ).scalar_one()
    result_item = next(item for item in canvas.canvas_data if item["id"] == payload["canvas_item_id"])

    def overlaps(a: dict, b: dict) -> bool:
        return not (
            a["x"] + a["width"] <= b["x"]
            or b["x"] + b["width"] <= a["x"]
            or a["y"] + a["height"] <= b["y"]
            or b["y"] + b["height"] <= a["y"]
        )

    assert all(not overlaps(result_item, existing) for existing in existing_items)
    assert 80 <= result_item["x"] <= 420
    assert 80 <= result_item["y"] <= 420
