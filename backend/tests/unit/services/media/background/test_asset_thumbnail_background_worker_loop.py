from __future__ import annotations

import asyncio

import pytest

from app.services.media.background import worker_loop as worker_loop_module
from app.services.media.background.worker_loop import AssetThumbnailBackgroundWorkerLoop


class _ThumbnailWorkerRecorder:
    def __init__(self) -> None:
        self.start_calls: list[dict] = []
        self.shutdown_called = False

    def start(self, **kwargs) -> None:
        self.start_calls.append(kwargs)

    def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.mark.asyncio
async def test_thumbnail_loop_owns_only_thumbnail_worker(monkeypatch):
    worker = _ThumbnailWorkerRecorder()
    monkeypatch.setattr(worker_loop_module, "asset_thumbnail_worker", worker)
    task = asyncio.create_task(AssetThumbnailBackgroundWorkerLoop().run())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert worker.start_calls == [{"config": {"max_width": 320, "quality": 75}, "session_ttl": 24 * 60 * 60}]
    assert worker.shutdown_called is True
