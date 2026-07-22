import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.schemas.harness import SendHarnessMessageRequest
from app.services.agent_harness import catalog
from app.services.agent_harness.catalog import CatalogSnapshot, SkillSummary
from app.services.agent_harness.runtime.eventing.event_log import append_event
from app.services.agent_harness.runtime.eventing.turn_protocol import build_turn_completed_payload
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    get_conversation,
    update_conversation,
)
from app.services.agent_harness.workspace.conversation.conversation_snapshot import (
    build_conversation_detail_snapshot,
)
from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

_runtime_capture = SimpleNamespace(
    start_conversation_run=None,
    _test_engine_factory=None,
    ConversationAlreadyRunningError=Exception,
)


def _catalog_skill(
    skill_id: str,
    *,
    artifact_mode: str = "web",
    selectable: bool = True,
    phase_enabled: bool = True,
    canvas_explicit: bool = False,
    canvas_default: bool = False,
    helper_eligible: bool = False,
) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name=skill_id,
        name_en=skill_id,
        name_zh=skill_id,
        description=f"{skill_id} skill",
        description_en=f"{skill_id} skill",
        description_zh=f"{skill_id} skill",
        icon="",
        color="",
        triggers=[skill_id],
        mode="prototype",
        surface=None,
        platform=None,
        scenario=None,
        artifact_mode=artifact_mode,
        default_for=[],
        featured=1,
        preview_type="html",
        preview_entry=None,
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider=None,
        protocol_family=None,
        protocol_metadata={},
        capabilities={
            "selection_enabled": selectable,
            "phase_enabled": phase_enabled,
            "canvas_explicit": canvas_explicit,
            "canvas_default": canvas_default,
            "helper_eligible": helper_eligible,
        },
        example_prompt=None,
        has_example_html=False,
    )


@pytest.fixture(autouse=True)
def _agent_catalog_summaries_for_phase_tests(monkeypatch):
    skills = [
        _catalog_skill("web", artifact_mode="web"),
        _catalog_skill("docx", artifact_mode="document"),
        _catalog_skill("xlsx", artifact_mode="spreadsheet"),
        _catalog_skill("pptx", artifact_mode="slides"),
        _catalog_skill("html-ppt", artifact_mode="slides"),
        _catalog_skill("saas-landing", artifact_mode="web"),
        _catalog_skill("imagegen", artifact_mode="image", selectable=False),
        _catalog_skill("canvas_agent", artifact_mode="web", selectable=False),
        _catalog_skill(
            "design_workflow",
            artifact_mode="web",
            selectable=False,
            canvas_default=True,
        ),
        _catalog_skill(
            "brand_strategy_architect",
            artifact_mode="web",
            selectable=False,
            canvas_explicit=True,
        ),
        _catalog_skill(
            "vi-design-guide",
            artifact_mode="web",
            selectable=False,
            canvas_explicit=True,
        ),
        _catalog_skill(
            "critique",
            artifact_mode="web",
            selectable=False,
            helper_eligible=True,
        ),
        _catalog_skill(
            "menswear-ecommerce-hero",
            artifact_mode="image",
            selectable=False,
            canvas_explicit=True,
        ),
    ]
    monkeypatch.setattr(
        catalog,
        "_LOCAL_SKILL_SNAPSHOT",
        CatalogSnapshot(kind="skills", source_digest="test-skills", generated_at=1, items=skills),
    )
    monkeypatch.setattr(
        catalog,
        "_LOCAL_DESIGN_SYSTEM_SNAPSHOT",
        CatalogSnapshot(kind="design-systems", source_digest="test-design", generated_at=1, items=[]),
    )


async def _drain_started_runs(run_invocations: list[dict]) -> None:
    for invocation in run_invocations:
        producer_factory = invocation.get("producer_factory")
        if producer_factory is None:
            continue
        async for _ in producer_factory():
            pass


def _force_artifact_home_turn_route(monkeypatch, *, route_kind: str = "artifact_creation") -> None:
    async def _route_home_text_turn(*, conversation, **_kwargs):
        artifact_mode = str(conversation.get("artifact_mode") or "web").strip().lower()
        requires_plan_gate = artifact_mode in {"web", "document", "spreadsheet", "slides"}
        return {
            "route_kind": route_kind,
            "source": "classifier",
            "confidence": 0.95,
            "requires_plan_gate": requires_plan_gate,
            "requires_skill_selection": requires_plan_gate and not bool(conversation.get("skill_id")),
            "requires_design_system_selection": (
                requires_plan_gate
                and artifact_mode in {"web", "document", "slides"}
                and not bool(conversation.get("design_system_id"))
            ),
            "activity": "planning_outline" if requires_plan_gate else "executing",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )


def _append_waiting_input_interaction(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    request_id: str,
    question: str,
) -> None:
    interaction = {
        "request_id": request_id,
        "tool_call_id": request_id,
        "kind": "ask_user",
        "question": question,
        "status": "pending",
        "runtime_status": "waiting_input",
    }
    interaction_form_op = presentation_v2.interaction_form(
        conversation_id=conversation_id,
        run_id=run_id,
        interaction=interaction,
    )
    append_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=str(interaction_form_op["type"]),
        data=interaction_form_op,
        lane="user",
    )
    runtime_snapshot = {
        "runtime_status": "waiting_input",
        "run_state": "waiting_input",
        "turn_status": "waiting_input",
        "user_interaction": interaction,
    }
    append_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation_id,
            run_id=run_id,
            status="waiting_input",
            runtime_snapshot=runtime_snapshot,
        ),
        lane="user",
    )


@pytest.fixture(autouse=True)
def _bypass_license_capability_for_phase_tests(monkeypatch):
    async def _ensure_capability(_self, _capability):
        return None

    monkeypatch.setattr(
        "app.services.license_service.LicenseService.ensure_capability",
        _ensure_capability,
    )


@pytest.fixture(autouse=True)
def _bridge_legacy_run_capture_to_enqueue(monkeypatch):
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.workspace.conversation import conversation_meta_store

    class _LegacyConversationAlreadyRunningError(Exception):
        pass

    monkeypatch.setattr(
        _runtime_capture,
        "ConversationAlreadyRunningError",
        _LegacyConversationAlreadyRunningError,
    )

    async def _enqueue_message_run(*, user_id, conversation_id, payload, idempotency_key, wake_worker=True, **_kwargs):
        del idempotency_key, wake_worker, _kwargs

        async def _producer_factory():
            run_kwargs = {
                key: value
                for key, value in dict(payload or {}).items()
                if key != "payload_version"
            }
            run_kwargs.setdefault(
                "conversation",
                conversation_meta_store.get_conversation(user_id, conversation_id) or {},
            )

            factory = getattr(_runtime_capture, "_test_engine_factory", None)
            if callable(factory):
                engine = factory(user_id)
                async for item in engine.run(**run_kwargs):
                    yield item
            if False:
                yield {}

        start = getattr(_runtime_capture, "start_conversation_run", None)
        if start is not None:
            try:
                start(user_id, conversation_id, _producer_factory)
            except _LegacyConversationAlreadyRunningError as exc:
                raise AgentRunAlreadyActiveError(str(exc)) from exc
        return SimpleNamespace(id=1, run_id="test-run")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_message_run",
        _enqueue_message_run,
    )
    async def _wake_agent_run_worker():
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.agent_coordination.run_wakeup_bus.wake_agent_run_worker",
        _wake_agent_run_worker,
    )

    async def _default_resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=[],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _default_resolve_selection,
    )


@pytest.mark.asyncio
async def test_send_message_endpoint_delegates_to_service(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}
    response = object()

    async def _send_harness_message(**kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.send_message_service.send_harness_message",
        _send_harness_message,
    )

    result = await harness_endpoint.send_message(
        conversation_id="conv-service",
        data=SendHarnessMessageRequest(content="hello"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert result is response
    assert captured["conversation_id"] == "conv-service"
    assert captured["user"] is user
    assert captured["data"].content == "hello"


@pytest.mark.asyncio
async def test_send_message_ui_action_payload_does_not_call_home_text_classifier(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    conversation = {
        "id": "conv-ui-action",
        "runtime_profile": "home",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "executing",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs) or conversation.update(kwargs) or conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _route_home_text_turn(**_kwargs):
        raise AssertionError("ui action payload must not use home text classifier")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )

    class _FakeEngine:
        async def run(self, **kwargs):
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", lambda _user_id: _FakeEngine())

    await harness_endpoint.send_message(
        conversation_id="conv-ui-action",
        data=SendHarnessMessageRequest(
            content="Help me regenerate slide 2 in the PPT",
            input_kind="user_ui_action",
            action_type="presentation_regenerate_slide",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(
        update.get("turn_route", {}).get("source") == "ui_action"
        and update.get("turn_route", {}).get("route_kind") == "workflow_continuation"
        for update in updates
    )


@pytest.mark.parametrize(
    ("conversation_model_preferences", "request_model_preferences", "expected_model"),
    [
        ({"multimodal_model": "kimi-k2.5"}, None, "kimi-k2.5"),
        (
            {"multimodal_model": "glm-5.1"},
            {"multimodal_model": "claude-sonnet-4-5"},
            "claude-sonnet-4-5",
        ),
    ],
)
@pytest.mark.asyncio
async def test_send_message_routes_home_turn_with_selected_multimodal_model(
    monkeypatch,
    conversation_model_preferences,
    request_model_preferences,
    expected_model,
):
    user = SimpleNamespace(id=7)
    route_calls: list[dict] = []
    run_invocations: list[dict] = []
    conversation = {
        "id": "conv-router-model",
        "runtime_profile": "home",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "",
        "plan_state": None,
        "model_preferences": conversation_model_preferences,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _route_home_text_turn(**kwargs):
        route_calls.append(kwargs)
        return {
            "route_kind": "artifact_creation",
            "source": "classifier",
            "confidence": 0.95,
            "requires_plan_gate": True,
            "requires_skill_selection": True,
            "requires_design_system_selection": True,
            "activity": "planning_outline",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )

    await harness_endpoint.send_message(
        conversation_id="conv-router-model",
        data=SendHarnessMessageRequest(
            content="帮我做一个官网",
            model_preferences=request_model_preferences,
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert route_calls
    assert route_calls[0]["model_name"] == expected_model
    assert run_invocations


@pytest.mark.asyncio
async def test_send_message_home_informational_turn_stays_executing_in_web_mode(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    conversation = {
        "id": "conv-home-info-web",
        "runtime_profile": "home",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "executing",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
        "runtime_status": "idle",
        "run_state": "idle",
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs) or conversation.update(kwargs) or conversation,
    )

    async def _route_home_text_turn(**_kwargs):
        return {
            "route_kind": "informational_turn",
            "source": "classifier",
            "confidence": 0.91,
            "requires_plan_gate": False,
            "requires_skill_selection": False,
            "requires_design_system_selection": False,
            "activity": "answering",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"conversation_snapshot": dict(conversation), "producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    class _FakeEngine:
        async def run(self, **kwargs):
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", lambda _user_id: _FakeEngine())

    await harness_endpoint.send_message(
        conversation_id="conv-home-info-web",
        data=SendHarnessMessageRequest(content="搜索下尼采的生平", artifact_mode="web"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert any(update.get("turn_route", {}).get("route_kind") == "informational_turn" for update in updates)
    assert conversation["phase"] == "executing"
    assert conversation["activity"] == "answering"
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "executing"


@pytest.mark.asyncio
async def test_send_message_blocks_premium_home_harness_runtime(monkeypatch):
    user = SimpleNamespace(id=7)
    start_run_calls: list[dict] = []
    capability_calls: list[str] = []
    conversation = {
        "id": "conv-home-premium",
        "runtime_profile": "home",
        "skill_id": None,
        "phase": "planning",
        "model_preferences": None,
    }

    async def _ensure_capability(self, capability):
        capability_calls.append(capability)
        raise HTTPException(status_code=403, detail="current license edition does not include this feature")

    monkeypatch.setattr(
        "app.services.license_service.LicenseService.ensure_capability",
        _ensure_capability,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda _user_id, _conversation_id, producer_factory: start_run_calls.append({
            "conversation_id": _conversation_id,
            "producer_factory": producer_factory,
        }),
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.send_message(
            conversation_id="conv-home-premium",
            data=SendHarnessMessageRequest(content="hello"),
            request=SimpleNamespace(headers={}),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 403
    assert capability_calls == ["home_agent"]
    assert start_run_calls == []


@pytest.mark.asyncio
async def test_send_message_allows_premium_canvas_harness_runtime_without_home_capability(monkeypatch):
    user = SimpleNamespace(id=7)
    start_run_calls: list[dict] = []
    capability_calls: list[str] = []
    conversation = {
        "id": "conv-canvas-premium",
        "runtime_profile": "canvas",
        "project_id": 88,
        "skill_id": "design_workflow",
        "resolved_skill_id": "design_workflow",
        "skill_selection_mode": "auto",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    async def _ensure_capability(self, capability):
        capability_calls.append(capability)
        raise HTTPException(status_code=403, detail="current license edition does not include this feature")

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.license_service.LicenseService.ensure_capability",
        _ensure_capability,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs),
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda _user_id, _conversation_id, producer_factory: start_run_calls.append({
            "conversation_id": _conversation_id,
            "producer_factory": producer_factory,
        }),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )

    response = await harness_endpoint.send_message(
        conversation_id="conv-canvas-premium",
        data=SendHarnessMessageRequest(content="帮我生成一张图"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert capability_calls == []
    assert response.status_code == 200
    assert start_run_calls and start_run_calls[0]["conversation_id"] == "conv-canvas-premium"


@pytest.mark.asyncio
async def test_send_message_stream_captures_immediate_user_interaction_events_started_before_body_iteration(monkeypatch, tmp_path):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        user.id,
        title="canvas-race",
        runtime_profile="canvas",
        project_id=88,
        skill_id="brand_strategy_architect",
        resolved_skill_id="brand_strategy_architect",
        skill_selection_mode="manual",
        skill_resolution_source="user_selected",
        web_search_enabled=False,
    )
    conversation.update({
        "phase": "executing",
        "model_preferences": None,
        "run_id": "run-race-1",
    })

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_runtime_state",
        lambda *_args, **_kwargs: {"runtime_status": "waiting_input"},
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )

    def _start_conversation_run(_user_id, conversation_id, _producer_factory):
        _append_waiting_input_interaction(
            user_id=user.id,
            conversation_id=conversation_id,
            run_id=conversation["run_id"],
            request_id="call-race-1",
            question="Race interaction",
        )
        return SimpleNamespace(task=None)

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    response = await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(content="帮我做品牌策划"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    joined = "".join(chunks)
    assert '"type": "run_preparing"' in joined
    assert '"type": "presentation.block.upsert"' in joined
    assert '"ui_kind": "interaction_form"' in joined
    assert '"request_id": "call-race-1"' in joined


@pytest.mark.asyncio
async def test_send_message_stream_waits_briefly_for_terminal_interaction_event_enqueued_after_waiting_input(monkeypatch, tmp_path):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        user.id,
        title="canvas-race-delayed",
        runtime_profile="canvas",
        project_id=88,
        skill_id="brand_strategy_architect",
        resolved_skill_id="brand_strategy_architect",
        skill_selection_mode="manual",
        skill_resolution_source="user_selected",
        web_search_enabled=False,
    )
    conversation.update({
        "phase": "executing",
        "model_preferences": None,
        "run_id": "run-race-2",
    })

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    state_calls = {"count": 0}

    def _get_runtime_state(*_args, **_kwargs):
        state_calls["count"] += 1
        if state_calls["count"] == 1:
            loop = asyncio.get_running_loop()
            loop.create_task(_emit_delayed_interaction())
        return {
            "runtime_status": "waiting_input",
            "user_interaction": None,
        }

    async def _emit_delayed_interaction():
        await asyncio.sleep(0.03)
        _append_waiting_input_interaction(
            user_id=user.id,
            conversation_id=conversation["id"],
            run_id=conversation["run_id"],
            request_id="call-race-delayed-1",
            question="Delayed interaction",
        )

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_runtime_state",
        _get_runtime_state,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: SimpleNamespace(task=None),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS",
        0.01,
    )

    response = await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(content="帮我做品牌策划"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    joined = "".join(chunks)
    assert '"type": "run_preparing"' in joined
    assert '"type": "presentation.block.upsert"' in joined
    assert '"ui_kind": "interaction_form"' in joined
    assert '"request_id": "call-race-delayed-1"' in joined


@pytest.mark.asyncio
async def test_send_message_stream_waits_for_pending_interaction_event_even_after_runtime_state_is_already_waiting_input(monkeypatch, tmp_path):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(
        user.id,
        title="canvas-race-pending",
        runtime_profile="canvas",
        project_id=88,
        skill_id="brand_strategy_architect",
        resolved_skill_id="brand_strategy_architect",
        skill_selection_mode="manual",
        skill_resolution_source="user_selected",
        web_search_enabled=False,
    )
    conversation.update({
        "phase": "executing",
        "model_preferences": None,
        "run_id": "run-race-pending",
    })

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    state_calls = {"count": 0}

    def _get_runtime_state(*_args, **_kwargs):
        state_calls["count"] += 1
        if state_calls["count"] == 1:
            loop = asyncio.get_running_loop()
            loop.create_task(_emit_delayed_interaction())
        return {
            "runtime_status": "waiting_input",
            "user_interaction": {
                "request_id": "call-race-pending-1",
                "tool_call_id": "call-race-pending-1",
                "question": "Pending interaction",
                "status": "pending",
            },
        }

    async def _emit_delayed_interaction():
        await asyncio.sleep(0.03)
        _append_waiting_input_interaction(
            user_id=user.id,
            conversation_id=conversation["id"],
            run_id=conversation["run_id"],
            request_id="call-race-pending-1",
            question="Pending interaction",
        )

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_runtime_state",
        _get_runtime_state,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: SimpleNamespace(task=None),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS",
        0.05,
    )

    response = await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(content="帮我做品牌策划"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    joined = "".join(chunks)
    assert '"type": "run_preparing"' in joined
    assert '"type": "presentation.block.upsert"' in joined
    assert '"ui_kind": "interaction_form"' in joined
    assert '"request_id": "call-race-pending-1"' in joined


@pytest.mark.asyncio
async def test_stream_events_does_not_reconcile_recent_waiting_tool_conversation(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="recent-stream-waiting-tool")
    now = datetime.now(UTC).isoformat()
    update_conversation(
        7,
        conversation["id"],
        runtime_status="running",
        run_state="waiting_tool",
        turn_status="running",
        last_activity_at=now,
        last_activity_source="artifact_dependency_wait",
        finished_at=None,
    )
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "waiting_tool",
            "turn_status": "running",
            "last_activity_at": now,
            "last_activity_source": "artifact_dependency_wait",
            "heartbeat_at": None,
        },
        touch_updated_at=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS",
        0.01,
    )

    response = await harness_endpoint.stream_harness_events(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
    )

    first_chunk = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert '"type": "run_preparing"' in first_chunk
    stored = get_conversation(7, conversation["id"])
    assert stored is not None
    assert stored["runtime_status"] == "running"
    assert stored["run_state"] == "waiting_tool"


@pytest.mark.asyncio
async def test_canvas_product_hero_message_migrates_to_image_runtime_from_skill(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []

    conversation = create_conversation(
        user.id,
        title="canvas-product-from-web",
        runtime_profile="canvas",
        project_id=88,
        skill_selection_mode="auto",
        artifact_mode="web",
        web_search_enabled=False,
    )
    patch_runtime_state(
        user.id,
        conversation["id"],
        {
            "runtime_status": "idle",
            "run_state": "idle",
        },
        touch_updated_at=False,
    )

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda _user_id, _conversation_id, producer_factory: run_invocations.append({
            "conversation_id": _conversation_id,
            "producer_factory": producer_factory,
        }),
        raising=False,
    )

    response = await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(
            content="给这件T恤生成电商商品图",
            skill_id="menswear-ecommerce-hero",
            web_search_enabled=False,
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    stored = get_conversation(user.id, conversation["id"])
    assert response.status_code == 200
    assert stored is not None
    assert stored["skill_id"] == "menswear-ecommerce-hero"
    assert stored["resolved_skill_id"] == "menswear-ecommerce-hero"
    assert stored["skill_selection_mode"] == "manual"
    assert stored["skill_resolution_source"] == "user_selected"
    assert stored["artifact_mode"] == "image"


@pytest.mark.asyncio
async def test_send_message_does_not_eagerly_reenter_planning_for_complex_skill_follow_up(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-1",
        "skill_id": "pptx",
        "phase": "executing",
        "model_preferences": None,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    async def _route_home_text_turn(*_args, **_kwargs):
        return {
            "route_kind": "informational_turn",
            "source": "deterministic_context",
            "confidence": 1.0,
            "requires_plan_gate": False,
            "requires_skill_selection": False,
            "requires_design_system_selection": False,
            "activity": "answering",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-1",
        data=SendHarnessMessageRequest(
            content="换个方案，重新做一版，并且再补一个完整目录。",
            skill_selection_mode="auto",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert {"phase": "planning", "plan_approved": False} not in updates
    assert {"language": "zh"} in updates
    assert {"web_search_enabled": False} in updates


@pytest.mark.asyncio
async def test_send_message_keeps_execution_for_simple_skill_follow_up(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-2",
        "skill_id": "pptx",
        "phase": "executing",
        "model_preferences": None,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-2",
        data=SendHarnessMessageRequest(
            content="把标题颜色改成蓝色。",
            skill_selection_mode="auto",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert {"phase": "planning", "plan_approved": False} not in updates


@pytest.mark.asyncio
async def test_send_message_run_payload_reuses_persisted_user_message_identity(monkeypatch):
    user = SimpleNamespace(id=7)
    captured_payloads: list[dict] = []
    appended_messages: list[dict] = []
    conversation = {
        "id": "conv-user-message-identity",
        "skill_id": "xlsx",
        "phase": "planning",
        "runtime_profile": "home",
        "artifact_mode": "spreadsheet",
        "model_preferences": None,
        "web_search_enabled": False,
    }
    _force_artifact_home_turn_route(monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.active_run_guard.has_active_agent_run",
        lambda *_args, **_kwargs: False,
    )

    async def _capture_enqueue_message_run(**kwargs):
        captured_payloads.append(kwargs["payload"])
        return SimpleNamespace(id=42, run_id="run-user-message-identity", created=True)

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_message_run",
        _capture_enqueue_message_run,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message) or message,
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_latched_internal_hidden_skill_ids",
        lambda **_kwargs: (True, []),
    )

    await harness_endpoint.send_message(
        conversation_id="conv-user-message-identity",
        data=SendHarnessMessageRequest(
            content="生成一个表格",
            artifact_mode="spreadsheet",
            web_search_enabled=False,
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert captured_payloads
    user_message_event = captured_payloads[0]["user_message_event"]
    assert user_message_event["id"]
    assert user_message_event["created_at"]
    assert user_message_event["content"] == "生成一个表格"
    assert appended_messages == []


@pytest.mark.asyncio
async def test_send_message_persists_structured_upload_references(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    conversation = {
        "id": "conv-upload-ref",
        "skill_id": "imagegen",
        "phase": "executing",
        "runtime_profile": "home",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_latched_internal_hidden_skill_ids",
        lambda **_kwargs: (True, []),
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-upload-ref",
        data=SendHarnessMessageRequest(
            content="照着这张图生成一张新图",
            attachments=[
                {
                    "type": "image",
                    "url": "references/inputs/upload_001/source.png",
                    "name": "reference.png",
                }
            ],
            references=[
                {
                    "id": "ref-upload-1",
                    "kind": "upload_attachment",
                    "media_type": "image",
                    "display_name": "reference.png",
                    "source": {
                        "type": "harness_input",
                        "path": "references/inputs/upload_001/source.png",
                    },
                }
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert appended_messages
    references = appended_messages[0]["metadata"]["references"]
    assert references == [
        {
            "id": "ref-upload-1",
            "kind": "upload_attachment",
            "media_type": "image",
            "display_name": "reference.png",
            "tool_reference": "references/inputs/upload_001/source.png",
            "source": {
                "type": "harness_input",
                "path": "references/inputs/upload_001/source.png",
            },
        }
    ]


@pytest.mark.asyncio
async def test_send_message_rejects_unattached_upload_reference(monkeypatch):
    user = SimpleNamespace(id=7)
    conversation = {
        "id": "conv-upload-ref-invalid",
        "skill_id": "imagegen",
        "phase": "executing",
        "runtime_profile": "home",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.send_message(
            conversation_id="conv-upload-ref-invalid",
            data=SendHarnessMessageRequest(
                content="照着这张图生成一张新图",
                attachments=[
                    {
                        "type": "image",
                        "url": "references/inputs/upload_001/source.png",
                        "name": "reference.png",
                    }
                ],
                references=[
                    {
                        "id": "ref-upload-missing",
                        "kind": "upload_attachment",
                        "media_type": "image",
                        "source": {
                            "type": "harness_input",
                            "path": "references/inputs/upload_999/source.png",
                        },
                    }
                ],
            ),
            request=SimpleNamespace(headers={}),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert "ref-upload-missing" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_send_message_persists_structured_home_asset_and_workspace_references(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    conversation = {
        "id": "conv-home-asset-ref",
        "skill_id": "imagegen",
        "phase": "executing",
        "runtime_profile": "home",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(harness_endpoint, "_latched_internal_hidden_skill_ids", lambda **_kwargs: (True, []))

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-home-asset-ref",
        data=SendHarnessMessageRequest(
            content="用这两张图继续生成",
            attachments=[
                {
                    "type": "image",
                    "url": "https://cdn.example.com/library.png",
                    "name": "library.png",
                },
                {
                    "type": "image",
                    "url": "references/generated/generated_image_001/original.png",
                    "name": "generated.png",
                },
            ],
            references=[
                {
                    "id": "home-asset:https://cdn.example.com/library.png",
                    "kind": "home_asset",
                    "media_type": "image",
                    "display_name": "library.png",
                    "source": {"type": "home_asset", "url": "https://cdn.example.com/library.png"},
                },
                {
                    "id": "workspace-file:references/generated/generated_image_001/original.png",
                    "kind": "workspace_file",
                    "media_type": "image",
                    "display_name": "generated.png",
                    "source": {
                        "type": "workspace_file",
                        "path": "references/generated/generated_image_001/original.png",
                    },
                },
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    references = appended_messages[0]["metadata"]["references"]
    assert [reference["kind"] for reference in references] == ["home_asset", "workspace_file"]
    assert [reference["tool_reference"] for reference in references] == [
        "https://cdn.example.com/library.png",
        "references/generated/generated_image_001/original.png",
    ]
    assert appended_messages[0]["metadata"]["reference_diagnostics"] == {
        "count": 2,
        "ids": [
            "home-asset:https://cdn.example.com/library.png",
            "workspace-file:references/generated/generated_image_001/original.png",
        ],
        "kinds": {"home_asset": 1, "workspace_file": 1},
    }


@pytest.mark.asyncio
async def test_canvas_send_message_persists_structured_local_upload_reference_without_legacy_hidden_context(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    run_calls: list[dict] = []
    conversation = {
        "id": "conv-canvas-local-ref",
        "runtime_profile": "canvas",
        "project_id": 88,
        "skill_id": "canvas_agent",
        "resolved_skill_id": "canvas_agent",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return [
            {
                "id": "img-local-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/88/local-source.png",
                "name": "本地上传图",
                "asset_origin": "local_upload",
            }
        ]

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[{"id": "img-local-1"}],
            prompt_context="## 当前引用的画布资源\n- URL: `/api/v1/uploads/canvas/88/local-source.png`",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_latched_internal_hidden_skill_ids",
        lambda **_kwargs: (True, []),
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            run_calls.append(kwargs)
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-local-ref",
        data=SendHarnessMessageRequest(
            content="照着 @[本地上传图](canvas:img-local-1) 生成一张新图",
            references=[
                {
                    "id": "canvas:img-local-1",
                    "kind": "canvas_item",
                    "media_type": "image",
                    "display_name": "本地上传图",
                    "source": {
                        "type": "canvas_item",
                        "item_id": "img-local-1",
                    },
                }
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    references = appended_messages[0]["metadata"]["references"]
    assert references == [
        {
            "id": "canvas:img-local-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "本地上传图",
            "tool_reference": "/api/v1/uploads/canvas/88/local-source.png",
            "source": {
                "type": "canvas_item",
                "item_id": "img-local-1",
            },
        }
    ]
    assert "hidden_user_context" not in appended_messages[0].get("metadata", {})
    assert run_calls[0]["hidden_user_context"] is None


@pytest.mark.asyncio
async def test_canvas_send_message_snapshots_generated_artifact_reference(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    run_calls: list[dict] = []
    conversation = {
        "id": "conv-canvas-generated-ref",
        "runtime_profile": "canvas",
        "project_id": 88,
        "skill_id": "canvas_agent",
        "resolved_skill_id": "canvas_agent",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return [
            {
                "id": "generated-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/88/generated-preview.png",
                "name": "生成图",
                "asset_origin": "ai_generated",
                "artifact_ref": "artifact_ref:generated-image-1",
            }
        ]

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[{"id": "generated-1"}],
            prompt_context="legacy canvas reference context should not be used",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.send_message_service._is_generation_artifact_available",
        lambda _conversation_dir, artifact_ref: artifact_ref == "artifact_ref:generated-image-1",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_latched_internal_hidden_skill_ids",
        lambda **_kwargs: (True, []),
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            run_calls.append(kwargs)
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-generated-ref",
        data=SendHarnessMessageRequest(
            content="照着 @[生成图](canvas:generated-1) 做一个变体",
            references=[
                {
                    "id": "canvas:generated-1",
                    "kind": "canvas_item",
                    "media_type": "image",
                    "display_name": "生成图",
                    "source": {
                        "type": "canvas_item",
                        "item_id": "generated-1",
                    },
                }
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert appended_messages[0]["metadata"]["references"] == [
        {
            "id": "canvas:generated-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "生成图",
            "tool_reference": "artifact_ref:generated-image-1",
            "source": {
                "type": "canvas_item",
                "item_id": "generated-1",
                "origin": "generated_artifact",
                "artifact_ref": "artifact_ref:generated-image-1",
            },
        }
    ]
    assert run_calls[0]["hidden_user_context"] is None


@pytest.mark.asyncio
async def test_canvas_send_message_falls_back_to_url_for_unavailable_generated_artifact_reference(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    run_calls: list[dict] = []
    conversation = {
        "id": "conv-canvas-generated-ref-fallback",
        "runtime_profile": "canvas",
        "project_id": 88,
        "skill_id": "canvas_agent",
        "resolved_skill_id": "canvas_agent",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return [
            {
                "id": "generated-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/88/generated-preview.png",
                "name": "生成图",
                "asset_origin": "ai_generated",
                "artifact_ref": "artifact_ref:missing-generated-image-1",
            }
        ]

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[{"id": "generated-1"}],
            prompt_context="legacy canvas reference context should not be used",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.send_message_service._is_generation_artifact_available",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_latched_internal_hidden_skill_ids",
        lambda **_kwargs: (True, []),
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            run_calls.append(kwargs)
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-generated-ref-fallback",
        data=SendHarnessMessageRequest(
            content="照着 @[生成图](canvas:generated-1) 做一个变体",
            references=[
                {
                    "id": "canvas:generated-1",
                    "kind": "canvas_item",
                    "media_type": "image",
                    "display_name": "生成图",
                    "source": {
                        "type": "canvas_item",
                        "item_id": "generated-1",
                    },
                }
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert appended_messages[0]["metadata"]["references"] == [
        {
            "id": "canvas:generated-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "生成图",
            "tool_reference": "/api/v1/uploads/canvas/88/generated-preview.png",
            "source": {
                "type": "canvas_item",
                "item_id": "generated-1",
                "origin": "canvas_url_fallback",
            },
        }
    ]
    assert run_calls[0]["hidden_user_context"] is None


@pytest.mark.asyncio
async def test_canvas_send_message_snapshots_mark_reference_without_legacy_hidden_context(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    appended_messages: list[dict] = []
    run_calls: list[dict] = []
    conversation = {
        "id": "conv-canvas-mark-ref",
        "runtime_profile": "canvas",
        "project_id": 88,
        "skill_id": "canvas_agent",
        "resolved_skill_id": "canvas_agent",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    async def _require_canvas_project_access(_db, *, user_id, project_id):
        return SimpleNamespace(id=project_id, user_id=user_id)

    async def _load_canvas_items(*_args, **_kwargs):
        return [
            {
                "id": "img-local-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/88/local-source.png",
                "name": "本地上传图",
                "asset_origin": "local_upload",
            }
        ]

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._require_canvas_project_access",
        _require_canvas_project_access,
    )
    monkeypatch.setattr("app.services.agent_harness.canvas.load_canvas_items", _load_canvas_items)
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda *_args, **_kwargs: SimpleNamespace(
            cleaned_content="legacy stripped content",
            resources=[],
            prompt_context="legacy mark context should not be used",
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.append_model_message",
        lambda _user_id, _conversation_id, message: appended_messages.append(message),
    )
    monkeypatch.setattr(harness_endpoint, "_latched_internal_hidden_skill_ids", lambda **_kwargs: (True, []))

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            run_calls.append(kwargs)
            appended_messages.append({"metadata": kwargs.get("message_metadata", {})})
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-mark-ref",
        data=SendHarnessMessageRequest(
            content="只调整 #[葡萄](canvas-mark:mark-1:image:img-local-1:x:0.42:y:0.61)",
            references=[
                {
                    "id": "canvas-mark:mark-1",
                    "kind": "canvas_mark",
                    "media_type": "image",
                    "display_name": "葡萄",
                    "source": {
                        "type": "canvas_mark",
                        "mark_id": "mark-1",
                        "image_item_id": "img-local-1",
                    },
                    "mark": {
                        "id": "mark-1",
                        "image_item_id": "img-local-1",
                        "number": 1,
                        "label": "葡萄",
                        "position": {"x": 0.42, "y": 0.61},
                    },
                }
            ],
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    reference = appended_messages[0]["metadata"]["references"][0]
    assert reference["kind"] == "canvas_mark"
    assert reference["tool_reference"] == "/api/v1/uploads/canvas/88/local-source.png"
    assert reference["mark"]["position"] == {"x": 0.42, "y": 0.61}
    assert appended_messages[0]["metadata"]["reference_diagnostics"] == {
        "count": 1,
        "ids": ["canvas-mark:mark-1"],
        "kinds": {"canvas_mark": 1},
    }
    assert run_calls[0]["hidden_user_context"] is None


@pytest.mark.asyncio
async def test_send_message_does_not_auto_assign_mode_entry_skill_for_artifact_mode(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-3",
        "skill_id": None,
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    async def _route_home_text_turn(*_args, **_kwargs):
        return {
            "route_kind": "informational_turn",
            "source": "deterministic_context",
            "confidence": 1.0,
            "requires_plan_gate": False,
            "requires_skill_selection": False,
            "requires_design_system_selection": False,
            "activity": "answering",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _route_home_text_turn,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id=None,
                confidence=0.0,
                reasoning_summary="",
                should_replace_current=False,
            ),
            design_system=SimpleNamespace(
                id=None,
                confidence=0.0,
                reasoning_summary="",
                should_replace_current=False,
            ),
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-3",
        data=SendHarnessMessageRequest(
            content="生成一个四页的设计行业PPT",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert not any("skill_id" in item for item in updates)


@pytest.mark.asyncio
async def test_send_message_does_not_clear_canvas_default_skill_when_request_skill_is_null(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-canvas-default",
        "runtime_profile": "canvas",
        "project_id": 64,
        "skill_id": "design_workflow",
        "resolved_skill_id": "design_workflow",
        "skill_selection_mode": "auto",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    async def _allow_capability(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.license_service.LicenseService.ensure_capability",
        _allow_capability,
    )

    async def _allow_canvas_project(*_args, **_kwargs):
        return SimpleNamespace(id=64)

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)
    monkeypatch.setattr("app.services.agent_harness.canvas.load_canvas_items", _load_canvas_items)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-default",
        data=SendHarnessMessageRequest(
            content="帮我创建一个猴子的图片",
            skill_id=None,
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert conversation["skill_id"] == "design_workflow"
    assert conversation["resolved_skill_id"] == "design_workflow"
    assert not any(update.get("skill_id") is None for update in updates if "skill_id" in update)


@pytest.mark.asyncio
async def test_send_message_canvas_uses_selected_skill_without_helper_resolution(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []

    conversation = {
        "id": "conv-canvas-selected-skill",
        "runtime_profile": "canvas",
        "project_id": 64,
        "skill_id": "vi-design-guide",
        "resolved_skill_id": "vi-design-guide",
        "skill_selection_mode": "manual",
        "skill_resolution_source": "user_selected",
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    async def _require_canvas_project_access(*_args, **_kwargs):
        return SimpleNamespace(id=64)

    monkeypatch.setattr(
        harness_endpoint,
        "_require_canvas_project_access",
        _require_canvas_project_access,
    )

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr("app.services.agent_harness.canvas.load_canvas_items", _load_canvas_items)
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )

    async def _resolve_selection(**_kwargs):
        raise AssertionError("canvas send-message must not resolve skill or helper skills")

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-selected-skill",
        data=SendHarnessMessageRequest(content="为鹦鹉咖啡做VI"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert engine_run_calls[0]["conversation"]["skill_id"] == "vi-design-guide"
    assert engine_run_calls[0]["conversation"]["skill_selection_mode"] == "manual"
    assert engine_run_calls[0]["conversation"]["skill_resolution_source"] == "user_selected"


@pytest.mark.asyncio
async def test_send_message_canvas_defaults_to_design_workflow_without_selection_resolution(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []

    conversation = {
        "id": "conv-canvas-missing-skill",
        "runtime_profile": "canvas",
        "project_id": 64,
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "phase": "executing",
        "model_preferences": None,
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs) or conversation.update(kwargs) or conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )
    async def _require_canvas_project_access(*_args, **_kwargs):
        return SimpleNamespace(id=64)

    monkeypatch.setattr(
        harness_endpoint,
        "_require_canvas_project_access",
        _require_canvas_project_access,
    )

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    monkeypatch.setattr("app.services.agent_harness.canvas.load_canvas_items", _load_canvas_items)
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.parse_canvas_references",
        lambda content, _canvas_items, **_kwargs: SimpleNamespace(
            cleaned_content=content,
            resources=[],
            prompt_context="",
        ),
    )

    async def _resolve_selection(**_kwargs):
        raise AssertionError("canvas send-message must use its deterministic default skill")

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            pass

        async def run(self, **kwargs):
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-canvas-missing-skill",
        data=SendHarnessMessageRequest(content="生成一张品牌主视觉"),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(update.get("skill_id") == "design_workflow" for update in updates)
    assert conversation["skill_id"] == "design_workflow"
    assert conversation["resolved_skill_id"] == "design_workflow"
    assert conversation["skill_selection_mode"] == "auto"
    assert engine_run_calls[0]["conversation"]["skill_id"] == "design_workflow"


@pytest.mark.asyncio
async def test_send_message_auto_resolves_skill_only_when_auto_modes_omit_ids(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-4",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="saas-landing",
                confidence=0.93,
                reasoning_summary="Landing-page request benefits from a landing-page skill.",
                should_replace_current=True,
            ),
            design_system=None,
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-4",
        data=SendHarnessMessageRequest(
            content="做一个设计公司的落地页",
            skill_selection_mode="auto",
            artifact_mode="web",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(
        item.get("skill_id") == "saas-landing"
        and item.get("skill_selection_mode") == "auto"
        and item.get("resolved_skill_id") == "saas-landing"
        for item in updates
    )
    assert conversation["_pending_auto_selection_announcement_message"] == {
        "role": "assistant",
        "content": "已自动选择技能：Saas Landing。",
        "metadata": {
            "source": "auto_selection_announcement",
            "selected_skill_id": "saas-landing",
            "previous_skill_id": None,
        },
    }


@pytest.mark.asyncio
async def test_send_message_auto_resolves_skill_when_frontend_sends_null_skill_id(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-null-skill-id",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return dict(conversation)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="html-ppt",
                confidence=0.95,
                reasoning_summary="Slides request should resolve to the PPT skill.",
                should_replace_current=True,
            ),
            design_system=None,
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        async def run(self, **kwargs):
            assert kwargs["conversation"]["skill_id"] == "html-ppt"
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", lambda _user_id: _FakeEngine())

    await harness_endpoint.send_message(
        conversation_id="conv-null-skill-id",
        data=SendHarnessMessageRequest(
            content="生成一个五页的设计行业PPT",
            skill_id=None,
            skill_selection_mode="auto",
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(
        item.get("skill_id") == "html-ppt"
        and item.get("resolved_skill_id") == "html-ppt"
        and item.get("skill_selection_mode") == "auto"
        for item in updates
    )
    assert conversation["skill_id"] == "html-ppt"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_mode", "expected_skill_id"),
    [
        ("web", "web"),
        ("document", "docx"),
        ("spreadsheet", "xlsx"),
        ("slides", "pptx"),
    ],
)
async def test_send_message_defaults_required_plan_skill_when_auto_resolution_is_empty(
    monkeypatch,
    artifact_mode,
    expected_skill_id,
):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []
    live_events: list[dict] = []
    resolve_calls: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": f"conv-required-plan-default-skill-{artifact_mode}",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": artifact_mode,
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return dict(conversation)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**kwargs):
        resolve_calls.append(kwargs)
        return SimpleNamespace(
            skill=SimpleNamespace(
                id=None,
                confidence=0.0,
                reasoning_summary="",
                should_replace_current=False,
            ),
            internal_skill_ids=[],
            design_system=None,
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.live_event_publisher.publish_user_event",
        lambda user_id, conversation_id, run_id, event_type, data, lane="user": live_events.append({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "event_type": event_type,
            "data": data,
            "lane": lane,
        }),
    )

    class _FakeEngine:
        async def run(self, **kwargs):
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", lambda _user_id: _FakeEngine())

    await harness_endpoint.send_message(
        conversation_id=f"conv-required-plan-default-skill-{artifact_mode}",
        data=SendHarnessMessageRequest(
            content="生成一个五页的设计行业PPT",
            skill_selection_mode="auto",
            artifact_mode=artifact_mode,
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert resolve_calls and resolve_calls[0]["resolve_skill"] is True
    assert conversation["skill_id"] == expected_skill_id
    assert conversation["resolved_skill_id"] == expected_skill_id
    assert conversation["skill_resolution_source"] == "deterministic_default"
    assert engine_run_calls[0]["conversation"]["skill_id"] == expected_skill_id
    assert any(
        event["event_type"] == "selection_resolved"
        and event["data"]["skill_id"] == expected_skill_id
        and event["data"]["skill_resolution_source"] == "deterministic_default"
        for event in live_events
    )


@pytest.mark.asyncio
async def test_send_message_persists_explicit_auto_selected_skill_announcement(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-5",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "artifact_mode": "web",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-5",
        data=SendHarnessMessageRequest(
            content="生成一个四页的设计行业PPT",
            skill_id="html-ppt",
            skill_selection_mode="auto",
            skill_decision_reason="html-ppt skill is best for this request.",
            skill_decision_confidence=0.9,
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert any(
        item.get("skill_id") == "html-ppt"
        and item.get("skill_selection_mode") == "auto"
        for item in updates
    )
    assert conversation["_pending_auto_selection_announcement_message"] == {
        "role": "assistant",
        "content": "已自动选择技能：Html Ppt。",
        "metadata": {
            "source": "auto_selection_announcement",
            "selected_skill_id": "html-ppt",
            "previous_skill_id": None,
        },
    }
    assert not any("design_system_id" in item and item.get("design_system_id") for item in updates)


@pytest.mark.asyncio
async def test_send_message_persists_auto_selected_skill_announcement_after_pre_resolve(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []

    conversation = {
        "id": "conv-5b",
        "skill_id": "html-ppt",
        "resolved_skill_id": "html-ppt",
        "skill_selection_mode": "auto",
        "skill_resolution_source": "ai_resolved",
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.load_messages",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-5b",
        data=SendHarnessMessageRequest(
            content="生成一个四页的设计行业PPT",
            skill_id="html-ppt",
            skill_selection_mode="auto",
            skill_decision_reason="html-ppt skill is best for this request.",
            skill_decision_confidence=0.9,
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert conversation["_pending_auto_selection_announcement_message"] == {
        "role": "assistant",
        "content": "已自动选择技能：Html Ppt。",
        "metadata": {
            "source": "auto_selection_announcement",
            "selected_skill_id": "html-ppt",
            "previous_skill_id": None,
        },
    }


@pytest.mark.asyncio
async def test_send_message_auto_resolves_skill_even_when_design_system_id_exists(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-5",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": {
            "type": "design_system",
            "design_system_id": "atelier-zero",
            "source": "conversation_design_system_id",
        },
        "artifact_mode": "web",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )
    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="saas-landing",
                confidence=0.91,
                reasoning_summary="Skill should still be resolved before the design system is used.",
                should_replace_current=True,
            ),
            design_system=None,
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-5",
        data=SendHarnessMessageRequest(
            content="做一个设计公司的落地页",
            skill_selection_mode="auto",
            artifact_mode="web",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(
        item.get("skill_id") == "saas-landing"
        and item.get("resolved_skill_id") == "saas-landing"
        for item in updates
    )


@pytest.mark.asyncio
async def test_send_message_keeps_plan_first_phase_after_auto_resolving_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    live_events: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-plan-first",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "executing",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        conversation.update(kwargs)
        updates.append(kwargs)
        return dict(conversation)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"conversation_snapshot": dict(conversation), "producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="xlsx",
                confidence=0.99,
                reasoning_summary="Spreadsheet request benefits from xlsx.",
                should_replace_current=True,
            ),
            design_system=None,
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.live_event_publisher.publish_user_event",
        lambda user_id, conversation_id, run_id, event_type, data, lane="user": live_events.append({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "event_type": event_type,
            "data": data,
            "lane": lane,
        }),
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-plan-first",
        data=SendHarnessMessageRequest(
            content="帮我根据这批出生数据生成一个 Excel 表格",
            skill_selection_mode="auto",
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert conversation["artifact_mode"] == "spreadsheet"
    assert conversation["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"
    assert any(
        event["event_type"] == "selection_resolved"
        and event["data"]["skill_id"] == "xlsx"
        and event["data"]["resolved_skill_id"] == "xlsx"
        and event["data"]["skill_selection_mode"] == "auto"
        and event["data"]["skill_resolution_source"] == "ai_resolved"
        for event in live_events
    )


@pytest.mark.asyncio
async def test_send_message_keeps_plan_first_phase_for_pre_resolved_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-pre-resolved",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        async def _consume():
            generator = producer_factory()
            await generator.aclose()

        import asyncio

        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        asyncio.create_task(_consume())
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-pre-resolved",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_id="xlsx",
            skill_selection_mode="auto",
            skill_decision_reason="Spreadsheet request is best served by xlsx.",
            skill_decision_confidence=1.0,
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert any(item.get("phase") == "planning" for item in updates)
    assert conversation["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"


@pytest.mark.asyncio
async def test_send_message_clears_stale_plan_state_before_auto_resolving_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    # Simulate the merged conversation shape returned by get_conversation():
    # spreadsheet mode is correct, but a stale truthy plan_state is already present.
    conversation = {
        "id": "conv-xlsx-stale-plan-state",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": {
            "status": "planning_ready",
            "title": "stale merged plan",
        },
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="xlsx",
                confidence=0.99,
                reasoning_summary="Spreadsheet request benefits from xlsx.",
                should_replace_current=True,
            ),
            design_system=None,
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-stale-plan-state",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_selection_mode="auto",
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(item.get("plan_state") is None for item in updates)
    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert any(item.get("phase") == "planning" for item in updates)
    assert conversation["phase"] == "planning"
    assert conversation["plan_state"] is None
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["plan_state"] is None


@pytest.mark.asyncio
async def test_send_message_clears_stale_plan_state_for_pre_resolved_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-stale-plan-state-pre-resolved",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": {
            "status": "planning_ready",
            "title": "stale merged plan",
        },
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-stale-plan-state-pre-resolved",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_id="xlsx",
            skill_selection_mode="auto",
            skill_decision_reason="Spreadsheet request is best served by xlsx.",
            skill_decision_confidence=1.0,
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert any(item.get("plan_state") is None for item in updates)
    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert any(item.get("phase") == "planning" for item in updates)
    assert conversation["phase"] == "planning"
    assert conversation["plan_state"] is None
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["plan_state"] is None


@pytest.mark.asyncio
async def test_send_message_clears_truthy_nondict_plan_state_before_auto_resolving_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-stale-string-plan-state",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": "planning_ready",
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="xlsx",
                confidence=0.99,
                reasoning_summary="Spreadsheet request benefits from xlsx.",
                should_replace_current=True,
            ),
            design_system=None,
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-stale-string-plan-state",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_selection_mode="auto",
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert any(item.get("plan_state") is None for item in updates)
    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert any(item.get("phase") == "planning" for item in updates)
    assert conversation["phase"] == "planning"
    assert conversation["plan_state"] is None
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["plan_state"] is None


@pytest.mark.asyncio
async def test_send_message_clears_truthy_nondict_plan_state_for_pre_resolved_xlsx(monkeypatch):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-stale-string-plan-state-pre-resolved",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "skill_resolution_source": None,
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": ["planning_ready"],
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-stale-string-plan-state-pre-resolved",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_id="xlsx",
            skill_selection_mode="auto",
            skill_decision_reason="Spreadsheet request is best served by xlsx.",
            skill_decision_confidence=1.0,
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    assert any(item.get("plan_state") is None for item in updates)
    assert any(
        item.get("skill_id") == "xlsx"
        and item.get("resolved_skill_id") == "xlsx"
        for item in updates
    )
    assert any(item.get("phase") == "planning" for item in updates)
    assert conversation["phase"] == "planning"
    assert conversation["plan_state"] is None
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"
    assert run_invocations[0]["conversation_snapshot"]["plan_state"] is None


@pytest.mark.asyncio
async def test_send_message_appends_phase_diagnostic_trace_without_user_content(monkeypatch):
    user = SimpleNamespace(id=7)
    trace_calls: list[dict] = []
    run_invocations: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-xlsx-phase-diagnostic",
        "skill_id": "xlsx",
        "resolved_skill_id": "xlsx",
        "skill_selection_mode": "auto",
        "skill_resolution_source": "ai_resolved",
        "design_system_id": None,
        "artifact_mode": "spreadsheet",
        "phase": "executing",
        "plan_state": None,
        "runtime_status": "idle",
        "run_state": "idle",
        "turn_status": "idle",
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        conversation.update(kwargs)
        return conversation

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    def _append_trace(_user_id, _conversation_id, **kwargs):
        trace_calls.append(kwargs)

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.persistence.append_trace",
        _append_trace,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-xlsx-phase-diagnostic",
        data=SendHarnessMessageRequest(
            content="帮我根据历年出生人口生成一个表格",
            skill_selection_mode="auto",
            artifact_mode="spreadsheet",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    diagnostic = next(item for item in trace_calls if item["trace_type"] == "send_message_phase_diagnostic")
    payload = diagnostic["payload"]
    assert payload["derived_phase"] == "planning"
    assert payload["artifact_mode"] == "spreadsheet"
    assert payload["skill_id"] == "xlsx"
    assert payload["plan_state_type"] == "none"
    assert "帮我根据历年出生人口生成一个表格" not in str(payload)
    assert run_invocations[0]["conversation_snapshot"]["phase"] == "planning"


@pytest.mark.asyncio
async def test_send_message_reuses_auto_resolve_parent_usage_log_for_run_snapshot(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)

    conversation = {
        "id": "conv-auto-billing-parent",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": {"multimodal_model": "glm-5.1"},
        "web_search_enabled": True,
    }

    def _update_conversation(_user_id, _conversation_id, **kwargs):
        conversation.update(kwargs)
        return dict(conversation)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.append_message",
        lambda *_args, **_kwargs: None,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({"conversation_snapshot": dict(conversation), "producer_factory": producer_factory})
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=None,
            design_system=None,
            preflight_model_calls=[
                SimpleNamespace(
                    model_name="glm-5.1",
                    usage={"input_tokens": 30, "output_tokens": 10},
                    elapsed_ms=100,
                    kind="selection_resolver",
                ),
            ],
        )

    async def _record_preflight_model_billing(_engine, **kwargs):
        kwargs["ctx"].parent_usage_log_id = 4321
        kwargs["conversation"]["parent_usage_log_id"] = 4321
        return True

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.record_preflight_model_billing",
        _record_preflight_model_billing,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-auto-billing-parent",
        data=SendHarnessMessageRequest(
            content="做一个设计公司的落地页",
            skill_selection_mode="auto",
            artifact_mode="web",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert conversation["parent_usage_log_id"] == 4321
    assert engine_run_calls[0]["conversation"]["parent_usage_log_id"] == 4321


@pytest.mark.asyncio
async def test_send_message_persists_internal_hidden_skill_activation_without_changing_selected_skill(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    persisted_runtime_sessions: list[dict] = []
    engine_run_calls: list[dict] = []

    conversation = {
        "id": "conv-hidden-activation",
        "skill_id": "html-ppt",
        "resolved_skill_id": "html-ppt",
        "skill_selection_mode": "manual",
        "skill_resolution_source": "user_selected",
        "design_system_id": None,
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.read_runtime_state",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        lambda _user_id, _conversation_id, **kwargs: persisted_runtime_sessions.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.live_event_publisher.publish_user_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.conversation_events.append_conversation_event",
        lambda *_args, **_kwargs: {"sequence": 1},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.append_conversation_event",
        lambda *_args, **_kwargs: {"sequence": 1},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.persistence.append_event",
        lambda *_args, **_kwargs: {"sequence": 1},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.append_event",
        lambda *_args, **_kwargs: {"sequence": 1},
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**_kwargs):
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-hidden-activation",
        data=SendHarnessMessageRequest(
            content="继续完善这个PPT，并帮我批判性检查一下结构",
            skill_selection_mode="manual",
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    runtime_state = conversation.get("runtime_state") or {}
    assert runtime_state["runtime_contract"]["internal_hidden_skills"] == [
        {"id": "critique", "activation_source": "ai_resolved"}
    ]
    assert runtime_state["workspace_runtime_session"]["selected_skill"] == "html-ppt"
    assert runtime_state["workspace_runtime_session"]["internal_hidden_skills"] == [
        {"id": "critique", "activation_source": "ai_resolved"}
    ]
    assert conversation["skill_id"] == "html-ppt"
    assert run_invocations[0]["conversation_snapshot"]["skill_id"] == "html-ppt"
    assert engine_run_calls[0]["conversation"]["_pending_internal_hidden_skill_announcement_message"]["content"] == (
        "已加载内部技能：Critique。"
    )


@pytest.mark.asyncio
async def test_send_message_records_internal_hidden_skill_resolver_preflight_billing_with_selection_kind(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    persisted_runtime_sessions: list[dict] = []
    engine_run_calls: list[dict] = []
    billing_calls: list[dict] = []

    conversation = {
        "id": "conv-hidden-activation-billing",
        "skill_id": "design_workflow",
        "resolved_skill_id": "design_workflow",
        "skill_selection_mode": "auto",
        "skill_resolution_source": "ai_resolved",
        "design_system_id": None,
        "artifact_mode": "image",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": {"multimodal_model": "kimi-k2.5"},
        "web_search_enabled": False,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.read_runtime_state",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        lambda _user_id, _conversation_id, **kwargs: persisted_runtime_sessions.append(kwargs) or kwargs,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**kwargs):
        assert kwargs["resolve_skill"] is False
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[
                SimpleNamespace(
                    model_name="kimi-k2.5",
                    usage={"input_tokens": 811, "output_tokens": 66},
                    elapsed_ms=750,
                    kind="selection_resolver",
                ),
            ],
        )

    async def _record_preflight_model_billing(_engine, **kwargs):
        billing_calls.append(kwargs)
        kwargs["ctx"].parent_usage_log_id = 8765
        kwargs["conversation"]["parent_usage_log_id"] = 8765
        return True

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.record_preflight_model_billing",
        _record_preflight_model_billing,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-hidden-activation-billing",
        data=SendHarnessMessageRequest(
            content="生成一个猴子的图片，然后分析下内容",
            skill_selection_mode="auto",
            artifact_mode="image",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert len(billing_calls) == 1
    assert billing_calls[0]["kind"] == "selection_resolver"
    assert billing_calls[0]["model_name"] == "kimi-k2.5"
    assert billing_calls[0]["usage"] == {"input_tokens": 811, "output_tokens": 66}
    assert conversation["parent_usage_log_id"] == 8765
    assert engine_run_calls[0]["conversation"]["parent_usage_log_id"] == 8765
    runtime_state = conversation.get("runtime_state") or {}
    assert runtime_state["runtime_contract"]["internal_hidden_skills"] == [
        {"id": "critique", "activation_source": "ai_resolved"}
    ]


@pytest.mark.asyncio
async def test_send_message_reuses_latched_internal_hidden_skills_without_rerunning_helper_resolution(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []
    helper_resolution_calls: list[dict] = []

    conversation = {
        "id": "conv-hidden-latched",
        "skill_id": "html-ppt",
        "resolved_skill_id": "html-ppt",
        "skill_selection_mode": "auto",
        "skill_resolution_source": "ai_resolved",
        "design_system_id": None,
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
        "runtime_state": {
            "runtime_contract": {
                "internal_hidden_skills": [{"id": "critique", "activation_source": "ai_resolved"}],
            }
        },
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.read_runtime_state",
        lambda *_args, **_kwargs: conversation["runtime_state"],
    )

    persisted_runtime_sessions: list[dict] = []
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        lambda _user_id, _conversation_id, **kwargs: persisted_runtime_sessions.append(kwargs) or kwargs,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**kwargs):
        helper_resolution_calls.append(kwargs)
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-hidden-latched",
        data=SendHarnessMessageRequest(
            content="继续完善这个PPT",
            skill_selection_mode="auto",
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert helper_resolution_calls == []
    assert persisted_runtime_sessions == []
    assert engine_run_calls[0]["conversation"]["runtime_state"]["runtime_contract"]["internal_hidden_skills"] == [
        {"id": "critique", "activation_source": "ai_resolved"}
    ]


@pytest.mark.asyncio
async def test_send_message_reuses_empty_helper_skill_latch_without_rerunning_resolution(monkeypatch):
    user = SimpleNamespace(id=7)
    run_invocations: list[dict] = []
    engine_run_calls: list[dict] = []
    helper_resolution_calls: list[dict] = []

    conversation = {
        "id": "conv-hidden-empty-latched",
        "skill_id": "html-ppt",
        "resolved_skill_id": "html-ppt",
        "skill_selection_mode": "auto",
        "skill_resolution_source": "ai_resolved",
        "design_system_id": None,
        "artifact_mode": "slides",
        "phase": "planning",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
        "runtime_state": {
            "runtime_contract": {
                "internal_hidden_skills": [],
                "internal_hidden_skill_resolution": {
                    "selected_skill_id": "html-ppt",
                    "resolved": True,
                },
            },
            "workspace_runtime_session": {
                "selected_skill": "html-ppt",
                "internal_hidden_skills": [],
                "internal_hidden_skill_resolution": {
                    "selected_skill_id": "html-ppt",
                    "resolved": True,
                },
            },
        },
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.read_runtime_state",
        lambda *_args, **_kwargs: conversation["runtime_state"],
    )

    persisted_runtime_sessions: list[dict] = []
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        lambda _user_id, _conversation_id, **kwargs: persisted_runtime_sessions.append(kwargs) or kwargs,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(conversation),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**kwargs):
        helper_resolution_calls.append(kwargs)
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id="conv-hidden-empty-latched",
        data=SendHarnessMessageRequest(
            content="继续完善这个PPT",
            skill_selection_mode="auto",
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)

    assert helper_resolution_calls == []
    assert persisted_runtime_sessions == []
    assert engine_run_calls[0]["conversation"]["runtime_state"]["runtime_contract"]["internal_hidden_skills"] == []


@pytest.mark.asyncio
async def test_send_message_switching_home_conversation_back_to_auto_clears_latched_skill_and_reruns_resolution(
    monkeypatch,
    tmp_path,
):
    user = SimpleNamespace(id=7)
    updates: list[dict] = []
    persisted_runtime_sessions: list[dict] = []
    run_invocations: list[dict] = []
    resolve_calls: list[dict] = []
    engine_run_calls: list[dict] = []
    _force_artifact_home_turn_route(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(
        user.id,
        title="reset-auto",
        runtime_profile="home",
        skill_id="html-ppt",
        resolved_skill_id="html-ppt",
        skill_selection_mode="manual",
        skill_resolution_source="user_selected",
        artifact_mode="web",
    )
    patch_runtime_state(
        user.id,
        conversation["id"],
        {
            "runtime_contract": {
                "internal_hidden_skills": [{"id": "critique", "activation_source": "ai_resolved"}],
                "internal_hidden_skill_resolution": {
                    "selected_skill_id": "html-ppt",
                    "resolved": True,
                },
            },
            "workspace_runtime_session": {
                "selected_skill": "html-ppt",
                "internal_hidden_skills": [{"id": "critique", "activation_source": "ai_resolved"}],
                "internal_hidden_skill_resolution": {
                    "selected_skill_id": "html-ppt",
                    "resolved": True,
                },
            },
        },
        touch_updated_at=False,
    )

    from app.services.agent_harness.runtime.state import runtime_projection_store as runtime_store_module
    from app.services.agent_harness.workspace.conversation import (
        conversation_meta_store as meta_store_module,
    )

    original_update_conversation = meta_store_module.update_conversation
    original_persist_runtime_session = runtime_store_module.persist_runtime_session

    def _recording_update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        return original_update_conversation(_user_id, _conversation_id, **kwargs)

    def _recording_persist_runtime_session(_user_id, _conversation_id, **kwargs):
        persisted_runtime_sessions.append(kwargs)
        return original_persist_runtime_session(_user_id, _conversation_id, **kwargs)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _recording_update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        _recording_persist_runtime_session,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        run_invocations.append({
            "conversation_snapshot": dict(get_conversation(_user_id, _conversation_id) or {}),
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    async def _resolve_selection(**kwargs):
        resolve_calls.append(kwargs)
        if kwargs["resolve_skill"]:
            return SimpleNamespace(
                skill=SimpleNamespace(
                    id="saas-landing",
                    confidence=0.92,
                    reasoning_summary="Reset to auto should choose a fresh landing skill.",
                    should_replace_current=True,
                ),
                internal_skill_ids=["critique"],
                design_system_recommendations=[],
                preflight_model_calls=[],
            )
        return SimpleNamespace(
            skill=None,
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    class _FakeEngine:
        def __init__(self, _user_id):
            self.run_calls = []

        async def run(self, **kwargs):
            self.run_calls.append(kwargs)
            engine_run_calls.append(kwargs)
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", _FakeEngine)

    await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(
            content="做一个设计公司的落地页",
            skill_selection_mode="auto",
            artifact_mode="web",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )
    await _drain_started_runs(run_invocations)
    stored = get_conversation(user.id, conversation["id"])

    assert any(
        item.get("skill_selection_mode") == "auto"
        and item.get("skill_id") is None
        and item.get("resolved_skill_id") is None
        for item in updates
    )
    assert resolve_calls[0]["resolve_skill"] is True
    assert resolve_calls[0]["current_skill_id"] is None
    assert stored is not None
    assert stored["skill_id"] == "saas-landing"
    assert stored["skill_selection_mode"] == "auto"
    assert engine_run_calls[0]["conversation"]["skill_id"] == "saas-landing"
    assert engine_run_calls[0]["conversation"]["skill_selection_mode"] == "auto"


@pytest.mark.asyncio
async def test_send_message_returns_409_without_resolving_skills_when_remote_worker_already_claimed_run(
    monkeypatch,
    tmp_path,
):
    

    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    user = SimpleNamespace(id=7)
    resolve_calls: list[dict] = []
    persisted_runtime_sessions: list[dict] = []
    updates: list[dict] = []

    conversation = create_conversation(
        user.id,
        title="remote-owner-send-message",
        runtime_profile="home",
        skill_selection_mode="auto",
        artifact_mode="web",
    )

    from app.services.agent_harness.workspace.conversation import (
        conversation_meta_store as meta_store_module,
    )

    original_update_conversation = meta_store_module.update_conversation

    def _recording_update_conversation(_user_id, _conversation_id, **kwargs):
        updates.append(kwargs)
        return original_update_conversation(_user_id, _conversation_id, **kwargs)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        _recording_update_conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.active_run_guard.has_active_agent_run",
        lambda _conversation_id: True,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.runtime_projection_store.persist_runtime_session",
        lambda _user_id, _conversation_id, **kwargs: persisted_runtime_sessions.append(kwargs) or kwargs,
    )

    async def _resolve_selection(**kwargs):
        resolve_calls.append(kwargs)
        return SimpleNamespace(
            skill=SimpleNamespace(
                id="saas-landing",
                confidence=0.91,
                reasoning_summary="Should never be used when a remote owner already claimed the run.",
                should_replace_current=True,
            ),
            internal_skill_ids=["critique"],
            design_system_recommendations=[],
            preflight_model_calls=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.send_message(
            conversation_id=conversation["id"],
            data=SendHarnessMessageRequest(
                content="做一个设计公司的落地页",
                skill_selection_mode="auto",
                artifact_mode="web",
            ),
            request=SimpleNamespace(headers={}),
            db=object(),
            user=user,
        )

    stored = get_conversation(user.id, conversation["id"])
    snapshot = build_conversation_detail_snapshot(user.id, conversation["id"])

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Conversation already has an active run"
    assert resolve_calls == []
    assert persisted_runtime_sessions == []
    assert all(
        set(item.keys()).issubset({"web_search_enabled", "language", "turn_route", "activity", "phase"})
        for item in updates
    ), updates
    assert stored is not None
    assert stored["skill_id"] is None
    assert stored["resolved_skill_id"] is None
    assert stored["skill_selection_mode"] == "auto"
    assert stored["runtime_status"] == "idle"
    assert snapshot is not None
    assert snapshot["interaction_profile"] == "home_blocking_preflight"


@pytest.mark.asyncio
async def test_send_message_persists_user_turn_and_terminal_error_when_internal_skill_preflight_fails(
    monkeypatch,
):
    user = SimpleNamespace(id=7)
    conversation = create_conversation(
        user.id,
        title="internal-skill-preflight-failure",
        skill_id="html-ppt",
        resolved_skill_id="html-ppt",
        skill_resolution_source="user_selected",
        skill_selection_mode="manual",
        artifact_mode="slides",
        mode="fast",
        web_search_enabled=True,
    )

    async def _resolve_selection(**kwargs):
        assert kwargs["resolve_skill"] is False
        raise RuntimeError("No available channel for model gemini-3.1-pro-preview")

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_selection",
        _resolve_selection,
    )

    response = await harness_endpoint.send_message(
        conversation_id=conversation["id"],
        data=SendHarnessMessageRequest(
            content="hello",
            skill_selection_mode="manual",
            artifact_mode="slides",
        ),
        request=SimpleNamespace(headers={}),
        db=object(),
        user=user,
    )

    streamed_chunks: list[str] = []
    async for chunk in response.body_iterator:
        streamed_chunks.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))

    stored = get_conversation(user.id, conversation["id"])
    assert stored is not None
    assert stored["runtime_status"] == "failed"
    assert stored["last_error_summary"] == "No available channel for model gemini-3.1-pro-preview"

    snapshot = build_conversation_detail_snapshot(user.id, conversation["id"])
    assert snapshot is not None
    assert [message["role"] for message in snapshot["messages"]] == ["user", "assistant"]
    assert snapshot["messages"][0]["content"] == "hello"
    assistant_blocks = snapshot["messages"][1].get("blocks") or []
    error_block = next(block for block in assistant_blocks if block.get("ui_kind") == "error_card")
    assert error_block["payload"]["message"] == "No available channel for model gemini-3.1-pro-preview"
    assert any("turn_completed" in chunk for chunk in streamed_chunks)


@pytest.mark.asyncio
async def test_send_message_text_path_blocks_on_home_turn_classifier_before_starting_run(monkeypatch):
    """Confirms hypothesis #2 end-to-end.

    For a user_text_message payload, send_harness_message awaits
    route_home_text_turn before reaching _build_live_streaming_response, which
    is what eventually calls start_conversation_run. If the classifier hangs
    (slow model, cold start, timeout), the POST /messages handler hangs too —
    no SSE bytes are sent to the client during that window, even though the
    backend will eventually run the turn to completion. From the user's
    perspective the second message appears to "disconnect" until the
    classifier returns and the run kicks off.

    This test pins the ordering: while the classifier is gated, no
    start_conversation_run call has been issued.
    """
    user = SimpleNamespace(id=7)
    start_run_calls: list[dict] = []
    classifier_invocations: list[dict] = []
    conversation = {
        "id": "conv-home-classifier-gate",
        "runtime_profile": "home",
        "skill_id": None,
        "resolved_skill_id": None,
        "skill_selection_mode": "auto",
        "design_system_id": None,
        "artifact_mode": "web",
        "phase": "executing",
        "plan_state": None,
        "model_preferences": None,
        "web_search_enabled": True,
        "runtime_status": "completed",
        "run_state": "completed",
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda _user_id, _conversation_id, **kwargs: conversation.update(kwargs) or conversation,
    )

    def _start_conversation_run(_user_id, _conversation_id, producer_factory):
        start_run_calls.append({
            "conversation_id": _conversation_id,
            "producer_factory": producer_factory,
        })
        return None

    monkeypatch.setattr(
        _runtime_capture,
        "start_conversation_run",
        _start_conversation_run,
        raising=False,
    )

    class _FakeEngine:
        async def run(self, **_kwargs):
            if False:
                yield None

    monkeypatch.setattr(_runtime_capture, "_test_engine_factory", lambda _user_id: _FakeEngine())

    gate = asyncio.Event()

    async def _gated_route_home_text_turn(*, conversation, content, attachments=None, **_kwargs):
        classifier_invocations.append({"content": content, "artifact_mode": conversation.get("artifact_mode")})
        await gate.wait()
        return {
            "route_kind": "informational_turn",
            "source": "classifier",
            "confidence": 0.92,
            "requires_plan_gate": False,
            "requires_skill_selection": False,
            "requires_design_system_selection": False,
            "activity": "answering",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.home_turn_router.route_home_text_turn",
        _gated_route_home_text_turn,
    )

    send_task = asyncio.create_task(
        harness_endpoint.send_message(
            conversation_id="conv-home-classifier-gate",
            data=SendHarnessMessageRequest(content="第二次：搜索下黑格尔的生平"),
            request=SimpleNamespace(headers={}),
            db=object(),
            user=user,
        )
    )

    # Let the handler reach the gated classifier.
    await asyncio.sleep(0)
    assert classifier_invocations, "classifier should have been invoked before sending SSE"

    # While the classifier is still awaiting, the POST has not produced a
    # StreamingResponse, and start_conversation_run has not been invoked.
    # asyncio.shield + wait_for proves we are truly stuck, not just
    # cooperatively yielding.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(send_task), timeout=0.05)
    assert not send_task.done()
    assert start_run_calls == [], (
        "start_conversation_run must not be invoked until route_home_text_turn returns"
    )

    # Release the classifier; now the handler completes and the run starts.
    gate.set()
    response = await send_task
    assert response is not None
    # body_iterator triggers the run's producer once consumed; but the call to
    # start_conversation_run itself happens inside _build_live_streaming_response
    # synchronously, so it should already be recorded.
    assert len(start_run_calls) == 1
    assert start_run_calls[0]["conversation_id"] == "conv-home-classifier-gate"



