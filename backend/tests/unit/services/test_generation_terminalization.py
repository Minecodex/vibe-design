"""Unit tests for GenerationTerminalizationService side-effect isolation.

Regression guard for the "stuck run" bug: when billing/refund raises during terminal
finalization, the user-visible artifact event (canvas item -> failed/completed) must still
be published, otherwise the canvas item stays "generating" and the run hangs at "running".
"""

from types import SimpleNamespace

import pytest

from app.services.generation_terminalization import GenerationTerminalizationService


def _failed_apimart_task():
    return SimpleNamespace(
        id=501,
        user_id=7,
        status="failed",
        provider_code="builtin",
        builtin_provider_code="apimart",
        error_message="provider failed",
    )


@pytest.mark.asyncio
async def test_artifact_event_published_even_when_billing_raises():
    published: list[int] = []

    async def fake_publisher(task):
        published.append(task.id)

    class FailingBilling:
        def __init__(self, *_a, **_k):
            pass

        async def refund_generation_usage_log_if_pending(self, *_a, **_k):
            raise RuntimeError("refund blew up")

    service = GenerationTerminalizationService(
        db=object(),
        billing_service_factory=FailingBilling,
        artifact_publisher=fake_publisher,
    )

    finalized = await service.finalize_terminal_task(_failed_apimart_task(), user_id=7)

    # User-visible terminal event still landed despite the billing failure...
    assert published == [501]
    # ...and the call reports partial failure so the caller does NOT set the idempotency
    # flag, leaving startup recovery to retry the unfinished billing.
    assert finalized is False


@pytest.mark.asyncio
async def test_all_side_effects_succeed_reports_true():
    published: list[int] = []

    async def fake_publisher(task):
        published.append(task.id)

    class OkBilling:
        def __init__(self, *_a, **_k):
            pass

        async def refund_generation_usage_log_if_pending(self, *_a, **_k):
            return None

    service = GenerationTerminalizationService(
        db=object(),
        billing_service_factory=OkBilling,
        artifact_publisher=fake_publisher,
    )

    finalized = await service.finalize_terminal_task(_failed_apimart_task(), user_id=7)

    assert published == [501]
    assert finalized is True


@pytest.mark.asyncio
async def test_artifact_failure_does_not_block_billing():
    refunded: list[int] = []

    async def failing_publisher(task):
        raise RuntimeError("publish blew up")

    class TrackingBilling:
        def __init__(self, *_a, **_k):
            pass

        async def refund_generation_usage_log_if_pending(self, task_id, _user_id):
            refunded.append(task_id)

    service = GenerationTerminalizationService(
        db=object(),
        billing_service_factory=TrackingBilling,
        artifact_publisher=failing_publisher,
    )

    finalized = await service.finalize_terminal_task(_failed_apimart_task(), user_id=7)

    # Billing still settled even though the event publish failed; not fully finalized.
    assert refunded == [501]
    assert finalized is False
