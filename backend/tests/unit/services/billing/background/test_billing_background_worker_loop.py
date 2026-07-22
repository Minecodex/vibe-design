from __future__ import annotations

import asyncio

import pytest

from app.services.billing.background import worker_loop as billing_loop_mod
from app.services.billing.background.worker_loop import BillingBackgroundWorkerLoop


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def start(self) -> None:
        self.events.append("start")

    async def shutdown(self) -> None:
        self.events.append("shutdown")


async def _run_loop_until_idle_then_cancel(loop: BillingBackgroundWorkerLoop) -> None:
    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_billing_loop_runs_only_apimart_balance_sync(monkeypatch):
    balance = _Recorder()
    monkeypatch.setattr(billing_loop_mod, "provider_balance_sync_worker", balance)

    await _run_loop_until_idle_then_cancel(BillingBackgroundWorkerLoop())

    assert balance.events == ["start", "shutdown"]


@pytest.mark.asyncio
async def test_billing_loop_propagates_balance_sync_start_failure(monkeypatch):
    class _ExplodingStart:
        def start(self) -> None:
            raise RuntimeError("balance sync init failed")

        async def shutdown(self) -> None:
            raise AssertionError("shutdown is not reached when start fails")

    monkeypatch.setattr(
        billing_loop_mod,
        "provider_balance_sync_worker",
        _ExplodingStart(),
    )

    with pytest.raises(RuntimeError, match="balance sync init failed"):
        await BillingBackgroundWorkerLoop().run()
