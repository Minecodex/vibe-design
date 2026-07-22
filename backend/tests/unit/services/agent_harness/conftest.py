import pytest

@pytest.fixture(autouse=True)
def _disable_usage_log_io(monkeypatch):
    async def _noop_create_parent_usage_log(self, *, conversation, ctx):
        if ctx.parent_usage_log_id is not None:
            self.current_parent_usage_log_id = ctx.parent_usage_log_id
            return
        self.current_parent_usage_log_id = None

    async def _noop_update_parent_usage_log(self, *, conversation, ctx, status):
        self.current_parent_usage_log_id = ctx.parent_usage_log_id
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.create_parent_usage_log",
        _noop_create_parent_usage_log,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.update_parent_usage_log",
        _noop_update_parent_usage_log,
    )


@pytest.fixture(autouse=True)
def _disable_harness_amount_charges(monkeypatch):
    async def _noop_charge_harness_amount(*_args, **_kwargs):
        return 0

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.charge_harness_amount",
        _noop_charge_harness_amount,
    )

