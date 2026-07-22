import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.project_member import ProjectMember
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User


@pytest.fixture(autouse=True)
def _public_deploy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "public")


async def _authenticate_client(client: AsyncClient, db_session: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"canvas-assets-{suffix}@example.com",
        username=f"canvas_assets_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return user


async def _create_project_for_user(db_session: AsyncSession, user: User) -> Project:
    project = Project(user_id=user.id, title="Canvas Asset Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _put_canvas(client: AsyncClient, project_id: int, canvas_data: list[dict]) -> object:
    current = await client.get(f"/api/v1/projects/{project_id}")
    assert current.status_code == 200
    return await client.put(
        f"/api/v1/projects/{project_id}",
        json={
            "canvas_data": canvas_data,
            "canvas_base_revision": current.json()["canvas_revision"],
        },
    )


async def _create_member_user(db_session: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"canvas-member-{suffix}@example.com",
        username=f"canvas_member_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_project_update_removes_asset_when_canvas_item_removed(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "remove")
    project = await _create_project_for_user(db_session, user)

    initial_item = {
        "id": "local-image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/local.png",
        "x": 10,
        "y": 20,
        "width": 320,
        "height": 240,
        "asset_origin": "local_upload",
    }

    create_response = await _put_canvas(client, project.id, [initial_item])
    assert create_response.status_code == 200

    created_assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert created_assets_response.status_code == 200
    assert created_assets_response.json() == [
        {
            "id": created_assets_response.json()[0]["id"],
            "project_id": project.id,
            "user_id": user.id,
            "asset_type": "image",
            "url": "/api/v1/uploads/canvas/1/local.png",
            "created_at": created_assets_response.json()[0]["created_at"],
            "updated_at": created_assets_response.json()[0]["updated_at"],
            "adder_avatar": None,
            "adder_nickname": None,
            "is_favorite": False,
            "project_name": "Canvas Asset Project",
            "canvas_item_id": "local-image-1",
            "canvas_group_id": None,
            "canvas_group_name": None,
            "origin_kind": "local_upload",
            "source_asset_id": None,
            "list_preview_url": None,
            "list_preview_status": None,
        }
    ]

    remove_response = await _put_canvas(client, project.id, [])
    assert remove_response.status_code == 200
    assert remove_response.json()["canvas_data"] == []

    assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert assets_response.status_code == 200
    assert assets_response.json() == []


@pytest.mark.asyncio
async def test_project_assets_support_canvas_group_filters(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "group-filter")
    project = await _create_project_for_user(db_session, user)

    canvas_data = [
        {
            "id": "group-lookbook",
            "type": "group",
            "name": "Lookbook",
            "url": "",
            "x": 0,
            "y": 0,
            "width": 640,
            "height": 480,
        },
        {
            "id": "group-products",
            "type": "group",
            "name": "Products",
            "url": "",
            "x": 700,
            "y": 0,
            "width": 640,
            "height": 480,
        },
        {
            "id": "hero-image",
            "type": "image",
            "url": "/api/v1/uploads/canvas/1/hero.png",
            "groupId": "group-lookbook",
            "x": 20,
            "y": 20,
            "width": 320,
            "height": 240,
            "asset_origin": "local_upload",
        },
        {
            "id": "product-image",
            "type": "image",
            "url": "/api/v1/uploads/canvas/1/product.png",
            "groupId": "group-products",
            "x": 720,
            "y": 20,
            "width": 320,
            "height": 240,
            "asset_origin": "local_upload",
        },
        {
            "id": "standalone-image",
            "type": "image",
            "url": "/api/v1/uploads/canvas/1/standalone.png",
            "x": 0,
            "y": 520,
            "width": 320,
            "height": 240,
            "asset_origin": "local_upload",
        },
        {
            "id": "lookbook-video",
            "type": "video",
            "url": "/api/v1/uploads/canvas/1/lookbook.mp4",
            "groupId": "group-lookbook",
            "x": 360,
            "y": 20,
            "width": 320,
            "height": 180,
            "asset_origin": "local_upload",
        },
    ]
    update_response = await _put_canvas(client, project.id, canvas_data)
    assert update_response.status_code == 200

    groups_response = await client.get(
        f"/api/v1/projects/{project.id}/assets/groups",
        params={"asset_type": "image"},
    )
    assert groups_response.status_code == 200
    assert groups_response.json() == [
        {
            "group_id": "group-lookbook",
            "group_name": "Lookbook",
            "asset_count": 1,
            "image_count": 1,
            "video_count": 0,
            "is_ungrouped": False,
        },
        {
            "group_id": "group-products",
            "group_name": "Products",
            "asset_count": 1,
            "image_count": 1,
            "video_count": 0,
            "is_ungrouped": False,
        },
        {
            "group_id": None,
            "group_name": None,
            "asset_count": 1,
            "image_count": 1,
            "video_count": 0,
            "is_ungrouped": True,
        },
    ]

    lookbook_response = await client.get(
        f"/api/v1/projects/{project.id}/assets",
        params={"asset_type": "image", "canvas_group_id": "group-lookbook"},
    )
    assert lookbook_response.status_code == 200
    lookbook_assets = lookbook_response.json()
    assert [asset["canvas_item_id"] for asset in lookbook_assets] == ["hero-image"]
    assert lookbook_assets[0]["canvas_group_id"] == "group-lookbook"
    assert lookbook_assets[0]["canvas_group_name"] == "Lookbook"

    ungrouped_response = await client.get(
        f"/api/v1/projects/{project.id}/assets",
        params={"asset_type": "image", "ungrouped_only": True},
    )
    assert ungrouped_response.status_code == 200
    assert {asset["canvas_item_id"] for asset in ungrouped_response.json()} == {"standalone-image"}


@pytest.mark.asyncio
async def test_project_create_initializes_owner_canvas_row(client: AsyncClient, db_session: AsyncSession):
    from app.schemas.project import ProjectCreate
    from app.services.project_service import ProjectService

    user = await _authenticate_client(client, db_session, "owner-canvas")
    service = ProjectService(db_session)
    created_project = await service.create(user.id, ProjectCreate(title="Owner Canvas Project"))

    project_id = created_project.id
    assert created_project.canvas_data == []

    owner_canvas = (
        await db_session.execute(
            select(ProjectUserCanvas).where(
                ProjectUserCanvas.project_id == project_id,
                ProjectUserCanvas.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    assert owner_canvas is not None
    assert owner_canvas.canvas_data == []
    assert owner_canvas.canvas_meta is None
    assert owner_canvas.canvas_revision == 0
    assert created_project.canvas_revision == 0


@pytest.mark.asyncio
async def test_project_canvas_revision_rejects_stale_full_snapshot(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "revision-conflict")
    project = await _create_project_for_user(db_session, user)

    first_item = {
        "id": "first-image",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/first.png",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
    }
    stale_item = {
        "id": "stale-image",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/stale.png",
        "x": 40,
        "y": 40,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
    }

    initial = await client.get(f"/api/v1/projects/{project.id}")
    assert initial.status_code == 200
    assert initial.json()["canvas_revision"] == 0

    first_update = await client.put(
        f"/api/v1/projects/{project.id}",
        json={"canvas_data": [first_item], "canvas_base_revision": 0},
    )
    assert first_update.status_code == 200
    assert first_update.json()["canvas_revision"] == 1

    stale_update = await client.put(
        f"/api/v1/projects/{project.id}",
        json={"canvas_data": [stale_item], "canvas_base_revision": 0},
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"]["code"] == "canvas_revision_conflict"
    assert stale_update.json()["detail"]["canvas_revision"] == 1

    project_response = await client.get(f"/api/v1/projects/{project.id}")
    assert project_response.status_code == 200
    assert project_response.json()["canvas_data"] == [first_item]
    assert project_response.json()["canvas_revision"] == 1

    assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert assets_response.status_code == 200
    assert [asset["canvas_item_id"] for asset in assets_response.json()] == ["first-image"]


@pytest.mark.asyncio
async def test_project_title_update_does_not_require_canvas_revision(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "title-no-revision")
    project = await _create_project_for_user(db_session, user)

    canvas_update = await _put_canvas(client, project.id, [{"id": "item-1", "type": "image", "url": "/api/v1/uploads/canvas/1/a.png", "x": 0, "y": 0, "width": 100, "height": 100}])
    assert canvas_update.status_code == 200
    assert canvas_update.json()["canvas_revision"] == 1

    title_update = await client.put(
        f"/api/v1/projects/{project.id}",
        json={"title": "Renamed"},
    )
    assert title_update.status_code == 200
    assert title_update.json()["title"] == "Renamed"
    assert title_update.json()["canvas_revision"] == 1


@pytest.mark.asyncio
async def test_project_update_keeps_canvas_data_isolated_per_user(client: AsyncClient, db_session: AsyncSession):
    owner = await _authenticate_client(client, db_session, "scoped-owner")
    member = await _create_member_user(db_session, "scoped-member")
    project = await _create_project_for_user(db_session, owner)

    membership = ProjectMember(project_id=project.id, user_id=member.id, role="editor")
    db_session.add(membership)
    await db_session.commit()

    owner_item = {
        "id": "owner-image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/owner.png",
        "x": 10,
        "y": 20,
        "width": 320,
        "height": 240,
        "asset_origin": "local_upload",
    }
    member_item = {
        "id": "member-image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/member.png",
        "x": 40,
        "y": 80,
        "width": 400,
        "height": 300,
        "asset_origin": "local_upload",
    }

    owner_update = await _put_canvas(client, project.id, [owner_item])
    assert owner_update.status_code == 200
    assert owner_update.json()["canvas_data"] == [owner_item]

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=member.id)}"
    member_before_update = await client.get(f"/api/v1/projects/{project.id}")
    assert member_before_update.status_code == 200
    assert member_before_update.json()["canvas_data"] == []

    member_update = await _put_canvas(client, project.id, [member_item])
    assert member_update.status_code == 200
    assert member_update.json()["canvas_data"] == [member_item]

    member_after_update = await client.get(f"/api/v1/projects/{project.id}")
    assert member_after_update.status_code == 200
    assert member_after_update.json()["canvas_data"] == [member_item]

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=owner.id)}"
    owner_after_member_update = await client.get(f"/api/v1/projects/{project.id}")
    assert owner_after_member_update.status_code == 200
    assert owner_after_member_update.json()["canvas_data"] == [owner_item]


@pytest.mark.asyncio
async def test_asset_delete_removes_canvas_item_and_empty_group(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "delete")
    project = await _create_project_for_user(db_session, user)

    grouped_item = {
        "id": "video-1",
        "type": "video",
        "url": "/api/v1/uploads/canvas/1/video.mp4",
        "x": 100,
        "y": 120,
        "width": 480,
        "height": 270,
        "groupId": "group-1",
        "asset_origin": "ai_generated",
    }
    group_item = {
        "id": "group-1",
        "type": "group",
        "url": "",
        "name": "Group 1",
        "x": 80,
        "y": 90,
        "width": 540,
        "height": 340,
    }

    create_response = await _put_canvas(client, project.id, [grouped_item, group_item])
    assert create_response.status_code == 200

    asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "video-1")
        )
    ).scalar_one()

    delete_response = await client.post(
        "/api/v1/assets/batch",
        json={"asset_ids": [asset.id], "action": "delete"},
    )
    assert delete_response.status_code == 200

    project_after_delete = await client.get(f"/api/v1/projects/{project.id}")
    assert project_after_delete.status_code == 200
    assert project_after_delete.json()["canvas_data"] == []


@pytest.mark.asyncio
async def test_asset_delete_permission_error_is_localized(client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "public")

    owner = await _authenticate_client(client, db_session, "delete-owner")
    project = await _create_project_for_user(db_session, owner)
    member = await _create_member_user(db_session, "delete-member")

    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role="editor"))
    db_session.add(
        ProjectAsset(
            project_id=project.id,
            user_id=owner.id,
            asset_type="image",
            origin_kind="ai_generated",
            url="/api/v1/uploads/canvas/1/owner-delete.png",
            canvas_item_id="owner-image-1",
        )
    )
    await db_session.commit()

    asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "owner-image-1")
        )
    ).scalar_one()

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=member.id)}"
    client.headers.pop("accept-language", None)

    zh_response = await client.post(
        f"/api/v1/projects/{project.id}/assets/batch",
        json={"asset_ids": [asset.id], "action": "delete"},
    )
    assert zh_response.status_code == 403
    assert zh_response.json()["detail"] == "不能删除其他成员添加的素材，除非您是项目创建者"

    client.headers["accept-language"] = "en-US"
    en_response = await client.post(
        f"/api/v1/projects/{project.id}/assets/batch",
        json={"asset_ids": [asset.id], "action": "delete"},
    )
    assert en_response.status_code == 403
    assert en_response.json()["detail"] == "Cannot delete assets you did not add unless you are the project creator"


@pytest.mark.asyncio
async def test_project_update_creates_imported_asset_with_source_asset_id(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "import")
    project = await _create_project_for_user(db_session, user)

    first_item = {
        "id": "image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/image-1.png",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
    }
    create_response = await _put_canvas(client, project.id, [first_item])
    assert create_response.status_code == 200

    source_asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "image-1")
        )
    ).scalar_one()

    imported_item = {
        "id": "image-2",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/image-1.png",
        "x": 40,
        "y": 40,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
        "source_asset_id": source_asset.id,
    }
    second_response = await _put_canvas(client, project.id, [first_item, imported_item])
    assert second_response.status_code == 200

    assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert assets_response.status_code == 200
    assets = assets_response.json()

    imported_asset = next(asset for asset in assets if asset["canvas_item_id"] == "image-2")
    assert imported_asset["origin_kind"] == "local_upload"
    assert imported_asset["source_asset_id"] == source_asset.id


@pytest.mark.asyncio
async def test_project_update_rehosts_imported_canvas_upload_from_accessible_project(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from app.services import canvas_media_rehost_service

    upload_root = tmp_path / "canvas"
    monkeypatch.setattr(canvas_media_rehost_service, "CANVAS_UPLOAD_ROOT", upload_root)

    user = await _authenticate_client(client, db_session, "rehost-import")
    source_project = await _create_project_for_user(db_session, user)
    target_project = await _create_project_for_user(db_session, user)

    source_dir = upload_root / str(source_project.id)
    source_dir.mkdir(parents=True)
    source_file = source_dir / "source.png"
    source_file.write_bytes(b"source-image")

    source_asset = ProjectAsset(
        project_id=source_project.id,
        user_id=user.id,
        asset_type="image",
        origin_kind="local_upload",
        url=f"/api/v1/uploads/canvas/{source_project.id}/source.png",
        canvas_item_id="source-image",
    )
    db_session.add(source_asset)
    await db_session.commit()
    await db_session.refresh(source_asset)

    imported_item = {
        "id": "imported-image",
        "type": "image",
        "url": f"/api/v1/uploads/canvas/{source_project.id}/source.png",
        "x": 40,
        "y": 40,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
        "source_asset_id": source_asset.id,
    }
    response = await _put_canvas(client, target_project.id, [imported_item])
    assert response.status_code == 200

    saved_item = response.json()["canvas_data"][0]
    assert saved_item["id"] == "imported-image"
    assert saved_item["url"].startswith(f"/api/v1/uploads/canvas/{target_project.id}/")
    assert saved_item["url"] != imported_item["url"]

    copied_filename = saved_item["url"].rsplit("/", 1)[-1]
    assert (upload_root / str(target_project.id) / copied_filename).read_bytes() == b"source-image"

    imported_asset = (
        await db_session.execute(
            select(ProjectAsset).where(
                ProjectAsset.project_id == target_project.id,
                ProjectAsset.canvas_item_id == "imported-image",
            )
        )
    ).scalar_one()
    assert imported_asset.url == saved_item["url"]
    assert imported_asset.source_asset_id == source_asset.id


@pytest.mark.asyncio
async def test_deleting_imported_canvas_asset_keeps_original_shared_asset(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "import-delete")
    project = await _create_project_for_user(db_session, user)

    first_item = {
        "id": "shared-image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/source.png",
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
    }
    create_response = await _put_canvas(client, project.id, [first_item])
    assert create_response.status_code == 200

    source_asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "shared-image-1")
        )
    ).scalar_one()

    imported_item = {
        "id": "private-copy-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/source.png",
        "x": 24,
        "y": 36,
        "width": 300,
        "height": 300,
        "asset_origin": "local_upload",
        "source_asset_id": source_asset.id,
    }
    import_response = await _put_canvas(client, project.id, [first_item, imported_item])
    assert import_response.status_code == 200

    imported_asset = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "private-copy-1")
        )
    ).scalar_one()

    delete_response = await client.post(
        f"/api/v1/projects/{project.id}/assets/batch",
        json={"asset_ids": [imported_asset.id], "action": "delete"},
    )
    assert delete_response.status_code == 200

    assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert assets_response.status_code == 200
    remaining_assets = assets_response.json()

    assert [asset["canvas_item_id"] for asset in remaining_assets] == ["shared-image-1"]

    project_response = await client.get(f"/api/v1/projects/{project.id}")
    assert project_response.status_code == 200
    assert project_response.json()["canvas_data"] == [first_item]


@pytest.mark.asyncio
async def test_project_update_refreshes_asset_updated_at_and_list_order(client: AsyncClient, db_session: AsyncSession):
    user = await _authenticate_client(client, db_session, "updated-at")
    project = await _create_project_for_user(db_session, user)

    first_item = {
        "id": "image-1",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/original.png",
        "x": 0,
        "y": 0,
        "width": 400,
        "height": 400,
        "asset_origin": "local_upload",
    }
    second_item = {
        "id": "image-2",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/second.png",
        "x": 50,
        "y": 50,
        "width": 320,
        "height": 320,
        "asset_origin": "local_upload",
    }

    create_response = await _put_canvas(client, project.id, [first_item, second_item])
    assert create_response.status_code == 200

    asset_one = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "image-1")
        )
    ).scalar_one()
    asset_two = (
        await db_session.execute(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id, ProjectAsset.canvas_item_id == "image-2")
        )
    ).scalar_one()

    older_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
    asset_one.updated_at = older_timestamp
    asset_two.updated_at = older_timestamp
    await db_session.commit()

    updated_first_item = {
        **first_item,
        "url": "/api/v1/uploads/canvas/1/cropped.png",
        "width": 300,
        "height": 300,
    }
    update_response = await _put_canvas(client, project.id, [updated_first_item, second_item])
    assert update_response.status_code == 200

    assets_response = await client.get(f"/api/v1/projects/{project.id}/assets")
    assert assets_response.status_code == 200
    assets = assets_response.json()

    assert [asset["canvas_item_id"] for asset in assets] == ["image-1", "image-2"]
    refreshed_asset = assets[0]
    stale_asset = assets[1]

    assert refreshed_asset["url"] == "/api/v1/uploads/canvas/1/cropped.png"
    assert "updated_at" in refreshed_asset
    assert refreshed_asset["updated_at"] != older_timestamp.isoformat()
    assert stale_asset["updated_at"].startswith(older_timestamp.date().isoformat())
