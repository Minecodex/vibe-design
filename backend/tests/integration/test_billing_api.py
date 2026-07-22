import uuid
from contextlib import asynccontextmanager

import pytest

from app.core.config import settings
from app.models.billing import UsageLog


@pytest.fixture
async def billing_auth_client(client, db_session):
    from app.core.security import create_access_token, get_password_hash
    from app.models.user import User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"billing-{suffix}@example.com",
        username=f"billinguser-{suffix}",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return client, user.id


@pytest.mark.asyncio
async def test_redemption_endpoints_are_not_registered(billing_auth_client):
    auth_client, _user_id = billing_auth_client

    list_response = await auth_client.get("/api/v1/billing/redemptions")
    redeem_response = await auth_client.post(
        "/api/v1/billing/redeem",
        json={"code": "retired"},
    )

    assert list_response.status_code == 404
    assert redeem_response.status_code == 404


@pytest.mark.asyncio
async def test_balance_endpoint_returns_provider_balance_in_sync_mode(
    billing_auth_client,
    db_session,
    monkeypatch,
):
    auth_client, user_id = billing_auth_client
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")

    from app.models.user_apimart_credential import UserApimartCredential

    db_session.add(
        UserApimartCredential(
            user_id=user_id,
            api_key="sk-api-balance",
            status="active",
            is_current=True,
            created_by_user_id=user_id,
        )
    )
    await db_session.commit()

    async def fake_provider_balance(api_key):
        assert api_key == "sk-api-balance"
        return 1234

    from app.services import billing_service

    monkeypatch.setattr(billing_service, "is_provider_balance_sync_enabled", lambda: True)
    monkeypatch.setattr(
        billing_service.provider_balance_sync_service,
        "get_balance_cents",
        fake_provider_balance,
    )

    response = await auth_client.get("/api/v1/billing/balance")

    assert response.status_code == 200
    assert response.json()["balance_cents"] == 1234


@pytest.mark.asyncio
async def test_balance_endpoint_returns_zero_after_apimart_key_is_revoked(
    billing_auth_client,
    db_session,
):
    auth_client, user_id = billing_auth_client
    from app.models.user_apimart_credential import UserApimartCredential

    credential = UserApimartCredential(
        user_id=user_id,
        api_key="sk-api-revoked-balance",
        status="active",
        is_current=True,
        created_by_user_id=user_id,
    )
    db_session.add(credential)
    await db_session.commit()
    from app.services.user_apimart_key_service import UserApimartKeyService

    await UserApimartKeyService(db_session).revoke_key(user_id)

    response = await auth_client.get("/api/v1/billing/balance")

    assert response.status_code == 200
    assert response.json() == {"balance_cents": 0}


@pytest.mark.asyncio
async def test_balance_endpoint_ignores_local_balance_and_uses_apimart_key(
    billing_auth_client,
    db_session,
    monkeypatch,
):
    auth_client, user_id = billing_auth_client
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    monkeypatch.setattr(settings, "PROVIDER_BALANCE_SYNC_ENABLED", False, raising=False)

    from app.models.user import User

    user = await db_session.get(User, user_id)
    user.balance_cents = 4321

    from app.models.user_apimart_credential import UserApimartCredential

    db_session.add(
        UserApimartCredential(
            user_id=user_id,
            api_key="sk-api-only-mode",
            status="active",
            is_current=True,
            created_by_user_id=user_id,
        )
    )
    await db_session.commit()

    async def fake_provider_balance(api_key):
        assert api_key == "sk-api-only-mode"
        return 2468

    from app.services import billing_service

    monkeypatch.setattr(
        billing_service.provider_balance_sync_service,
        "get_balance_cents",
        fake_provider_balance,
    )

    response = await auth_client.get("/api/v1/billing/balance")

    assert response.status_code == 200
    assert response.json()["balance_cents"] == 2468


@pytest.mark.asyncio
async def test_usage_list_hides_child_logs_by_default(billing_auth_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    auth_client, user_id = billing_auth_client

    parent = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent",
        model_label="agent",
        task_type="agent",
        amount_cents=9,
        amount_cents_original=9,
        billing_label="billing.labels.agent_call",
        status="success",
        params={"agent_run_id": "run-parent"},
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    child = UsageLog(
        user_id=user_id,
        parent_id=parent.id,
        task_id=None,
        model_name="claude-opus-4-8",
        model_label="Opus 4.8",
        task_type="multimodal",
        amount_cents=9,
        amount_cents_original=9,
        billing_label="billing.labels.multimodal_call",
        status="success",
        params={"input_tokens": 1000, "output_tokens": 2000},
    )
    db_session.add(child)
    await db_session.commit()

    response = await auth_client.get("/api/v1/billing/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [parent.id]
    assert payload["items"][0]["parent_id"] is None
    assert payload["items"][0]["billing_label"] == "billing.labels.agent_call"
    assert "params" not in payload["items"][0]


@pytest.mark.asyncio
async def test_usage_list_supports_filtering_by_billing_label(billing_auth_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    auth_client, user_id = billing_auth_client

    smart_designer_log = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent_harness",
        model_label="Agent Harness",
        task_type="agent",
        amount_cents=9,
        amount_cents_original=9,
        billing_label="billing.labels.smart_designer",
        status="success",
        params={"agent_run_id": "run-smart-designer"},
    )
    web_generate_log = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent_harness",
        model_label="Agent Harness",
        task_type="agent",
        amount_cents=11,
        amount_cents_original=11,
        billing_label="billing.labels.web_generate",
        status="success",
        params={"agent_run_id": "run-web-generate"},
    )
    db_session.add_all([smart_designer_log, web_generate_log])
    await db_session.commit()
    await db_session.refresh(smart_designer_log)

    response = await auth_client.get("/api/v1/billing/usage", params={"billing_label": "billing.labels.smart_designer"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [smart_designer_log.id]
    assert payload["items"][0]["billing_label"] == "billing.labels.smart_designer"
    assert payload["items"][0]["task_type"] == "agent"


@pytest.mark.asyncio
async def test_usage_children_endpoint_returns_only_selected_parent_children(billing_auth_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    auth_client, user_id = billing_auth_client

    first_parent = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent",
        model_label="agent",
        task_type="agent",
        amount_cents=12,
        amount_cents_original=12,
        billing_label="billing.labels.agent_call",
        status="pending",
        params={"agent_run_id": "run-a"},
    )
    second_parent = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent",
        model_label="agent",
        task_type="agent",
        amount_cents=5,
        amount_cents_original=5,
        billing_label="billing.labels.agent_call",
        status="success",
        params={"agent_run_id": "run-b"},
    )
    db_session.add_all([first_parent, second_parent])
    await db_session.commit()
    await db_session.refresh(first_parent)
    await db_session.refresh(second_parent)

    expected_child = UsageLog(
        user_id=user_id,
        parent_id=first_parent.id,
        task_id=None,
        model_name="claude-opus-4-8",
        model_label="Opus 4.8",
        task_type="multimodal",
        amount_cents=4,
        amount_cents_original=4,
        billing_label="billing.labels.multimodal_call",
        status="success",
        params={"input_tokens": 1000, "output_tokens": 2000},
    )
    another_child = UsageLog(
        user_id=user_id,
        parent_id=second_parent.id,
        task_id=None,
        model_name="claude-opus-4-8",
        model_label="Opus 4.8",
        task_type="multimodal",
        amount_cents=5,
        amount_cents_original=5,
        billing_label="billing.labels.multimodal_call",
        status="success",
        params={"input_tokens": 1500, "output_tokens": 2500},
    )
    db_session.add_all([expected_child, another_child])
    await db_session.commit()
    await db_session.refresh(expected_child)

    response = await auth_client.get(f"/api/v1/billing/usage/{first_parent.id}/children")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [expected_child.id]
    assert payload["items"][0]["parent_id"] == first_parent.id
    assert payload["items"][0]["billing_label"] == "billing.labels.multimodal_call"
    assert payload["items"][0]["params"] == {"input_tokens": 1000, "output_tokens": 2000}


@pytest.mark.asyncio
async def test_usage_summary_endpoint_returns_live_harness_summary(billing_auth_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    auth_client, user_id = billing_auth_client

    parent = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent_harness",
        model_label="Agent Harness",
        task_type="agent",
        amount_cents=18,
        amount_cents_original=18,
        billing_label="billing.labels.web_generate",
        status="pending",
        params={
            "engine": "agent_harness",
            "conversation_id": "conv_live_1",
            "agent_run_id": "run_live_1",
            "billing_summary": {
                "mode": "web",
                "mode_label": "网页生成",
                "multimodal_calls": 2,
                "image_analysis_calls": 1,
                "image_generation_calls": 0,
                "video_generation_calls": 0,
                "multimodal_models": ["gpt-4.1"],
                "image_analysis_models": ["gpt-4.1"],
                "image_models": [],
                "video_models": [],
                "multimodal_model_stats": [],
                "image_analysis_model_stats": [],
                "image_model_stats": [],
                "video_model_stats": [],
                "total_elapsed_ms": 2300,
            },
        },
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    response = await auth_client.get(f"/api/v1/billing/usage/{parent.id}/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == parent.id
    assert payload["engine"] == "agent_harness"
    assert payload["conversation_id"] == "conv_live_1"
    assert payload["agent_run_id"] == "run_live_1"
    assert payload["billing_summary"]["multimodal_calls"] == 2
    assert payload["billing_summary"]["total_elapsed_ms"] == 2300


@pytest.mark.asyncio
async def test_harness_billing_chain_is_visible_in_billing_summary_api(
    billing_auth_client,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    monkeypatch.setattr(settings, "HARNESS_WORKSPACE_ROOT", str(tmp_path))
    auth_client, user_id = billing_auth_client

    from types import SimpleNamespace

    from app.services.agent_harness.core.context import create_context
    from app.services.agent_harness.runtime.execution_support import billing_controller
    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
    )

    conversation = create_conversation(
        user_id,
        title="Harness billing chain",
        artifact_mode="slides",
        skill_id="pptx",
        model_preferences={"multimodal_model": "glm-5.1"},
    )
    engine = SimpleNamespace(user_id=user_id, current_parent_usage_log_id=None)
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation["id"],
        run_id="run-billing-chain",
        conversation=conversation,
    )

    @asynccontextmanager
    async def _db_session_factory():
        yield db_session

    async def _charge(_user_id, **_kwargs):
        return 3

    monkeypatch.setattr(billing_controller, "get_db_session_factory", lambda: _db_session_factory)
    monkeypatch.setattr(billing_controller, "charge_harness_amount", _charge)

    for kind in ("selection_resolver", "quick_brief_schema", "design_system_selection"):
        recorded = await billing_controller.record_preflight_model_billing(
            engine,
            conversation=conversation,
            ctx=ctx,
            model_name="glm-5.1",
            usage={
                "input_tokens": 100,
                "output_tokens": 20,
                "request_id": f"req-{kind}",
                "oneapi_request_id": f"oneapi-{kind}",
            },
            elapsed_ms=100,
            kind=kind,
        )
        assert recorded is True

    for kind in (None, "final_summary"):
        usage = {
            "input_tokens": 120,
            "output_tokens": 30,
            "request_id": f"req-{kind or 'main'}",
            "oneapi_request_id": f"oneapi-{kind or 'main'}",
        }
        if kind == "final_summary":
            usage.update(
                {
                    "cached_tokens": 64,
                    "cache_read_tokens": 32,
                    "cache_creation_tokens": 16,
                }
            )
        recorded = await billing_controller.record_model_usage_billing(
            user_id=user_id,
            ctx=ctx,
            model_name="glm-5.1",
            usage=usage,
            elapsed_ms=200,
            kind=kind,
        )
        assert recorded is True

    await billing_controller.update_parent_usage_log(
        engine,
        conversation=conversation,
        ctx=ctx,
        status="success",
    )

    usage_list = await auth_client.get("/api/v1/billing/usage")
    assert usage_list.status_code == 200
    list_payload = usage_list.json()
    parent_id = ctx.parent_usage_log_id
    assert parent_id is not None
    matching_items = [item for item in list_payload["items"] if item["id"] == parent_id]
    assert len(matching_items) == 1
    assert matching_items[0]["amount_cents"] == 0

    summary_response = await auth_client.get(f"/api/v1/billing/usage/{parent_id}/summary")
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["billing_summary"]["mode"] == "slides"
    assert summary_payload["billing_summary"]["multimodal_calls"] == 5
    assert summary_payload["billing_summary"]["multimodal_model_stats"] == [
        {
            "model_name": "glm-5.1",
            "model_label": "GLM 5.1",
            "calls": 5,
            "success_calls": 5,
            "failed_calls": 0,
        }
    ]

    children_response = await auth_client.get(f"/api/v1/billing/usage/{parent_id}/children")
    assert children_response.status_code == 200
    children_payload = children_response.json()
    assert children_payload["total"] == 5
    assert [item["parent_id"] for item in children_payload["items"]] == [parent_id] * 5
    assert {item["task_type"] for item in children_payload["items"]} == {"multimodal"}
    assert {item["params"]["kind"] for item in children_payload["items"]} == {
        "selection_resolver",
        "quick_brief_schema",
        "design_system_selection",
        "agent_llm",
        "final_summary",
    }
    assert {item["params"]["request_id"] for item in children_payload["items"]} == {
        "req-selection_resolver",
        "req-quick_brief_schema",
        "req-design_system_selection",
        "req-main",
        "req-final_summary",
    }
    assert {item["params"]["oneapi_request_id"] for item in children_payload["items"]} == {
        "oneapi-selection_resolver",
        "oneapi-quick_brief_schema",
        "oneapi-design_system_selection",
        "oneapi-main",
        "oneapi-final_summary",
    }
    final_summary_child = next(item for item in children_payload["items"] if item["params"]["kind"] == "final_summary")
    assert final_summary_child["params"]["cached_tokens"] == 64
    assert final_summary_child["params"]["cache_read_tokens"] == 32
    assert final_summary_child["params"]["cache_creation_tokens"] == 16


@pytest.mark.asyncio
async def test_usage_children_endpoint_allows_nested_subagent_children(billing_auth_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    auth_client, user_id = billing_auth_client

    parent = UsageLog(
        user_id=user_id,
        task_id=None,
        model_name="agent",
        model_label="agent",
        task_type="agent",
        amount_cents=12,
        amount_cents_original=12,
        billing_label="billing.labels.agent_call",
        status="success",
        params={"agent_run_id": "run-root"},
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    subagent = UsageLog(
        user_id=user_id,
        parent_id=parent.id,
        task_id=None,
        model_name="subagent",
        model_label="Subagent",
        task_type="agent",
        amount_cents=8,
        amount_cents_original=8,
        billing_label="billing.labels.agent_call",
        status="success",
        params={
            "kind": "subagent",
            "agent_run_id": "sub-run-1",
            "subagent_task_id": "subagent-1",
            "subagent_label": "南洋休闲区效果图",
        },
    )
    db_session.add(subagent)
    await db_session.commit()
    await db_session.refresh(subagent)

    nested_tool = UsageLog(
        user_id=user_id,
        parent_id=subagent.id,
        task_id=None,
        model_name="claude-opus-4-8",
        model_label="Opus 4.8",
        task_type="multimodal",
        amount_cents=4,
        amount_cents_original=4,
        billing_label="billing.labels.multimodal_call",
        status="success",
        params={
            "kind": "agent_llm",
            "input_tokens": 123,
            "output_tokens": 456,
            "subagent_task_id": "subagent-1",
            "subagent_label": "南洋休闲区效果图",
        },
    )
    db_session.add(nested_tool)
    await db_session.commit()
    await db_session.refresh(nested_tool)

    response = await auth_client.get(f"/api/v1/billing/usage/{subagent.id}/children")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [nested_tool.id]
    assert payload["items"][0]["parent_id"] == subagent.id
    assert payload["items"][0]["kind"] == "agent_llm"
    assert payload["items"][0]["subagent_label"] == "南洋休闲区效果图"



