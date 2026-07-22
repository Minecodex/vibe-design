from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.asset_preview_service import AssetPreviewService
from app.services.asset_thumbnail_worker import AssetThumbnailWorkerServer, ThumbnailTaskRegistry
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator


class FakeThumbnailWorker:
    def __init__(self, status: str = "queued") -> None:
        self.status = status
        self.calls: list[dict[str, object]] = []

    async def submit_generate_preview(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": self.status}

    async def submit_generate_tile(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": self.status}


class FlakyThumbnailWorker:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def submit_generate_preview(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError("worker down")
        return {"status": "queued"}


class FakeDerivedKeys:
    def __init__(self) -> None:
        self.resource_parts: list[tuple[str, ...]] = []

    def build(self, *, domain, purpose, resource_parts=()):
        parts = tuple(str(part) for part in resource_parts)
        self.resource_parts.append(parts)
        return f"{domain}:{purpose}:{abs(hash(parts))}"


class FakeDerivedCoordinator:
    def __init__(self) -> None:
        self.keys = FakeDerivedKeys()
        self.leases: set[str] = set()
        self.snapshots: dict[str, dict] = {}

    async def try_acquire_lease(self, key, *, owner, ttl_seconds):
        if key in self.leases:
            return {"acquired": False, "owner": "other-worker"}
        self.leases.add(key)
        return {"acquired": True, "owner": owner}

    async def release_lease(self, key, *, owner):
        self.leases.discard(key)
        return True

    async def set_snapshot(self, key, value, *, ttl_seconds):
        self.snapshots[key] = dict(value)

    async def get_snapshot(self, key):
        return self.snapshots.get(key)


def _write_file(path: Path, content: bytes = b"image") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.mark.asyncio
async def test_asset_preview_service_resolves_generated_uploads_and_builds_preview_name(tmp_path: Path):
    generated_root = tmp_path / "generated"
    canvas_root = tmp_path / "canvas"
    source = generated_root / "2026-05" / "sample.png"
    _write_file(source)

    service = AssetPreviewService(
        worker=FakeThumbnailWorker(),
        generated_root=generated_root,
        canvas_root=canvas_root,
    )

    preview = await service.get_list_preview(
        asset_id=1,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/2026-05/sample.png",
    )

    assert preview.url is None
    assert preview.status == "missing"
    assert preview.target_path == generated_root / "2026-05" / "sample__list_320.webp"


@pytest.mark.asyncio
async def test_asset_preview_service_builds_canvas_preview_tier(tmp_path: Path):
    canvas_root = tmp_path / "canvas"
    source = canvas_root / "12" / "sample.png"
    _write_file(source)
    worker = FakeThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=tmp_path / "generated",
        canvas_root=canvas_root,
        canvas_quality=82,
    )

    preview = await service.get_canvas_preview(
        project_id=12,
        user_id=34,
        asset_url="/api/v1/uploads/canvas/12/sample.png",
        width=2048,
    )

    assert preview.url is None
    assert preview.status == "missing"
    assert preview.target_path == canvas_root / "12" / "sample__canvas_2048.webp"
    assert worker.calls[0]["max_width"] == 2048
    assert worker.calls[0]["quality"] == 82
    assert worker.calls[0]["target_path"] == str(preview.target_path)
    assert str(worker.calls[0]["task_key"]).startswith("project:12:canvas:2048:")


@pytest.mark.asyncio
async def test_asset_preview_service_builds_canvas_tile_metadata_and_target(
    tmp_path: Path,
    monkeypatch,
):
    canvas_root = tmp_path / "canvas"
    source = canvas_root / "12" / "sample.png"
    _write_file(source)
    worker = FakeThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=tmp_path / "generated",
        canvas_root=canvas_root,
        tile_quality=83,
    )
    monkeypatch.setattr(
        AssetPreviewService,
        "_get_image_size",
        staticmethod(lambda _source_path: (1024, 512)),
    )

    tile = await service.get_canvas_tile(
        project_id=12,
        asset_url="/api/v1/uploads/canvas/12/sample.png",
        z=2,
        x=3,
        y=1,
    )

    assert tile.url is None
    assert tile.status == "missing"
    assert tile.target_path == canvas_root / "12" / "sample__tile_256_2_3_1.webp"
    assert tile.tile_size == 256
    assert tile.source_width == 1024
    assert tile.source_height == 512
    assert tile.level_width == 1024
    assert tile.level_height == 512
    assert tile.columns == 4
    assert tile.rows == 2
    assert worker.calls[0]["target_path"] == str(tile.target_path)
    assert worker.calls[0]["z"] == 2
    assert worker.calls[0]["x"] == 3
    assert worker.calls[0]["y"] == 1
    assert worker.calls[0]["tile_size"] == 256
    assert worker.calls[0]["quality"] == 83
    assert str(worker.calls[0]["task_key"]).startswith("project:12:tile:2:3:1:")


@pytest.mark.asyncio
async def test_asset_preview_service_rejects_out_of_range_canvas_tile_without_worker_call(
    tmp_path: Path,
    monkeypatch,
):
    canvas_root = tmp_path / "canvas"
    source = canvas_root / "12" / "sample.png"
    _write_file(source)
    worker = FakeThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=tmp_path / "generated",
        canvas_root=canvas_root,
    )
    monkeypatch.setattr(
        AssetPreviewService,
        "_get_image_size",
        staticmethod(lambda _source_path: (1024, 512)),
    )

    tile = await service.get_canvas_tile(
        project_id=12,
        asset_url="/api/v1/uploads/canvas/12/sample.png",
        z=2,
        x=4,
        y=0,
    )

    assert tile.url is None
    assert tile.status is None
    assert tile.source_width == 1024
    assert tile.source_height == 512
    assert tile.tile_size == 256
    assert worker.calls == []


@pytest.mark.asyncio
async def test_asset_preview_service_returns_ready_canvas_tile_when_fresh(
    tmp_path: Path,
    monkeypatch,
):
    canvas_root = tmp_path / "canvas"
    source = canvas_root / "12" / "sample.png"
    target = canvas_root / "12" / "sample__tile_256_0_0_0.webp"
    _write_file(source)
    _write_file(target, b"tile")
    os.utime(source, (1_700_000_000, 1_700_000_000))
    os.utime(target, (1_700_000_100, 1_700_000_100))
    worker = FakeThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=tmp_path / "generated",
        canvas_root=canvas_root,
    )
    monkeypatch.setattr(
        AssetPreviewService,
        "_get_image_size",
        staticmethod(lambda _source_path: (1024, 512)),
    )

    tile = await service.get_canvas_tile(
        project_id=12,
        asset_url="/api/v1/uploads/canvas/12/sample.png",
        z=0,
        x=0,
        y=0,
    )

    assert tile.status == "ready"
    assert tile.url is not None
    assert tile.url.startswith("/api/v1/uploads/canvas/12/sample__tile_256_0_0_0.webp?v=")
    assert tile.columns == 1
    assert tile.rows == 1
    assert worker.calls == []


@pytest.mark.asyncio
async def test_asset_preview_service_rejects_unknown_canvas_preview_tier(tmp_path: Path):
    canvas_root = tmp_path / "canvas"
    source = canvas_root / "12" / "sample.png"
    _write_file(source)
    worker = FakeThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=tmp_path / "generated",
        canvas_root=canvas_root,
    )

    preview = await service.get_canvas_preview(
        project_id=12,
        asset_url="/api/v1/uploads/canvas/12/sample.png",
        width=768,
    )

    assert preview.url is None
    assert preview.status is None
    assert worker.calls == []


@pytest.mark.asyncio
async def test_asset_preview_service_resolves_reference_gallery_uploads(tmp_path: Path):
    reference_gallery_root = tmp_path / "reference-gallery"
    source = reference_gallery_root / "2026-06" / "sample.png"
    _write_file(source)

    service = AssetPreviewService(
        worker=FakeThumbnailWorker(),
        generated_root=tmp_path / "generated",
        canvas_root=tmp_path / "canvas",
        reference_gallery_root=reference_gallery_root,
    )

    preview = await service.get_list_preview(
        asset_id="reference-gallery:1",
        asset_type="image",
        asset_url="/api/v1/uploads/reference-gallery/2026-06/sample.png",
    )

    assert preview.url is None
    assert preview.status == "missing"
    assert preview.target_path == reference_gallery_root / "2026-06" / "sample__list_320.webp"


@pytest.mark.asyncio
async def test_asset_preview_service_rejects_non_local_or_traversal_paths(tmp_path: Path):
    service = AssetPreviewService(
        worker=FakeThumbnailWorker(),
        generated_root=tmp_path / "generated",
        canvas_root=tmp_path / "canvas",
    )

    remote = await service.get_list_preview(
        asset_id=2,
        asset_type="image",
        asset_url="https://example.com/image.png",
    )
    traversal = await service.get_list_preview(
        asset_id=3,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/../secret.png",
    )

    assert remote.url is None
    assert remote.status is None
    assert traversal.url is None
    assert traversal.status is None


@pytest.mark.asyncio
async def test_asset_preview_service_returns_ready_when_preview_exists_and_is_fresh(tmp_path: Path):
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    target = generated_root / "source__list_320.webp"
    _write_file(source)
    _write_file(target, b"preview")
    target.touch()

    service = AssetPreviewService(
        worker=FakeThumbnailWorker(),
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    preview = await service.get_list_preview(
        asset_id=4,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert preview.url is not None
    assert preview.url.startswith("/api/v1/uploads/generated/source__list_320.webp?v=")
    assert preview.status == "ready"


@pytest.mark.asyncio
async def test_asset_preview_service_returns_pending_when_worker_reports_duplicate(tmp_path: Path):
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    _write_file(source)
    worker = FakeThumbnailWorker(status="pending")
    service = AssetPreviewService(
        worker=worker,
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    preview = await service.get_list_preview(
        asset_id=5,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert preview.url is None
    assert preview.status == "pending"
    assert worker.calls[0]["task_key"] == "5:list"


@pytest.mark.asyncio
async def test_asset_preview_service_regenerates_stale_preview(tmp_path: Path):
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    target = generated_root / "source__list_320.webp"
    _write_file(source)
    _write_file(target, b"preview")
    os.utime(target, (1_700_000_000, 1_700_000_000))
    os.utime(source, (1_700_000_100, 1_700_000_100))

    worker = FakeThumbnailWorker(status="queued")
    service = AssetPreviewService(
        worker=worker,
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    preview = await service.get_list_preview(
        asset_id=6,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert preview.url is None
    assert preview.status == "missing"
    assert worker.calls


@pytest.mark.asyncio
async def test_asset_preview_service_delegates_duplicate_build_suppression_to_worker(
    monkeypatch,
    tmp_path: Path,
):
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    _write_file(source)

    class SequencedThumbnailWorker:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.statuses = ["queued", "pending"]

        async def submit_generate_preview(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": self.statuses[min(len(self.calls) - 1, len(self.statuses) - 1)]}

    worker = SequencedThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    first = await service.get_list_preview(
        asset_id=7,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )
    duplicate = await service.get_list_preview(
        asset_id=7,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert first.status == "missing"
    assert duplicate.status == "pending"
    assert len(worker.calls) == 2


@pytest.mark.asyncio
async def test_asset_preview_service_releases_guard_after_failed_build_for_retry(
    monkeypatch,
    tmp_path: Path,
):
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    _write_file(source)
    worker = FlakyThumbnailWorker()
    service = AssetPreviewService(
        worker=worker,
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    failed = await service.get_list_preview(
        asset_id=8,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )
    retried = await service.get_list_preview(
        asset_id=8,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert failed.status is None
    assert retried.status == "missing"
    assert len(worker.calls) == 2


@pytest.mark.asyncio
async def test_asset_preview_service_retries_after_queued_thumbnail_task_fails(
    monkeypatch,
    tmp_path: Path,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    generated_root = tmp_path / "generated"
    source = generated_root / "source.png"
    _write_file(source)
    deferred: list[callable] = []
    worker_calls = 0

    def fake_generate_list_preview(*, source_path, target_path, max_width, quality):
        raise RuntimeError("thumbnail failed")

    class InlineWorker(AssetThumbnailWorkerServer):
        def __init__(self):
            super().__init__(coordinator=EphemeralTaskCoordinator(ttl_seconds=30))
            self.model = self._create_model({"max_width": 320, "quality": 75})
            self.model.registry = ThumbnailTaskRegistry(start_background_task=lambda fn: deferred.append(fn))

        async def submit(self, payload, timeout=10):
            nonlocal worker_calls
            worker_calls += 1
            return self._handle_request(self.model, payload)

    monkeypatch.setattr(
        "app.services.asset_thumbnail_worker.generate_list_preview",
        fake_generate_list_preview,
    )
    service = AssetPreviewService(
        worker=InlineWorker(),
        generated_root=generated_root,
        canvas_root=tmp_path / "canvas",
    )

    first = await service.get_list_preview(
        asset_id=9,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )
    deferred[0]()
    retry = await service.get_list_preview(
        asset_id=9,
        asset_type="image",
        asset_url="/api/v1/uploads/generated/source.png",
    )

    assert first.status == "missing"
    assert retry.status == "missing"
    assert worker_calls == 2
