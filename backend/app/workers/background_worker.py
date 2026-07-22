from __future__ import annotations

import asyncio
import logging
import signal

from app.core.logging import setup_logging
from app.services.billing.background.worker_loop import BillingBackgroundWorkerLoop
from app.services.generation.background.worker_loop import GenerationBackgroundWorkerLoop
from app.services.media.background.worker_loop import AssetThumbnailBackgroundWorkerLoop
from app.workers.runtime_bootstrap import refresh_license_runtime

logger = logging.getLogger(__name__)


async def _main() -> None:
    setup_logging()
    await refresh_license_runtime()
    stop = asyncio.Event()

    def _stop() -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    tasks = [
        asyncio.create_task(GenerationBackgroundWorkerLoop().run(), name="generation-background-loop"),
        asyncio.create_task(BillingBackgroundWorkerLoop().run(), name="billing-background-loop"),
        asyncio.create_task(AssetThumbnailBackgroundWorkerLoop().run(), name="asset-thumbnail-background-loop"),
    ]
    stop_task = asyncio.create_task(stop.wait(), name="background-worker-stop")
    try:
        done, _pending = await asyncio.wait(
            {stop_task, *tasks},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            return
        for task in tasks:
            if task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
                raise RuntimeError(f"{task.get_name()} stopped unexpectedly")
    finally:
        stop_task.cancel()
        for task in [*tasks, stop_task]:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, stop_task, return_exceptions=True)
        logger.info("background-worker stopped")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
