from __future__ import annotations

import pytest

from app.services.agent_harness.workflow.contracts import BillingSpec, BlobSpec, MessageSpec, NotificationSpec, StepSpec, WorkspaceFileSpec
from app.services.agent_harness.workflow.gateway import (
    AgentRuntimeGateway,
    DirectDisplayMessageNotAllowed,
    SystemPublishStepCollision,
)
from app.services.agent_harness.workflow.runtime_preparation import create_workflow_context


@pytest.mark.asyncio
async def test_gateway_exposes_side_effect_contracts(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def fake_publish_runtime_notification(user_id: int, conversation_id: str) -> None:
        calls.append(("publish", (user_id, conversation_id)))

    def fake_promote_large_tool_result(user_id: int, conversation_id: str, **kwargs):
        calls.append(("blob", (user_id, conversation_id, kwargs)))
        return {"promoted": False, "content": kwargs["content"], "artifact": None}

    def fake_upsert_workspace_file(user_id: int, conversation_id: str, file: dict) -> None:
        calls.append(("file", (user_id, conversation_id, file)))

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.publish_runtime_notification",
        fake_publish_runtime_notification,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.promote_large_tool_result",
        fake_promote_large_tool_result,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.upsert_workspace_file",
        fake_upsert_workspace_file,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")

    await gateway.publish_notification(NotificationSpec(kind="runtime"))
    blob = await gateway.write_blob(BlobSpec(content="hello", tool_call_id="tool-1", tool_name="search"))
    await gateway.update_workspace_file(WorkspaceFileSpec(file={"external_id": "file-1", "name": "a.txt"}))

    assert blob["content"] == "hello"
    assert calls == [
        ("publish", (7, "gw-conv")),
        (
            "blob",
            (
                7,
                "gw-conv",
                {"tool_call_id": "tool-1", "tool_name": "search", "content": "hello"},
            ),
        ),
        ("file", (7, "gw-conv", {"external_id": "file-1", "name": "a.txt"})),
    ]


@pytest.mark.asyncio
async def test_gateway_billing_defaults_to_run_parent_usage_log(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_run_parent_usage_log_id_async(run_id: str) -> int:
        assert run_id == "run-1"
        return 123

    class _BillingService:
        def __init__(self, _db) -> None:
            pass

        async def create_usage_log(self, **kwargs):
            captured.update(kwargs)
            return type("UsageLog", (), {"id": 99, "status": kwargs.get("task_status")})()

    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_run_parent_usage_log_id_async",
        fake_get_run_parent_usage_log_id_async,
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.gateway.BillingService", _BillingService)
    monkeypatch.setattr("app.services.agent_harness.workflow.gateway.AsyncSessionLocal", lambda: _Session())

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    result = await gateway.record_billing(
        BillingSpec(
            billing_key="billing-key",
            model_name="model",
            task_type="agent_tool",
            amount_cents=5,
            task_status="completed",
        )
    )

    assert result == {"id": 99, "status": "completed"}
    assert captured["parent_id"] == 123
    assert captured["params"]["agent_run_id"] == "run-1"
    assert captured["params"]["workflow_step_id"] == "step-1"


def test_workflow_context_uses_run_parent_usage_log(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.get_run_parent_usage_log_id",
        lambda run_id: 456 if run_id == "run-context" else None,
    )

    ctx = create_workflow_context(
        user_id=7,
        conversation_id="conv-context",
        run_id="run-context",
        language="zh",
        conversation={
            "id": "conv-context",
            "runtime_profile": "canvas",
            "skill_id": "design_workflow",
            "artifact_mode": "web",
            "parent_usage_log_id": 111,
        },
    )

    assert ctx.parent_usage_log_id == 456
    assert ctx.skill_id == "design_workflow"


def test_workflow_context_backfills_run_parent_usage_log_from_conversation(monkeypatch):
    captured: dict[str, int] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.get_run_parent_usage_log_id",
        lambda _run_id: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.set_run_parent_usage_log_id",
        lambda run_id, parent_usage_log_id: captured.update({run_id: parent_usage_log_id}),
    )

    ctx = create_workflow_context(
        user_id=7,
        conversation_id="conv-context-fallback",
        run_id="run-context-fallback",
        language="zh",
        conversation={
            "id": "conv-context-fallback",
            "runtime_profile": "canvas",
            "parent_usage_log_id": 789,
        },
    )

    assert ctx.parent_usage_log_id == 789
    assert captured == {"run-context-fallback": 789}


@pytest.mark.asyncio
async def test_gateway_append_message_dedupes_via_indexed_lookup(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def fake_get_message_async(user_id: int, conversation_id: str, message_id: str):
        calls.append(("get", message_id))
        return {"id": message_id, "role": "assistant", "content": "existing"}

    async def fake_append_message_async(*_args, **_kwargs):
        calls.append(("append", None))
        raise AssertionError("append_message_async should be skipped when the message already exists")

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_message_async",
        fake_get_message_async,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.append_message_async",
        fake_append_message_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    result = await gateway.append_message(
        MessageSpec(role="assistant", content="x", idempotency_key="msg-1")
    )

    assert result["content"] == "existing"
    # Dedup goes through a single indexed lookup, never a full message load.
    assert [kind for kind, _ in calls] == ["get"]


@pytest.mark.asyncio
async def test_gateway_append_message_preserves_user_message_fields(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_message_async(_user_id: int, _conversation_id: str, _message_id: str):
        return None

    async def fake_append_message_async(user_id: int, conversation_id: str, message: dict):
        captured["user_id"] = user_id
        captured["conversation_id"] = conversation_id
        captured["message"] = message
        return message

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_message_async",
        fake_get_message_async,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.append_message_async",
        fake_append_message_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    result = await gateway.append_message(
        MessageSpec(
            role="user",
            content="hello",
            attachments=[{"type": "image", "url": "references/inputs/a.png"}],
            created_at="2026-06-04T00:00:00+00:00",
            idempotency_key="user-msg-1",
            metadata={"message_kind": "agent_context", "ui_visible": False, "references": [{"id": "ref-1"}]},
        )
    )

    assert result["id"] == "user-msg-1"
    assert result["attachments"] == [{"type": "image", "url": "references/inputs/a.png"}]
    assert result["created_at"] == "2026-06-04T00:00:00+00:00"
    assert result["metadata"] == {"message_kind": "agent_context", "ui_visible": False, "references": [{"id": "ref-1"}]}


@pytest.mark.asyncio
async def test_gateway_append_message_rejects_direct_user_visible_message(monkeypatch):
    async def fake_get_message_async(_user_id: int, _conversation_id: str, _message_id: str):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_message_async",
        fake_get_message_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    with pytest.raises(DirectDisplayMessageNotAllowed):
        await gateway.append_message(
            MessageSpec(
                role="assistant",
                content="hello",
                idempotency_key="display-msg-1",
                metadata={},
            )
        )


@pytest.mark.asyncio
async def test_gateway_get_latest_assistant_message_uses_indexed_lookup(monkeypatch):
    async def fake_get_latest_assistant_message_async(user_id: int, conversation_id: str):
        assert (user_id, conversation_id) == (7, "gw-conv")
        return {"id": "assistant-9", "role": "assistant", "content": "latest"}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_latest_assistant_message_async",
        fake_get_latest_assistant_message_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    latest = await gateway.get_latest_assistant_message()
    assert latest["content"] == "latest"


@pytest.mark.asyncio
async def test_gateway_updates_step_checkpoint(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_update_step_checkpoint_async(step_id: str, **kwargs):
        captured["step_id"] = step_id
        captured.update(kwargs)
        return {"step_id": step_id, "checkpoint": kwargs.get("patch")}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.update_step_checkpoint_async",
        fake_update_step_checkpoint_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    result = await gateway.update_step_checkpoint(
        claim_token="claim-token",
        patch={"stream": {"delta_index": 10}},
    )

    assert result == {"step_id": "step-1", "checkpoint": {"stream": {"delta_index": 10}}}
    assert captured == {
        "step_id": "step-1",
        "claim_token": "claim-token",
        "patch": {"stream": {"delta_index": 10}},
    }


@pytest.mark.asyncio
async def test_gateway_rejects_system_publish_idempotency_collision(monkeypatch):
    class _ExistingStep:
        input = {
            "tool_calls": [
                {"id": "call-existing", "name": "publish_output", "arguments": {}},
            ]
        }

    async def fake_enqueue_step_async(**_kwargs):
        return _ExistingStep()

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.enqueue_step_async",
        fake_enqueue_step_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")

    with pytest.raises(SystemPublishStepCollision):
        await gateway.enqueue_step(
            StepSpec(
                step_type="execute_tool",
                input={
                    "tool_calls": [
                        {"id": "system_publish:run-1", "name": "publish_output", "arguments": {}},
                    ]
                },
                idempotency_key="run:run-1:system-publish-output:execute",
            )
        )


@pytest.mark.asyncio
async def test_gateway_runtime_patch_preserves_snapshot_runtime_state(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_conversation_async(_user_id: int, _conversation_id: str):
        return {
            "id": "gw-conv",
            "runtime_snapshot": {
                "phase": "executing",
                "runtime_status": "running",
                "runtime_state": {
                    "artifact_manifest": {
                        "entry": "births.xlsx",
                        "kind": "spreadsheet",
                    },
                    "workspace_runtime_session": {
                        "active_entry": "births.xlsx",
                    },
                },
            },
            "runtime_state": {
                "artifact_manifest": {
                    "entry": "births.xlsx",
                    "kind": "spreadsheet",
                },
                "workspace_runtime_session": {
                    "active_entry": "births.xlsx",
                },
            },
        }

    async def fake_update_conversation_async(user_id: int, conversation_id: str, updates: dict):
        captured["user_id"] = user_id
        captured["conversation_id"] = conversation_id
        captured["updates"] = updates
        return updates

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_conversation_async",
        fake_get_conversation_async,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.update_conversation_async",
        fake_update_conversation_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    await gateway.update_runtime_snapshot(
        {"runtime_status": "running", "run_state": "rendering_context", "turn_status": "running"}
    )

    updates = captured["updates"]
    snapshot = updates["runtime_snapshot_json"]
    assert snapshot["run_state"] == "rendering_context"
    assert snapshot["runtime_state"]["artifact_manifest"]["entry"] == "births.xlsx"
    assert snapshot["runtime_state"]["workspace_runtime_session"]["active_entry"] == "births.xlsx"


@pytest.mark.asyncio
async def test_gateway_runtime_patch_wraps_runtime_state_fallback(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_conversation_async(_user_id: int, _conversation_id: str):
        return {
            "id": "gw-conv",
            "runtime_state": {
                "artifact_manifest": {
                    "entry": "births.xlsx",
                    "kind": "spreadsheet",
                },
            },
        }

    async def fake_update_conversation_async(_user_id: int, _conversation_id: str, updates: dict):
        captured["updates"] = updates
        return updates

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.get_conversation_async",
        fake_get_conversation_async,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.gateway.update_conversation_async",
        fake_update_conversation_async,
    )

    gateway = AgentRuntimeGateway(user_id=7, conversation_id="gw-conv", run_id="run-1", step_id="step-1")
    await gateway.update_runtime_snapshot({"runtime_status": "running"})

    snapshot = captured["updates"]["runtime_snapshot_json"]
    assert "artifact_manifest" not in snapshot
    assert snapshot["runtime_state"]["artifact_manifest"]["entry"] == "births.xlsx"
