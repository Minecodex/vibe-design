from __future__ import annotations

import asyncio

from app.services.provider_balance_sync import provider_balance_sync_worker


class BillingBackgroundWorkerLoop:
    async def run(self) -> None:
        provider_balance_sync_worker.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await provider_balance_sync_worker.shutdown()
