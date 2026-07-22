from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.project import Project
from app.models.user import User
from app.services.canvas_media_rehost_service import CanvasMediaRehostService


async def _create_user(db_session: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"rehost-{suffix}@example.com",
        username=f"rehost_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_project(db_session: AsyncSession, owner: User, title: str) -> Project:
    project = Project(user_id=owner.id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_rehost_canvas_payload_copies_accessible_canvas_upload(
    db_session: AsyncSession,
    tmp_path: Path,
):
    user = await _create_user(db_session, "owner")
    source_project = await _create_project(db_session, user, "Source")
    target_project = await _create_project(db_session, user, "Target")

    upload_root = tmp_path / "canvas"
    source_dir = upload_root / str(source_project.id)
    source_dir.mkdir(parents=True)
    (source_dir / "source.png").write_bytes(b"image")

    service = CanvasMediaRehostService(db_session, upload_root=upload_root)
    payload = [
        {
            "id": "image-1",
            "type": "image",
            "url": f"/api/v1/uploads/canvas/{source_project.id}/source.png",
        }
    ]

    result = await service.rehost_canvas_payload(
        payload,
        target_project_id=target_project.id,
        user_id=user.id,
    )

    assert result[0]["url"].startswith(f"/api/v1/uploads/canvas/{target_project.id}/")
    assert result[0]["url"] != payload[0]["url"]
    copied_filename = result[0]["url"].rsplit("/", 1)[-1]
    assert (upload_root / str(target_project.id) / copied_filename).read_bytes() == b"image"


@pytest.mark.asyncio
async def test_rehost_canvas_payload_keeps_inaccessible_canvas_upload_url(
    db_session: AsyncSession,
    tmp_path: Path,
):
    owner = await _create_user(db_session, "source-owner")
    other_user = await _create_user(db_session, "other-user")
    source_project = await _create_project(db_session, owner, "Private Source")
    target_project = await _create_project(db_session, other_user, "Target")

    upload_root = tmp_path / "canvas"
    source_dir = upload_root / str(source_project.id)
    source_dir.mkdir(parents=True)
    (source_dir / "source.png").write_bytes(b"image")

    service = CanvasMediaRehostService(db_session, upload_root=upload_root)
    payload = [
        {
            "id": "image-1",
            "type": "image",
            "url": f"/api/v1/uploads/canvas/{source_project.id}/source.png",
        }
    ]

    result = await service.rehost_canvas_payload(
        payload,
        target_project_id=target_project.id,
        user_id=other_user.id,
    )

    assert result is payload
    assert payload[0]["url"] == f"/api/v1/uploads/canvas/{source_project.id}/source.png"
    assert not (upload_root / str(target_project.id)).exists()
