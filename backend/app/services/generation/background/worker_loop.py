from __future__ import annotations

import asyncio

from app.services.background_scheduler_owner import background_scheduler_owner


class GenerationBackgroundWorkerLoop:
    async def run(self) -> None:
        background_scheduler_owner.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await background_scheduler_owner.shutdown()
