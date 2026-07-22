from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.services.agent_harness.runtime.context_projection_worker import process_context_projection_batch


logger = logging.getLogger(__name__)


async def run_context_projection_daemon() -> None:
    setup_logging()
    interval = max(0.25, float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS", 2.0) or 2.0))
    max_concurrency = max(1, int(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_MAX_CONCURRENCY", 1) or 1))
    batch_size = min(
        max(1, int(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_BATCH_SIZE", 1) or 1)),
        max_concurrency,
    )
    worker_id = "context-projection-daemon"
    while True:
        try:
            processed = await asyncio.to_thread(
                process_context_projection_batch,
                worker_id=worker_id,
                batch_size=batch_size,
            )
            if processed is None:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Context projection daemon iteration failed", exc_info=True)
            await asyncio.sleep(interval)


def main() -> None:
    asyncio.run(run_context_projection_daemon())


if __name__ == "__main__":
    main()
