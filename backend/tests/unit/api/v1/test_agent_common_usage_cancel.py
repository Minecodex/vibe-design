from types import SimpleNamespace

import pytest

from app.api.v1.endpoints._agent_common import mark_usage_log_cancelled


@pytest.mark.asyncio
async def test_mark_usage_log_cancelled_marks_parent_and_pending_children(monkeypatch):
    parent = SimpleNamespace(id=10, status="pending")
    child_pending = SimpleNamespace(id=11, status="pending", parent_id=10)
    child_success = SimpleNamespace(id=12, status="success", parent_id=10)
    updates: list[tuple[int, str]] = []

    class FakeUsageRepo:
        def __init__(self, _db):
            pass

        async def get(self, log_id: int):
            assert log_id == 10
            return parent

        async def get_children(self, parent_id: int):
            assert parent_id == 10
            return [child_pending, child_success]

        async def update(self, obj, data: dict):
            obj.status = data["status"]
            updates.append((obj.id, data["status"]))
            return obj

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.api.v1.endpoints._agent_common.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("app.repositories.billing_repository.UsageLogRepository", FakeUsageRepo)

    await mark_usage_log_cancelled(10)

    assert updates == [(10, "cancelled"), (11, "cancelled")]
