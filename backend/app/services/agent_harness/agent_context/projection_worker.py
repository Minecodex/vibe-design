from __future__ import annotations

import asyncio

from app.core.config import settings
from app.db.harness_session import run_harness_db
from app.services.agent_harness.runtime.context_projection_worker import process_context_projection_batch
from app.services.agent_harness.agent_coordination.context_wakeup_bus import wait_agent_context_wakeup


class AgentContextWorkerLoop:
    def __init__(self) -> None:
        self.poll_seconds = max(float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS", 5.0) or 5.0), 0.25)
        self.batch_size = max(int(getattr(settings, "HARNESS_AGENT_CONTEXT_CONCURRENCY", 1) or 1), 1)
        self._shutdown = asyncio.Event()

    async def run(self, *, active_run_count=None) -> None:
        # active_run_count kept in the signature for caller compatibility but
        # no longer used. Model context assembly is synchronous on the turn
        # path; the only remaining background responsibility here is
        # recall_sidecar refresh, which is final-consistent and safe to run
        # alongside active runs.
        del active_run_count
        while not self._shutdown.is_set():
            processed = await run_harness_db(process_context_projection_batch, batch_size=self.batch_size)
            if not processed:
                await wait_agent_context_wakeup(timeout_seconds=self.poll_seconds)

    async def shutdown(self) -> None:
        self._shutdown.set()
