from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from tempfile import gettempdir

from app.services.ephemeral_task_coordinator import (
    EphemeralTaskCoordinator,
    EphemeralTaskKey,
    EphemeralTaskLease,
)
from app.services.asset_tile_geometry import build_canvas_tile_geometry
from app.services.model_worker import ModelWorkerServer
from app.services.realtime_bus import RealtimeResource, RealtimeScope, publish_notification_sync

logger = logging.getLogger(__name__)

_SOCKET_PATH = os.path.join(gettempdir(), "asset_thumbnail_worker.sock")
_LOCK_PATH = os.path.join(gettempdir(), "asset_thumbnail_worker.lock")


def generate_list_preview(
    *,
    source_path: Path,
    target_path: Path,
    max_width: int,
    quality: int,
) -> None:
    import pyvips

    if not source_path.exists():
        raise FileNotFoundError(f"Source image does not exist: {source_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.stem}.{uuid.uuid4().hex}.tmp{target_path.suffix}")

    try:
        image = pyvips.Image.new_from_file(str(source_path), access="sequential")
        image = image.autorot()
        if image.width > max_width:
            image = image.resize(max_width / image.width)
        image.write_to_file(str(temp_path), Q=quality, strip=True)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def generate_canvas_tile(
    *,
    source_path: Path,
    target_path: Path,
    z: int,
    x: int,
    y: int,
    tile_size: int,
    quality: int,
) -> None:
    import pyvips

    if not source_path.exists():
        raise FileNotFoundError(f"Source image does not exist: {source_path}")

    source = pyvips.Image.new_from_file(str(source_path), access="random").autorot()
    geometry = build_canvas_tile_geometry(
        source_width=int(source.width),
        source_height=int(source.height),
        z=z,
        x=x,
        y=y,
        tile_size=tile_size,
    )
    if geometry is None:
        raise ValueError(f"Invalid canvas tile coordinates z={z} x={x} y={y}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.stem}.{uuid.uuid4().hex}.tmp{target_path.suffix}")

    try:
        tile = source.crop(
            geometry.source_left,
            geometry.source_top,
            geometry.source_width_crop,
            geometry.source_height_crop,
        )
        tile = tile.resize(geometry.tile_width / geometry.source_width_crop)
        tile.write_to_file(str(temp_path), Q=quality, strip=True)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


class ThumbnailTaskRegistry:
    def __init__(
        self,
        *,
        start_background_task: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self._start_background_task = start_background_task or self._default_start_background_task

    def submit(
        self,
        task_key: str,
        task_runner: Callable[[], None],
        *,
        on_success: Callable[[], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
    ) -> str:
        with self._lock:
            if task_key in self._inflight:
                return "pending"
            self._inflight.add(task_key)

        def _run() -> None:
            try:
                task_runner()
            except Exception as exc:
                logger.exception("Asset thumbnail generation failed for task %s", task_key)
                if on_failure is not None:
                    _call_task_callback(lambda: on_failure(exc), task_key=task_key, callback_name="failure")
            else:
                if on_success is not None:
                    _call_task_callback(on_success, task_key=task_key, callback_name="success")
            finally:
                with self._lock:
                    self._inflight.discard(task_key)

        self._start_background_task(_run)
        return "queued"

    @staticmethod
    def _default_start_background_task(task_runner: Callable[[], None]) -> None:
        thread = threading.Thread(target=task_runner, daemon=True)
        thread.start()


class _ThumbnailWorkerRuntime:
    def __init__(self, *, max_width: int, quality: int) -> None:
        self.max_width = max_width
        self.quality = quality
        self.registry = ThumbnailTaskRegistry()

    def handle_generate(self, request: dict) -> dict:
        source_path = Path(request["source_path"])
        target_path = Path(request["target_path"])
        task_key = str(request["task_key"])

        if target_path.exists() and source_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
            return {"ok": True, "status": "ready"}

        guard_handle = _guard_handle_from_request(request)
        status = self.registry.submit(
            task_key,
            lambda: generate_list_preview(
                source_path=source_path,
                target_path=target_path,
                max_width=int(request.get("max_width", self.max_width)),
                quality=int(request.get("quality", self.quality)),
            ),
            on_success=lambda: _on_preview_success(request, guard_handle),
            on_failure=(lambda _exc: _fail_guard_sync(guard_handle, error_type="generation_failed"))
            if guard_handle
            else None,
        )
        if status == "pending" and guard_handle is not None:
            _fail_guard_sync(guard_handle, error_type="already_pending")
        return {"ok": True, "status": status}

    def handle_generate_tile(self, request: dict) -> dict:
        source_path = Path(request["source_path"])
        target_path = Path(request["target_path"])
        task_key = str(request["task_key"])

        if target_path.exists() and source_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
            return {"ok": True, "status": "ready"}

        guard_handle = _guard_handle_from_request(request)
        status = self.registry.submit(
            task_key,
            lambda: generate_canvas_tile(
                source_path=source_path,
                target_path=target_path,
                z=int(request["z"]),
                x=int(request["x"]),
                y=int(request["y"]),
                tile_size=int(request["tile_size"]),
                quality=int(request.get("quality", self.quality)),
            ),
            on_success=lambda: _on_preview_success(request, guard_handle),
            on_failure=(lambda _exc: _fail_guard_sync(guard_handle, error_type="generation_failed"))
            if guard_handle
            else None,
        )
        if status == "pending" and guard_handle is not None:
            _fail_guard_sync(guard_handle, error_type="already_pending")
        return {"ok": True, "status": status}


class AssetThumbnailWorkerServer(ModelWorkerServer):
    def __init__(self, *, coordinator: EphemeralTaskCoordinator | None = None) -> None:
        super().__init__("asset-thumbnail", _SOCKET_PATH, _LOCK_PATH)
        self.coordinator = coordinator or EphemeralTaskCoordinator()

    def _create_model(self, config: dict[str, object]) -> _ThumbnailWorkerRuntime:
        return _ThumbnailWorkerRuntime(
            max_width=int(config.get("max_width", 320)),
            quality=int(config.get("quality", 75)),
        )

    def _handle_request(self, model: _ThumbnailWorkerRuntime, request: dict) -> dict:
        if request.get("cmd") == "generate_tile":
            return model.handle_generate_tile(request)
        if request.get("cmd") != "generate":
            raise ValueError(f"Unsupported thumbnail worker command: {request.get('cmd')}")
        return model.handle_generate(request)

    async def submit_generate_preview(
        self,
        *,
        task_key: str,
        source_path: str,
        target_path: str,
        max_width: int,
        quality: int,
        realtime: dict | None = None,
    ) -> dict:
        source = Path(source_path)
        target = Path(target_path)
        if target.exists() and source.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            return {"ok": True, "status": "ready"}
        task = EphemeralTaskKey.build(
            domain="derived-artifact",
            kind="image-list-preview",
            resource_parts=[
                _guard_identity(task_key),
                str(int(max_width)),
                str(int(quality)),
            ],
            version=_source_version(source),
        )
        handle = await self.coordinator.start(
            task,
            owner_prefix="thumbnail",
            status_payload={"transform_type": f"image:list:{int(max_width)}:{int(quality)}"},
        )
        if not handle.acquired:
            return {"ok": True, "status": "pending"}
        try:
            result = await self.submit(
                {
                    "cmd": "generate",
                    "task_key": task_key,
                    "source_path": source_path,
                    "target_path": target_path,
                    "max_width": max_width,
                    "quality": quality,
                    "guard": {
                        "key": handle.key,
                        "status_key": handle.status_key,
                        "owner": handle.owner,
                    },
                    "realtime": realtime or {},
                },
                timeout=10,
            )
        except Exception:
            await self.coordinator.fail(handle, error_type="submit_failed")
            raise
        status = str(result.get("status") or "")
        if status == "ready":
            await self.coordinator.finish(handle, status="ready")
        elif status == "pending":
            await self.coordinator.fail(handle, error_type="already_pending")
        elif status not in {"queued", "pending"}:
            await self.coordinator.fail(handle, error_type="unexpected_status")
        return result

    async def submit_generate_tile(
        self,
        *,
        task_key: str,
        source_path: str,
        target_path: str,
        z: int,
        x: int,
        y: int,
        tile_size: int,
        quality: int,
        realtime: dict | None = None,
    ) -> dict:
        source = Path(source_path)
        target = Path(target_path)
        if target.exists() and source.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            return {"ok": True, "status": "ready"}
        task = EphemeralTaskKey.build(
            domain="derived-artifact",
            kind="image-canvas-tile",
            resource_parts=[
                _guard_identity(task_key),
                str(int(z)),
                str(int(x)),
                str(int(y)),
                str(int(tile_size)),
                str(int(quality)),
            ],
            version=_source_version(source),
        )
        handle = await self.coordinator.start(
            task,
            owner_prefix="thumbnail",
            status_payload={"transform_type": f"image:canvas-tile:{int(z)}:{int(x)}:{int(y)}:{int(tile_size)}:{int(quality)}"},
        )
        if not handle.acquired:
            return {"ok": True, "status": "pending"}
        try:
            result = await self.submit(
                {
                    "cmd": "generate_tile",
                    "task_key": task_key,
                    "source_path": source_path,
                    "target_path": target_path,
                    "z": z,
                    "x": x,
                    "y": y,
                    "tile_size": tile_size,
                    "quality": quality,
                    "guard": {
                        "key": handle.key,
                        "status_key": handle.status_key,
                        "owner": handle.owner,
                    },
                    "realtime": realtime or {},
                },
                timeout=10,
            )
        except Exception:
            await self.coordinator.fail(handle, error_type="submit_failed")
            raise
        status = str(result.get("status") or "")
        if status == "ready":
            await self.coordinator.finish(handle, status="ready")
        elif status == "pending":
            await self.coordinator.fail(handle, error_type="already_pending")
        elif status not in {"queued", "pending"}:
            await self.coordinator.fail(handle, error_type="unexpected_status")
        return result


def _call_task_callback(callback: Callable[[], None], *, task_key: str, callback_name: str) -> None:
    try:
        callback()
    except Exception:
        logger.exception("Asset thumbnail %s callback failed for task %s", callback_name, task_key)


def _guard_handle_from_request(request: dict) -> EphemeralTaskLease | None:
    payload = request.get("guard")
    if not isinstance(payload, dict):
        return None
    key = str(payload.get("key") or "")
    status_key = str(payload.get("status_key") or "")
    owner = str(payload.get("owner") or "")
    if not key or not status_key or not owner:
        return None
    return EphemeralTaskLease(
        acquired=True,
        task=EphemeralTaskKey.build(domain="derived-artifact", kind="image-list-preview"),
        key=key,
        status_key=status_key,
        owner=owner,
    )


def _finish_guard_sync(handle: EphemeralTaskLease, *, status: str) -> None:
    _run_guard_action(lambda: EphemeralTaskCoordinator().finish(handle, status=status))


def _fail_guard_sync(handle: EphemeralTaskLease, *, error_type: str) -> None:
    _run_guard_action(lambda: EphemeralTaskCoordinator().fail(handle, error_type=error_type))


def _run_guard_action(action) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(action())
        return

    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            asyncio.run(action())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


def _on_preview_success(request: dict, guard_handle: EphemeralTaskLease | None) -> None:
    if guard_handle is not None:
        _finish_guard_sync(guard_handle, status="ready")
    payload = request.get("realtime")
    if not isinstance(payload, dict):
        return
    asset_id = str(payload.get("asset_id") or "").strip()
    if not asset_id:
        return
    project_id = _int_or_none(payload.get("project_id"))
    user_id = _int_or_none(payload.get("user_id"))
    version = str(payload.get("version") or "").strip() or None
    resource = RealtimeResource(type="asset", id=asset_id, version=version)
    if user_id is not None:
        publish_notification_sync(
            "asset.preview.updated",
            scope=RealtimeScope(user_id=user_id),
            resource=resource,
            reason="preview_ready",
            worker="asset-thumbnail",
        )
    if project_id is not None:
        publish_notification_sync(
            "asset.preview.updated",
            scope=RealtimeScope(project_id=project_id),
            resource=resource,
            reason="preview_ready",
            worker="asset-thumbnail",
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _guard_identity(task_key: str) -> str:
    return hashlib.sha256(str(task_key or "").encode("utf-8")).hexdigest()


def _source_version(source_path: Path) -> str:
    try:
        stat = source_path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_mtime_ns}:{stat.st_size}"


asset_thumbnail_worker = AssetThumbnailWorkerServer()
