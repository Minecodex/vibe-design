from __future__ import annotations

import asyncio

import pytest

from app.services.agent_harness.agent_resources.gpu import OWNER_AGENT, OWNER_MEDIA, acquire_gpu_guard
from app.services.agent_harness.agent_resources import gpu


@pytest.mark.asyncio
async def test_gpu_guard_serializes_agent_and_media_across_process_domains(monkeypatch):
    monkeypatch.setattr(gpu, "GPU_LEASE_SECONDS", 30)
    monkeypatch.setattr(gpu, "GPU_ACQUIRE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(gpu, "GPU_ACQUIRE_TIMEOUT_SECONDS", 0.02)

    async with acquire_gpu_guard(owner_domain=OWNER_AGENT, holder_id="agent-holder"):
        with pytest.raises(TimeoutError):
            async with acquire_gpu_guard(owner_domain=OWNER_MEDIA, holder_id="media-holder"):
                pass

    async with acquire_gpu_guard(owner_domain=OWNER_MEDIA, holder_id="media-holder") as lease:
        assert lease is not None
        assert lease.owner_domain == OWNER_MEDIA


@pytest.mark.asyncio
async def test_gpu_guard_aborts_holder_when_lease_renewal_is_lost(monkeypatch):
    monkeypatch.setattr(gpu, "_lease_seconds", lambda: 1)
    monkeypatch.setattr(gpu, "_gpu_slot_count", lambda: 1)
    monkeypatch.setattr(
        gpu,
        "_try_acquire_gpu_lease",
        lambda **_kwargs: gpu.GpuLeaseHandle(
            holder_id="agent-holder",
            owner_domain=OWNER_AGENT,
            slot_index=0,
            lease_seconds=1,
        ),
    )
    monkeypatch.setattr(gpu, "_renew_gpu_lease", lambda _handle: False)
    monkeypatch.setattr(gpu, "_release_gpu_lease", lambda _handle: None)

    with pytest.raises(gpu.GpuLeaseLostError):
        async with gpu.acquire_gpu_guard(owner_domain=OWNER_AGENT, holder_id="agent-holder"):
            await asyncio.sleep(2)
