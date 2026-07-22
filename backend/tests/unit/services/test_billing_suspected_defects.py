"""Tests that PIN DOWN suspected billing defects (analysis only — not fixed yet).

Each test documents a concrete behaviour found while deep-reading the billing code.
- Characterization tests assert the *current* (suspect) behaviour and carry a DEFECT note
  describing why it is wrong; they pass today and will break when the behaviour is fixed.
- `xfail` tests assert the *desired* behaviour and currently fail, so they make the defect
  visible without turning the suite red. An unexpected pass (xpass) flags that it got fixed.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services.billing_service import BillingService


# ---------------------------------------------------------------------------
# Defect 1 — a "blocked" child silently vanishes from its parent usage log.
#
# finalize_apimart_generation_billing marks a child "blocked" when the provider
# already produced the asset but the user balance could not cover it
# (manual_review_required / insufficient_balance_after_provider_success).
# refresh_parent_usage_log only counts status=="success" toward the amount and only
# status=="pending" as "active". A "blocked" child is therefore neither billed nor
# keeps the parent open — the parent finalizes as a clean "success" and the blocked
# sub-charge disappears from the parent with no flag for the operator to act on.
# (Triggers in non-provider-sync deploys, where the blocked branch is reachable.)
# ---------------------------------------------------------------------------


def _parent():
    return SimpleNamespace(
        id=100,
        user_id=7,
        amount_cents=0,
        amount_cents_original=0,
        elapsed_ms=0,
        status="pending",
        params={"agent_started_at": "2026-03-25T00:00:00+00:00"},
        created_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 25, 0, 0, 0, tzinfo=UTC),
    )


def _child(*, log_id, status, amount_cents, amount_original):
    return SimpleNamespace(
        id=log_id,
        parent_id=100,
        amount_cents=amount_cents,
        amount_cents_original=amount_original,
        status=status,
        elapsed_ms=1000,
        updated_at=datetime(2026, 3, 25, 0, 0, 2, tzinfo=UTC),
    )


def _service_with_children(parent, children, captured):
    service = BillingService(db=object())

    class FakeUsageRepo:
        async def get(self, log_id):
            return parent

        async def get_children(self, parent_id):
            return children

        async def update(self, obj, data):
            captured["data"] = data
            return SimpleNamespace(parent_id=None, **data)

    service.usage_repo = FakeUsageRepo()
    return service


@pytest.mark.asyncio
async def test_blocked_child_is_currently_dropped_from_parent_total(monkeypatch):
    """CHARACTERIZATION: documents that a blocked child is excluded today."""
    parent = _parent()
    children = [
        _child(log_id=1, status="success", amount_cents=3, amount_original=3),
        _child(log_id=2, status="blocked", amount_cents=0, amount_original=7),
    ]
    captured: dict = {}
    service = _service_with_children(parent, children, captured)

    await service.refresh_parent_usage_log(log_id=100)

    # DEFECT: the 7-cent blocked sub-charge is invisible at the parent level and the
    # parent reports a clean success. Ideally the parent should surface that a child
    # needs manual review instead of finalizing silently.
    assert captured["data"]["amount_cents"] == 3
    assert captured["data"]["status"] == "success"


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="DEFECT: parent finalizes 'success' while a child is 'blocked' (needs review)",
    strict=False,
)
async def test_blocked_child_should_not_finalize_parent_as_clean_success(monkeypatch):
    """DESIRED: a blocked child should keep the parent from silently reporting success."""
    parent = _parent()
    children = [
        _child(log_id=1, status="success", amount_cents=3, amount_original=3),
        _child(log_id=2, status="blocked", amount_cents=0, amount_original=7),
    ]
    captured: dict = {}
    service = _service_with_children(parent, children, captured)

    await service.refresh_parent_usage_log(log_id=100)

    assert captured["data"]["status"] != "success"


# ---------------------------------------------------------------------------
# Defect 2 — refund_generation_usage_log_if_pending mutates the LOCAL user balance
# even under provider-balance-sync mode, and without the private-deploy admin remap.
#
# The canonical refund_balance()/deduct_balance() helpers (a) early-return in
# is_provider_balance_sync_enabled() mode and (b) remap to the admin user when
# DEPLOY_TYPE=="private". But refund_generation_usage_log_if_pending and
# refund_usage_log_by_id_once issue a raw `UPDATE users SET balance_cents=...` on the
# *request* user with neither guard. So a pending log carrying a non-zero
# amount_cents_original (e.g. created before sync was switched on) gets refunded to the
# local balance even though the rest of sync-mode accounting never touches it — and in
# private deploy it credits the wrong account relative to the original debit.
# ---------------------------------------------------------------------------


class _RecordingDB:
    def __init__(self):
        self.executed: list[str] = []

    async def execute(self, stmt):
        self.executed.append(str(stmt))
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_generation_refund_skips_local_balance_in_provider_sync_mode(monkeypatch):
    """FIXED (D2): under provider-balance-sync, no local `users.balance_cents` mutation."""
    monkeypatch.setattr(
        "app.services.billing_service.is_provider_balance_sync_enabled",
        lambda: True,
    )

    log = SimpleNamespace(
        id=1,
        task_id=5,
        status="pending",
        amount_cents=0,
        amount_cents_original=50,  # non-zero (e.g. created before sync was enabled)
        parent_id=None,
        billing_locked_until=None,
        billing_lock_token=None,
        billing_finalized_at=None,
    )

    class FakeUsageRepo:
        async def get_by_task_id(self, _task_id):
            return log

        async def get(self, _log_id):
            return log

    db = _RecordingDB()
    service = BillingService(db=db)
    service.usage_repo = FakeUsageRepo()

    await service.refund_generation_usage_log_if_pending(task_id=5, user_id=99)

    balance_mutations = [stmt for stmt in db.executed if "balance_cents" in stmt]
    assert balance_mutations == []


@pytest.mark.asyncio
async def test_effective_balance_user_id_remaps_to_admin_in_private_deploy(monkeypatch):
    """FIXED (D2): inline refund/finalize target the same pooled account as deduct_balance."""
    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "private")
    service = BillingService(db=object())
    service._admin_id = 1
    assert await service._effective_balance_user_id(99) == 1


@pytest.mark.asyncio
async def test_effective_balance_user_id_uses_request_user_in_public_deploy(monkeypatch):
    monkeypatch.setattr("app.services.billing_service.settings.DEPLOY_TYPE", "saas")
    service = BillingService(db=object())
    assert await service._effective_balance_user_id(99) == 99
