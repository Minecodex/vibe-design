from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import harness as harness_endpoint
from app.schemas.harness import ResolveHarnessSelectionRequest


@pytest.mark.asyncio
async def test_resolve_harness_selection_returns_structured_result(monkeypatch):
    user = SimpleNamespace(id=7)

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="saas-landing",
                confidence=0.92,
                reasoning_summary="Landing-page request benefits from the landing-page skill.",
                should_replace_current=True,
            ),
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    result = await harness_endpoint.resolve_harness_selection(
        data=ResolveHarnessSelectionRequest(
            artifact_mode="web",
            prompt="做一个设计公司的落地页",
            resolve_skill=True,
        ),
        user=user,
    )

    assert result.skill is not None
    assert result.skill.id == "saas-landing"
    assert result.skill.should_replace_current is True


@pytest.mark.asyncio
async def test_resolve_harness_selection_records_preflight_billing_when_conversation_is_known(monkeypatch):
    user = SimpleNamespace(id=11)
    calls: list[dict] = []
    conversation = {
        "id": "conv-bill-selection",
        "artifact_mode": "spreadsheet",
        "skill_id": None,
        "model_preferences": {"multimodal_model": "glm-5.1"},
    }

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="xlsx",
                confidence=0.88,
                reasoning_summary="Spreadsheet request benefits from spreadsheet mode.",
                should_replace_current=True,
            ),
            design_system_recommendations=[],
            preflight_model_calls=[
                SimpleNamespace(
                    model_name="glm-5.1",
                    usage={"input_tokens": 100, "output_tokens": 20},
                    elapsed_ms=234,
                    kind="selection_resolver",
                ),
            ],
        )

    async def _record_preflight_model_billing(engine, **kwargs):
        calls.append({"engine_user_id": engine.user_id, **kwargs})
        kwargs["ctx"].parent_usage_log_id = 12345
        return True

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.record_preflight_model_billing",
        _record_preflight_model_billing,
    )
    persisted: list[dict] = []
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.preflight_lifecycle_service.persist_skill_resolution",
        lambda **kwargs: persisted.append(kwargs),
    )

    result = await harness_endpoint.resolve_harness_selection(
        data=ResolveHarnessSelectionRequest(
            conversation_id="conv-bill-selection",
            artifact_mode="spreadsheet",
            prompt="做一个销售表格",
            resolve_skill=True,
        ),
        user=user,
    )

    assert result.skill is not None
    assert result.skill.id == "xlsx"
    assert calls
    assert calls[0]["engine_user_id"] == 11
    assert calls[0]["conversation"]["artifact_mode"] == "spreadsheet"
    assert calls[0]["model_name"] == "glm-5.1"
    assert calls[0]["usage"] == {"input_tokens": 100, "output_tokens": 20}
    assert calls[0]["kind"] == "selection_resolver"
    assert len(calls) == 1
    assert persisted
    assert persisted[0]["next_skill_id"] == "xlsx"


@pytest.mark.asyncio
async def test_resolve_harness_selection_does_not_record_billing_without_conversation(monkeypatch):
    user = SimpleNamespace(id=12)
    calls: list[dict] = []

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=None,
            design_system_recommendations=[],
            preflight_model_calls=[
                SimpleNamespace(
                    model_name="glm-5.1",
                    usage={"input_tokens": 100, "output_tokens": 20},
                    elapsed_ms=234,
                    kind="selection_resolver",
                ),
            ],
        )

    async def _record_preflight_model_billing(engine, **kwargs):
        calls.append({"engine_user_id": engine.user_id, **kwargs})
        return True

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.record_preflight_model_billing",
        _record_preflight_model_billing,
    )

    result = await harness_endpoint.resolve_harness_selection(
        data=ResolveHarnessSelectionRequest(
            artifact_mode="web",
            prompt="做一个设计公司的落地页",
            resolve_skill=True,
        ),
        user=user,
    )

    assert result.skill is None
    assert calls == []

