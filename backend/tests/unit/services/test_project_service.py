from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.project_service as project_service_module
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_update_persists_empty_canvas_payload_and_syncs_assets(monkeypatch):
    service = object.__new__(ProjectService)
    project = SimpleNamespace(id=7, updated_at=None)
    service.repo = SimpleNamespace(
        db=SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock()),
        lock_by_id=AsyncMock(),
    )
    service.canvas_service = SimpleNamespace(
        replace_user_canvas=AsyncMock(),
    )
    sync_user_canvas_assets = AsyncMock()

    class FakeCanvasAssetSyncService:
        def __init__(self, db):
            self.db = db

        async def sync_user_canvas_assets(self, **kwargs):
            await sync_user_canvas_assets(**kwargs)

    async def fake_get(project_id, user_id, is_admin=False):
        assert project_id == 7
        assert user_id == 42
        return project

    async def fake_attach_users(projects):
        return projects

    async def fake_attach_canvas_data(projects, user_id):
        projects[0].canvas_data = [{"id": "existing-item"}]
        return projects

    monkeypatch.setattr(service, "get", fake_get)
    monkeypatch.setattr(service, "_attach_users", fake_attach_users)
    monkeypatch.setattr(service, "_attach_canvas_data", fake_attach_canvas_data)
    monkeypatch.setattr(project_service_module, "CanvasAssetSyncService", FakeCanvasAssetSyncService)

    result = await service.update(
        7,
        42,
        SimpleNamespace(model_dump=lambda exclude_unset=True: {"canvas_data": [], "canvas_base_revision": 0}),
    )

    service.canvas_service.replace_user_canvas.assert_awaited_once_with(project, 42, [], base_revision=0)
    sync_user_canvas_assets.assert_awaited_once_with(
        project=project,
        canvas_owner_user_id=42,
        canvas_payload=[],
        actor_user_id=42,
    )
    service.repo.db.commit.assert_awaited_once()
    service.repo.db.refresh.assert_awaited_once_with(project)
    assert result.canvas_data == [{"id": "existing-item"}]
