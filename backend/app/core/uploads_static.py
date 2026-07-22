from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Any

from fastapi.staticfiles import StaticFiles

from app.services.asset_preview_contract import get_canvas_preview_suffixes


IMMUTABLE_PREVIEW_SUFFIXES = (
    "__list_320.webp",
    *get_canvas_preview_suffixes(),
)
LIST_PREVIEW_CACHE_CONTROL = "public, max-age=31536000, immutable"


class UploadsStaticFiles(StaticFiles):
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: dict[str, Any],
        status_code: int = 200,
    ):
        response = super().file_response(full_path, stat_result, scope, status_code)
        if self._is_immutable_preview_request(scope.get("path", "")):
            response.headers["Cache-Control"] = LIST_PREVIEW_CACHE_CONTROL
        return response

    @staticmethod
    def _is_immutable_preview_request(request_path: str) -> bool:
        path = PurePosixPath(request_path or "")
        return path.name.endswith(".webp") and (
            any(path.name.endswith(suffix) for suffix in IMMUTABLE_PREVIEW_SUFFIXES)
            or "__tile_" in path.name
        )
