from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class GenerationResultMaterializer:
    def __init__(
        self,
        *,
        download_file_to_local: Callable[..., Awaitable[str]],
        build_download_failure_error: Callable[[str, Exception], str],
    ) -> None:
        self.download_file_to_local = download_file_to_local
        self.build_download_failure_error = build_download_failure_error

    async def store_builtin_result_urls(self, task: Any, urls: list[str] | None) -> dict[str, Any]:
        ext = "mp4" if getattr(task, "task_type", None) in ("text2video", "image2video") else "png"
        stored_urls: list[str] = []
        for url in urls or []:
            try:
                task_params = getattr(task, "params", None) if isinstance(getattr(task, "params", None), dict) else {}
                target_url = task_params.get("planned_result_url") if not stored_urls else None
                if target_url:
                    stored_url = await self.download_file_to_local(url, ext, target_url=target_url)
                else:
                    stored_url = await self.download_file_to_local(url, ext)
                stored_urls.append(stored_url)
            except Exception as exc:
                logger.error("Failed to materialize generation result: %s", type(exc).__name__)
                return {
                    "status": "failed",
                    "error_message": self.build_download_failure_error(str(url), exc),
                }

        primary_url = stored_urls[0] if stored_urls else None
        update: dict[str, Any] = {"status": "completed", "result_url": primary_url, "progress": 100}
        if stored_urls:
            update["result_urls"] = stored_urls
        return update
