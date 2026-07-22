from __future__ import annotations

import asyncio
import logging
import signal

from app.core.logging import setup_logging
from app.services.agent_harness.agent_context.projection_worker import AgentContextWorkerLoop
from app.services.agent_harness.workflow.worker_loop import WorkflowStepWorkerLoop
from app.services.agent_harness.catalog import (
    AgentCatalogUnavailableError,
    wait_agent_catalog_ready,
)
from app.workers.runtime_bootstrap import refresh_license_runtime

logger = logging.getLogger(__name__)

AGENT_CATALOG_RETRY_SLEEP_SECONDS = 2.0


async def _main() -> None:
    setup_logging()
    from app.core.asyncio_diagnostics import enable_asyncio_diagnostics, event_loop_lag_probe

    enable_asyncio_diagnostics(component="agent-worker")
    await refresh_license_runtime()
    await _wait_agent_catalog_ready_for_worker()
    run_loop = WorkflowStepWorkerLoop()
    context_loop = AgentContextWorkerLoop()
    stop = asyncio.Event()

    def _stop() -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    run_task = asyncio.create_task(run_loop.run(), name="workflow-step-worker-loop")
    context_task = asyncio.create_task(
        context_loop.run(active_run_count=lambda: len(getattr(run_loop, "_tasks", ()))),
        name="agent-context-worker-loop",
    )
    stop_task = asyncio.create_task(stop.wait(), name="agent-worker-stop")
    lag_probe_task = asyncio.create_task(
        event_loop_lag_probe(component="agent-worker", stop_event=stop),
        name="agent-worker-lag-probe",
    )
    try:
        done, _pending = await asyncio.wait(
            {stop_task, run_task, context_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            return
        for task in (run_task, context_task):
            if task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
                raise RuntimeError(f"{task.get_name()} stopped unexpectedly")
    finally:
        stop_task.cancel()
        await run_loop.shutdown()
        await context_loop.shutdown()
        for task in (run_task, context_task, stop_task, lag_probe_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(run_task, context_task, stop_task, lag_probe_task, return_exceptions=True)
        from app.services.agent_harness.runtime.eventing import presentation_delta_queue
        try:
            await presentation_delta_queue.aclose(flush=True, timeout=5.0)
        except Exception:
            logger.info("Presentation delta queue shutdown failed", exc_info=True)
        from app.db.harness_session import shutdown_harness_db_executor
        shutdown_harness_db_executor()
        logger.info("agent-worker stopped")


async def _wait_agent_catalog_ready_for_worker() -> None:
    attempts = 0
    while True:
        try:
            await wait_agent_catalog_ready()
            if attempts:
                logger.info("agent catalog became ready after %s retry attempts", attempts)
            return
        except AgentCatalogUnavailableError as exc:
            attempts += 1
            logger.warning(
                "agent catalog not ready for worker startup; retrying "
                "(attempt=%s, error=%s)",
                attempts,
                exc,
            )
            await asyncio.sleep(max(float(AGENT_CATALOG_RETRY_SLEEP_SECONDS), 0.0))


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
