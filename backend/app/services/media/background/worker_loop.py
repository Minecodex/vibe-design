from __future__ import annotations

import asyncio

from app.services.asset_thumbnail_worker import asset_thumbnail_worker


class AssetThumbnailBackgroundWorkerLoop:
    async def run(self) -> None:
        asset_thumbnail_worker.start(config={"max_width": 320, "quality": 75}, session_ttl=24 * 60 * 60)
        try:
            await asyncio.Event().wait()
        finally:
            asset_thumbnail_worker.shutdown()
