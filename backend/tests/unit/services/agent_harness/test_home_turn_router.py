import asyncio

import pytest

from app.services.agent_harness.runtime.execution_support.plan_gate_controller import PlanGateController
from app.services.agent_harness.workspace.conversation.home_turn_router import (
    canvas_bypass_route,
    route_after_interaction_submission,
    route_from_ui_action,
    route_home_text_turn,
)


@pytest.fixture(autouse=True)
def _planning_user_key(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier.resolve_user_apimart_key_for_context",
        AsyncMock(return_value="test-key"),
    )


@pytest.mark.asyncio
async def test_home_text_classifier_informational_skips_plan_gate():
    calls = []

    async def classifier(**kwargs):
        calls.append(kwargs)
        return {"label": "informational_turn", "confidence": 0.91}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web", "phase": "planning"},
        content="检索下尼采的生平",
        classifier=classifier,
    )

    assert calls
    assert route["route_kind"] == "informational_turn"
    assert route["requires_plan_gate"] is False
    assert route["activity"] == "answering"
    assert PlanGateController.initial_phase({
        "artifact_mode": "web",
        "phase": "planning",
        "turn_route": route,
    }) == "executing"


@pytest.mark.asyncio
async def test_home_text_classifier_artifact_creation_requires_plan_gate_for_web():
    async def classifier(**_kwargs):
        return {"label": "artifact_creation", "confidence": 0.94}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"},
        content="帮我做一个尼采生平网站",
        classifier=classifier,
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["requires_plan_gate"] is True
    assert route["activity"] == "planning_outline"
    assert PlanGateController.initial_phase({
        "artifact_mode": "web",
        "turn_route": route,
    }) == "planning"


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact_mode", ["web", "document", "slides"])
async def test_artifact_creation_requires_design_system_selection_for_visual_modes(artifact_mode):
    async def classifier(**_kwargs):
        return {"label": "artifact_creation", "confidence": 0.94}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": artifact_mode},
        content="帮我创建一个项目",
        classifier=classifier,
    )

    assert route["requires_plan_gate"] is True
    assert route["requires_design_system_selection"] is True


@pytest.mark.asyncio
async def test_artifact_creation_skips_design_system_selection_when_already_selected():
    async def classifier(**_kwargs):
        return {"label": "artifact_creation", "confidence": 0.94}

    route = await route_home_text_turn(
        conversation={
            "id": "conv-1",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "design_system_id": {"type": "design_system", "design_system_id": "manual"},
        },
        content="帮我创建一个项目",
        classifier=classifier,
    )

    assert route["requires_plan_gate"] is True
    assert route["requires_design_system_selection"] is False


@pytest.mark.asyncio
async def test_artifact_creation_skips_design_system_selection_for_spreadsheet():
    async def classifier(**_kwargs):
        return {"label": "artifact_creation", "confidence": 0.94}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "spreadsheet"},
        content="帮我创建一个表格",
        classifier=classifier,
    )

    assert route["requires_plan_gate"] is True
    assert route["requires_design_system_selection"] is False


@pytest.mark.asyncio
async def test_low_confidence_valid_classifier_label_still_controls_route():
    async def classifier(**_kwargs):
        return {"label": "artifact_creation", "confidence": 0.2}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"},
        content="随便看看",
        classifier=classifier,
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["confidence"] == 0.2
    assert route["requires_plan_gate"] is True
    assert route["activity"] == "planning_outline"


@pytest.mark.asyncio
async def test_invalid_classifier_label_defaults_to_informational():
    async def classifier(**_kwargs):
        return {"label": "unknown_mode", "confidence": 0.91}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"},
        content="随便看看",
        classifier=classifier,
    )

    assert route["route_kind"] == "informational_turn"
    assert route["confidence"] == 0.91
    assert route["requires_plan_gate"] is False


@pytest.mark.asyncio
async def test_home_text_classifier_collects_preflight_model_call_without_polluting_route():
    async def classifier(**_kwargs):
        return {
            "label": "informational_turn",
            "confidence": 0.9,
            "_preflight_model_call": {
                "model_name": "test-model",
                "usage": {"input_tokens": 12, "output_tokens": 3},
                "elapsed_ms": 42,
                "kind": "home_turn_router",
            },
        }

    model_calls = []
    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"},
        content="搜索下尼采的生平",
        classifier=classifier,
        preflight_model_calls=model_calls,
    )

    assert model_calls == [
        {
            "model_name": "test-model",
            "usage": {"input_tokens": 12, "output_tokens": 3},
            "elapsed_ms": 42,
            "kind": "home_turn_router",
        }
    ]
    assert "_preflight_model_call" not in route
    assert route["route_kind"] == "informational_turn"


@pytest.mark.asyncio
async def test_home_text_classifier_receives_selected_provider():
    calls = []

    async def classifier(**kwargs):
        calls.append(kwargs)
        return {"label": "informational_turn", "confidence": 0.9}

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"},
        content="搜索下尼采的生平",
        classifier=classifier,
        model_name="local-vision",
        provider_code="ollama",
    )

    assert route["route_kind"] == "informational_turn"
    assert calls[0]["model_name"] == "local-vision"
    assert calls[0]["provider_code"] == "ollama"


@pytest.mark.asyncio
async def test_initial_home_text_turn_records_default_classifier_model_call(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_API_KEY", "test-key")

    async def fake_model_call(**_kwargs):
        return {
            "label": "artifact_creation",
            "confidence": 0.91,
            "_preflight_model_call": {
                "model_name": "router-model",
                "usage": {"input_tokens": 21, "output_tokens": 5},
                "elapsed_ms": 37,
                "kind": "home_turn_router",
            },
        }

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier._call_side_classifier_model",
        fake_model_call,
    )

    model_calls: list[dict] = []
    route = await route_home_text_turn(
        conversation={
            "id": "new-conv",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "",
            "plan_state": None,
            "skill_id": None,
            "resolved_skill_id": None,
        },
        content="帮我做一个新品发布网站",
        user_id=7,
        conversation_id="new-conv",
        run_id="initial-send",
        model_name="router-model",
        preflight_model_calls=model_calls,
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["requires_plan_gate"] is True
    assert model_calls == [
        {
            "model_name": "router-model",
            "usage": {"input_tokens": 21, "output_tokens": 5},
            "elapsed_ms": 37,
            "kind": "home_turn_router",
        }
    ]


@pytest.mark.asyncio
async def test_initial_plan_first_turn_without_classifier_key_routes_to_artifact(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", False)

    route = await route_home_text_turn(
        conversation={
            "id": "new-conv",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "executing",
            "plan_state": None,
            "skill_id": None,
            "resolved_skill_id": None,
        },
        content="生成一个设计公司的落地页, 公司名称叫灵犀设计",
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["source"] == "classifier_unavailable_default"
    assert route["requires_plan_gate"] is True
    assert route["requires_skill_selection"] is True
    assert route["activity"] == "planning_outline"


@pytest.mark.asyncio
async def test_initial_plan_first_turn_when_classifier_fails_routes_to_artifact():
    async def classifier(**_kwargs):
        raise RuntimeError("upstream unavailable")

    route = await route_home_text_turn(
        conversation={
            "id": "new-conv",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "executing",
            "plan_state": None,
            "skill_id": None,
            "resolved_skill_id": None,
        },
        content="生成一个设计公司的落地页, 公司名称叫灵犀设计",
        classifier=classifier,
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["source"] == "classifier_failure_default"
    assert route["requires_plan_gate"] is True
    assert route["requires_skill_selection"] is True
    assert route["activity"] == "planning_outline"


@pytest.mark.asyncio
async def test_existing_plan_without_skill_when_classifier_fails_routes_to_revision():
    async def classifier(**_kwargs):
        raise RuntimeError("upstream unavailable")

    route = await route_home_text_turn(
        conversation={
            "id": "existing-conv",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "executing",
            "plan_state": {"title": "已有计划"},
            "skill_id": None,
            "resolved_skill_id": None,
        },
        content="继续修改这个页面",
        classifier=classifier,
    )

    assert route["route_kind"] == "artifact_revision"
    assert route["source"] == "classifier_failure_default"
    assert route["requires_skill_selection"] is True


@pytest.mark.asyncio
async def test_canvas_bypasses_classifier():
    async def classifier(**_kwargs):
        raise AssertionError("classifier should not be called for canvas")

    route = await route_home_text_turn(
        conversation={"id": "conv-1", "runtime_profile": "canvas", "artifact_mode": "web"},
        content="把标题调大",
        classifier=classifier,
    )

    assert route == canvas_bypass_route().to_dict()
    assert PlanGateController.requires_initial_plan({"runtime_profile": "canvas", "artifact_mode": "web", "turn_route": route}) is False


def test_ui_action_route_never_requires_classifier_or_plan_gate():
    route = route_from_ui_action(action_type="interaction_submitted")

    assert route["route_kind"] == "workflow_continuation"
    assert route["source"] == "ui_action"
    assert route["requires_plan_gate"] is False


def test_plan_gate_does_not_fallback_to_artifact_mode_without_route_or_plan():
    conversation = {
        "runtime_profile": "home",
        "artifact_mode": "web",
        "phase": "executing",
        "plan_state": None,
        "turn_route": None,
    }

    assert PlanGateController.requires_initial_plan(conversation) is False
    assert PlanGateController.initial_phase(conversation) == "executing"


def test_plan_gate_preserves_existing_plan_workflow_without_route():
    conversation = {
        "runtime_profile": "home",
        "artifact_mode": "web",
        "phase": "planning_ready",
        "plan_state": {"title": "计划", "summary": "已有计划"},
        "turn_route": None,
    }

    assert PlanGateController.initial_phase(conversation) == "planning_ready"


@pytest.mark.asyncio
async def test_pending_workflow_text_uses_deterministic_context_not_ui_action():
    async def classifier(**_kwargs):
        raise AssertionError("classifier should not be called while a workflow is pending")

    route = await route_home_text_turn(
        conversation={
            "id": "conv-1",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "runtime_status": "waiting_input",
            "user_interaction": {"request_id": "ask-1"},
        },
        content="选第二个",
        classifier=classifier,
    )

    assert route["route_kind"] == "workflow_continuation"
    assert route["source"] == "deterministic_context"
    assert route["requires_plan_gate"] is False


@pytest.mark.asyncio
async def test_route_home_text_turn_blocks_until_classifier_resolves():
    """Confirms hypothesis #2: route_home_text_turn awaits the classifier.

    The classifier is gated by an asyncio.Event. Until the event fires, the
    routing coroutine cannot return — and in send_harness_message the routing
    call sits ahead of _build_live_streaming_response, so until this returns
    no SSE bytes can flow to the client. This is the smoking gun for the
    perceived "front-end UI disconnected" pause on each text message.
    """
    gate = asyncio.Event()
    classifier_invocations: list[dict] = []

    async def gated_classifier(**kwargs):
        classifier_invocations.append(kwargs)
        await gate.wait()
        return {"label": "informational_turn", "confidence": 0.9}

    route_task = asyncio.create_task(
        route_home_text_turn(
            conversation={"id": "conv-gated", "runtime_profile": "home", "artifact_mode": "web"},
            content="搜索下黑格尔的生平",
            classifier=gated_classifier,
        )
    )

    # Give the classifier coroutine a chance to start and block on `gate`.
    await asyncio.sleep(0)
    assert classifier_invocations, "classifier should have been invoked"
    assert not route_task.done(), (
        "route_home_text_turn must not resolve while the classifier is still awaiting"
    )

    # asyncio.wait_for with a tight timeout proves the route is truly blocked,
    # not just yielded back to the event loop.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(route_task), timeout=0.05)
    assert not route_task.done()

    gate.set()
    route = await route_task
    assert route["route_kind"] == "informational_turn"


@pytest.mark.asyncio
async def test_route_home_text_turn_defaults_to_informational_when_classifier_times_out(monkeypatch):
    """Classifier timeout must not abort the send-message request.

    The classifier sits before StreamingResponse creation. If its timeout
    bubbles out, the API returns 500 before the agent run can start, which
    looks like a stuck turn in the UI.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "CLASSIFIER_TIMEOUT_SECONDS", 0.05)

    classifier_started = asyncio.Event()

    async def never_returning_classifier(**_kwargs):
        classifier_started.set()
        await asyncio.Event().wait()  # block forever

    route = await route_home_text_turn(
        conversation={"id": "conv-timeout", "runtime_profile": "home", "artifact_mode": "web"},
        content="搜索下黑格尔的生平",
        classifier=never_returning_classifier,
    )

    assert classifier_started.is_set(), "classifier should have been invoked"
    assert route["route_kind"] == "artifact_creation"
    assert route["source"] == "classifier_timeout_default"
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_quick_brief_keeps_plan_gate_for_slides():
    """Submitting a quick_brief (discovery) answer must NOT collapse plan gate.

    Regression: previously `/respond` always routed to `executing/no plan_gate`,
    so discovery answers in plan-first artifact modes silently skipped the
    plan-outline phase entirely.
    """
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-ppt",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "plan_state": None,
            "outline_runtime": {"current_outline": None},
        },
        pending_interaction={"kind": "quick_brief"},
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["source"] == "interaction_submitted"
    assert route["requires_plan_gate"] is True
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_design_system_picker_keeps_plan_gate_for_web():
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-web",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "skill_id": "open-design",
            "design_system_id": None,
            "plan_state": None,
            "outline_runtime": None,
        },
        pending_interaction={"kind": "design_system_picker"},
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["requires_plan_gate"] is True
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_ask_user_during_execution_stays_executing():
    """ask_user fired mid-execution must not re-trigger plan gate."""
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-mid",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "plan_state": {"items": [{"id": "1", "title": "intro"}]},
        },
        pending_interaction={"kind": "ask_user"},
    )

    assert route["requires_plan_gate"] is False
    assert route["activity"] == "executing"


def test_route_after_interaction_canvas_ask_user_bypasses_plan_gate_even_for_web_mode():
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-canvas",
            "runtime_profile": "canvas",
            "artifact_mode": "web",
            "phase": "planning",
            "plan_state": None,
        },
        pending_interaction={"kind": "ask_user"},
    )

    assert route["route_kind"] == "workflow_continuation"
    assert route["source"] == "canvas_bypass"
    assert route["requires_plan_gate"] is False
    assert route["activity"] == "executing"


def test_route_after_interaction_ask_user_during_initial_planning_keeps_plan_gate():
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-planning",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "phase": "planning",
            "plan_state": None,
        },
        pending_interaction={"kind": "ask_user"},
    )

    assert route["route_kind"] == "artifact_creation"
    assert route["source"] == "interaction_submitted"
    assert route["requires_plan_gate"] is True
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_ask_user_during_planning_with_existing_plan_keeps_revision_context():
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-planning",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "phase": "planning",
            "plan_state": {"items": [{"id": "1", "title": "intro"}]},
        },
        pending_interaction={"kind": "ask_user"},
    )

    assert route["route_kind"] == "workflow_continuation"
    assert route["requires_plan_gate"] is False
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_ask_user_during_plan_revision_stays_revising():
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-revising",
            "runtime_profile": "home",
            "artifact_mode": "slides",
            "phase": "revising_plan",
            "plan_state": {"items": [{"id": "1", "title": "intro"}]},
        },
        pending_interaction={"kind": "ask_user"},
    )

    assert route["requires_plan_gate"] is False
    assert route["activity"] == "planning_outline"


def test_route_after_interaction_quick_brief_on_non_plan_first_mode_executes():
    """Image / video modes are not plan-first; discovery answers go straight to executing."""
    route = route_after_interaction_submission(
        conversation={
            "id": "conv-img",
            "runtime_profile": "home",
            "artifact_mode": "image",
            "plan_state": None,
            "outline_runtime": None,
        },
        pending_interaction={"kind": "quick_brief"},
    )

    assert route["requires_plan_gate"] is False
    assert route["activity"] == "executing"

