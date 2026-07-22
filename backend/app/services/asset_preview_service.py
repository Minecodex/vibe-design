from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from app.core.config import API_V1_STR
from app.services.asset_preview_contract import (
    CANVAS_PREVIEW_WIDTHS,
    CANVAS_TILE_QUALITY,
    CANVAS_TILE_SIZE,
    LIST_PREVIEW_WIDTH,
)
from app.services.asset_tile_geometry import build_canvas_tile_geometry
from app.services.asset_thumbnail_worker import asset_thumbnail_worker
from app.services.realtime_bus import RealtimeResource, RealtimeScope, publish_notification

logger = logging.getLogger(__name__)

GENERATED_UPLOAD_ROOT = Path("uploads") / "generated"
CANVAS_UPLOAD_ROOT = Path("uploads") / "canvas"
REFERENCE_GALLERY_UPLOAD_ROOT = Path("uploads") / "reference-gallery"


@dataclass(frozen=True)
class AssetListPreview:
    url: str | None
    status: str | None
    target_path: Path | None = None


@dataclass(frozen=True)
class CanvasTilePreview:
    url: str | None
    status: str | None
    target_path: Path | None = None
    tile_size: int = CANVAS_TILE_SIZE
    source_width: int | None = None
    source_height: int | None = None
    level_width: int | None = None
    level_height: int | None = None
    columns: int | None = None
    rows: int | None = None


@dataclass(frozen=True)
class _ResolvedAssetPath:
    root: Path
    source_path: Path
    url_prefix: str


class AssetPreviewService:
    def __init__(
        self,
        *,
        worker=asset_thumbnail_worker,
        generated_root: Path = GENERATED_UPLOAD_ROOT,
        canvas_root: Path = CANVAS_UPLOAD_ROOT,
        reference_gallery_root: Path = REFERENCE_GALLERY_UPLOAD_ROOT,
        list_width: int = LIST_PREVIEW_WIDTH,
        list_quality: int = 75,
        canvas_widths: tuple[int, ...] = CANVAS_PREVIEW_WIDTHS,
        canvas_quality: int = 80,
        tile_size: int = CANVAS_TILE_SIZE,
        tile_quality: int = CANVAS_TILE_QUALITY,
    ) -> None:
        self.worker = worker
        self.generated_root = generated_root
        self.canvas_root = canvas_root
        self.reference_gallery_root = reference_gallery_root
        self.list_width = list_width
        self.list_quality = list_quality
        self.canvas_widths = canvas_widths
        self.canvas_quality = canvas_quality
        self.tile_size = tile_size
        self.tile_quality = tile_quality

    async def get_list_preview(
        self,
        *,
        asset_id: int | str,
        project_id: int | None = None,
        user_id: int | None = None,
        asset_type: str,
        asset_url: str,
    ) -> AssetListPreview:
        if asset_type != "image":
            return AssetListPreview(url=None, status=None)

        resolved = self._resolve_asset_path(asset_url)
        if resolved is None or not resolved.source_path.exists() or not resolved.source_path.is_file():
            return AssetListPreview(url=None, status=None)

        target_path = self._build_target_path(resolved.source_path, purpose="list", width=self.list_width)

        if self._is_preview_fresh(source_path=resolved.source_path, target_path=target_path):
            return AssetListPreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                target_path=target_path,
            )

        result = await self._submit_preview_generation(
            task_key=f"{asset_id}:list",
            source_path=resolved.source_path,
            target_path=target_path,
            max_width=self.list_width,
            quality=self.list_quality,
            realtime={
                "asset_id": str(asset_id),
                "project_id": project_id,
                "user_id": user_id,
                "version": self._build_guard_version(source_path=resolved.source_path),
            },
            log_subject=f"asset {asset_id}",
        )
        if result is None:
            return AssetListPreview(url=None, status=None, target_path=target_path)

        status = str(result.get("status") or "")
        if status == "ready":
            await self._publish_preview_updated(
                asset_id=asset_id,
                project_id=project_id,
                user_id=user_id,
                version=self._build_guard_version(source_path=resolved.source_path),
            )
            return AssetListPreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                target_path=target_path,
            )
        if status == "pending":
            return AssetListPreview(url=None, status="pending", target_path=target_path)
        if status == "queued":
            return AssetListPreview(url=None, status="missing", target_path=target_path)
        return AssetListPreview(url=None, status=None, target_path=target_path)

    async def get_canvas_tile(
        self,
        *,
        project_id: int,
        asset_url: str,
        z: int,
        x: int,
        y: int,
    ) -> CanvasTilePreview:
        resolved = self._resolve_asset_path(asset_url)
        if resolved is None or not resolved.source_path.exists() or not resolved.source_path.is_file():
            return CanvasTilePreview(url=None, status=None)

        source_size = self._get_image_size(resolved.source_path)
        if source_size is None:
            return CanvasTilePreview(url=None, status=None)

        source_width, source_height = source_size
        geometry = build_canvas_tile_geometry(
            source_width=source_width,
            source_height=source_height,
            z=z,
            x=x,
            y=y,
            tile_size=self.tile_size,
        )
        if geometry is None:
            return CanvasTilePreview(
                url=None,
                status=None,
                source_width=source_width,
                source_height=source_height,
                tile_size=self.tile_size,
            )

        target_path = self._build_tile_target_path(
            resolved.source_path,
            z=z,
            x=x,
            y=y,
            tile_size=self.tile_size,
        )
        base = {
            "target_path": target_path,
            "tile_size": self.tile_size,
            "source_width": source_width,
            "source_height": source_height,
            "level_width": geometry.level_width,
            "level_height": geometry.level_height,
            "columns": geometry.columns,
            "rows": geometry.rows,
        }
        if self._is_preview_fresh(source_path=resolved.source_path, target_path=target_path):
            return CanvasTilePreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                **base,
            )

        result = await self._submit_tile_generation(
            task_key=f"project:{project_id}:tile:{z}:{x}:{y}:{self._build_resource_key(resolved.source_path)}",
            source_path=resolved.source_path,
            target_path=target_path,
            z=z,
            x=x,
            y=y,
            tile_size=self.tile_size,
            quality=self.tile_quality,
            log_subject=f"canvas tile project {project_id}",
        )
        if result is None:
            return CanvasTilePreview(url=None, status=None, **base)

        status = str(result.get("status") or "")
        if status == "ready":
            return CanvasTilePreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                **base,
            )
        if status == "pending":
            return CanvasTilePreview(url=None, status="pending", **base)
        if status == "queued":
            return CanvasTilePreview(url=None, status="missing", **base)
        return CanvasTilePreview(url=None, status=None, **base)

    async def get_canvas_preview(
        self,
        *,
        project_id: int,
        user_id: int | None = None,
        asset_url: str,
        width: int,
    ) -> AssetListPreview:
        if width not in self.canvas_widths:
            return AssetListPreview(url=None, status=None)

        resolved = self._resolve_asset_path(asset_url)
        if resolved is None or not resolved.source_path.exists() or not resolved.source_path.is_file():
            return AssetListPreview(url=None, status=None)

        target_path = self._build_target_path(resolved.source_path, purpose="canvas", width=width)
        if self._is_preview_fresh(source_path=resolved.source_path, target_path=target_path):
            return AssetListPreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                target_path=target_path,
            )

        result = await self._submit_preview_generation(
            task_key=f"project:{project_id}:canvas:{width}:{self._build_resource_key(resolved.source_path)}",
            source_path=resolved.source_path,
            target_path=target_path,
            max_width=width,
            quality=self.canvas_quality,
            realtime={},
            log_subject=f"canvas preview project {project_id}",
        )
        if result is None:
            return AssetListPreview(url=None, status=None, target_path=target_path)

        status = str(result.get("status") or "")
        if status == "ready":
            return AssetListPreview(
                url=self._build_versioned_target_url(target_path=target_path, resolved=resolved),
                status="ready",
                target_path=target_path,
            )
        if status == "pending":
            return AssetListPreview(url=None, status="pending", target_path=target_path)
        if status == "queued":
            return AssetListPreview(url=None, status="missing", target_path=target_path)
        return AssetListPreview(url=None, status=None, target_path=target_path)

    async def _submit_preview_generation(
        self,
        *,
        task_key: str,
        source_path: Path,
        target_path: Path,
        max_width: int,
        quality: int,
        realtime: dict,
        log_subject: str,
    ) -> dict | None:
        try:
            return await self.worker.submit_generate_preview(
                task_key=task_key,
                source_path=str(source_path),
                target_path=str(target_path),
                max_width=max_width,
                quality=quality,
                realtime=realtime,
            )
        except Exception:
            logger.exception("Failed to submit asset preview generation task for %s", log_subject)
            return None

    async def _submit_tile_generation(
        self,
        *,
        task_key: str,
        source_path: Path,
        target_path: Path,
        z: int,
        x: int,
        y: int,
        tile_size: int,
        quality: int,
        log_subject: str,
    ) -> dict | None:
        try:
            return await self.worker.submit_generate_tile(
                task_key=task_key,
                source_path=str(source_path),
                target_path=str(target_path),
                z=z,
                x=x,
                y=y,
                tile_size=tile_size,
                quality=quality,
                realtime={},
            )
        except Exception:
            logger.exception("Failed to submit asset tile generation task for %s", log_subject)
            return None

    @staticmethod
    async def _publish_preview_updated(
        *,
        asset_id: int | str,
        project_id: int | None,
        user_id: int | None,
        version: str,
    ) -> None:
        resource = RealtimeResource(type="asset", id=str(asset_id), version=version)
        if user_id is not None:
            await publish_notification(
                "asset.preview.updated",
                scope=RealtimeScope(user_id=user_id),
                resource=resource,
                reason="preview_ready",
                worker="asset-preview",
            )
        if project_id is not None:
            await publish_notification(
                "asset.preview.updated",
                scope=RealtimeScope(project_id=project_id),
                resource=resource,
                reason="preview_ready",
                worker="asset-preview",
            )

    def _resolve_asset_path(self, asset_url: str) -> _ResolvedAssetPath | None:
        parsed = urlsplit(asset_url)
        path = unquote(parsed.path or "")

        roots = (
            (f"{API_V1_STR}/uploads/generated/", self.generated_root.resolve()),
            (f"{API_V1_STR}/uploads/canvas/", self.canvas_root.resolve()),
            (
                f"{API_V1_STR}/uploads/reference-gallery/",
                self.reference_gallery_root.resolve(),
            ),
        )

        for prefix, root in roots:
            if not path.startswith(prefix):
                continue

            raw_relative = path.removeprefix(prefix)
            relative = PurePosixPath(raw_relative)
            if relative.is_absolute() or ".." in relative.parts or not relative.name:
                return None

            candidate = (root / Path(*relative.parts)).resolve()
            if candidate != root and root not in candidate.parents:
                return None

            return _ResolvedAssetPath(root=root, source_path=candidate, url_prefix=prefix)

        return None

    @staticmethod
    def _build_target_path(source_path: Path, *, purpose: str, width: int) -> Path:
        return source_path.with_name(f"{source_path.stem}__{purpose}_{width}.webp")

    @staticmethod
    def _build_tile_target_path(source_path: Path, *, z: int, x: int, y: int, tile_size: int) -> Path:
        return source_path.with_name(f"{source_path.stem}__tile_{tile_size}_{z}_{x}_{y}.webp")

    def _build_target_url(self, *, target_path: Path, resolved: _ResolvedAssetPath) -> str:
        return f"{resolved.url_prefix}{target_path.relative_to(resolved.root).as_posix()}"

    def _build_versioned_target_url(self, *, target_path: Path, resolved: _ResolvedAssetPath) -> str:
        base_url = self._build_target_url(target_path=target_path, resolved=resolved)
        version = target_path.stat().st_mtime_ns
        return f"{base_url}?v={version}"

    @staticmethod
    def _is_preview_fresh(*, source_path: Path, target_path: Path) -> bool:
        if not target_path.exists() or not target_path.is_file():
            return False
        return target_path.stat().st_mtime >= source_path.stat().st_mtime

    @staticmethod
    def _build_guard_version(*, source_path: Path) -> str:
        stat = source_path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"

    @staticmethod
    def _build_resource_key(source_path: Path) -> str:
        return hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()

    @staticmethod
    def _get_image_size(source_path: Path) -> tuple[int, int] | None:
        try:
            import pyvips

            image = pyvips.Image.new_from_file(str(source_path), access="sequential")
            return int(image.width), int(image.height)
        except Exception:
            logger.exception("Failed to read image size for canvas tile source")
            return None


asset_preview_service = AssetPreviewService()
