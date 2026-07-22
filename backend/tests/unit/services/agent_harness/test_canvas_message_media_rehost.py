from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.project import Project
from app.models.user import User
from app.services.agent_harness.workspace.conversation.send_message_service import (
    _rehost_canvas_message_media,
)
from app.services.canvas_media_rehost_service import CanvasMediaRehostService


async def _create_user(db_session: AsyncSession) -> User:
    user = User(
        email="canvas-message-rehost@example.com",
        username="canvas_message_rehost",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_project(db_session: AsyncSession, user: User, title: str) -> Project:
    project = Project(user_id=user.id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_rehost_canvas_message_media_updates_asset_attachment_reference(
    db_session: AsyncSession,
    tmp_path: Path,
):
    user = await _create_user(db_session)
    source_project = await _create_project(db_session, user, "Source")
    target_project = await _create_project(db_session, user, "Target")

    upload_root = tmp_path / "canvas"
    source_dir = upload_root / str(source_project.id)
    source_dir.mkdir(parents=True)
    (source_dir / "source.png").write_bytes(b"image")

    source_url = f"/api/v1/uploads/canvas/{source_project.id}/source.png"
    attachments = [
        {
            "type": "image",
            "url": source_url,
            "name": "source.png",
            "reference": {
                "id": f"home-asset:{source_url}",
                "kind": "home_asset",
                "media_type": "image",
                "display_name": "source.png",
                "source": {
                    "type": "home_asset",
                    "url": source_url,
                },
            },
        }
    ]
    references = [attachments[0]["reference"]]

    next_attachments, next_references = await _rehost_canvas_message_media(
        attachments,
        references,
        media_rehost=CanvasMediaRehostService(db_session, upload_root=upload_root),
        project_id=target_project.id,
        user_id=user.id,
    )

    next_url = next_attachments[0]["url"]
    assert next_url.startswith(f"/api/v1/uploads/canvas/{target_project.id}/")
    assert next_url != source_url
    assert next_attachments[0]["reference"]["source"]["url"] == next_url
    assert next_attachments[0]["reference"]["id"] == f"home-asset:{next_url}"
    assert next_references[0]["source"]["url"] == next_url
    assert next_references[0]["id"] == f"home-asset:{next_url}"
