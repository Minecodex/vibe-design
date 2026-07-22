from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.schemas.harness import CreateHarnessConversationRequest


@pytest.mark.asyncio
async def test_create_harness_conversation_rejects_unknown_skill(monkeypatch):
    user = SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.create_conversation(
            data=CreateHarnessConversationRequest(skill_id="ppt", mode="fast"),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Unknown harness skill: ppt"


@pytest.mark.asyncio
async def test_create_harness_conversation_rejects_deferred_template_skill(monkeypatch):
    user = SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "imported_design_template": True,
                "template_support_state": "deferred",
                "template_deferred_reason": "complex_external_workflow",
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.create_conversation(
            data=CreateHarnessConversationRequest(skill_id="live-artifact", mode="fast"),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert "deferred imported template" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_harness_conversation_rejects_phase_disabled_skill(monkeypatch):
    user = SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "phase_enabled": False,
                "classification_notes": "phase_one_disabled",
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.create_conversation(
            data=CreateHarnessConversationRequest(skill_id="hyperframes", mode="fast"),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert "not enabled" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_harness_conversation_accepts_known_skill(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "phase_enabled": True,
                "canvas_explicit": False,
            },
        ),
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-1",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "phase": "planning" if kwargs["skill_id"] else "executing",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )

    result = await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(skill_id="pptx", mode="fast"),
        db=object(),
        user=user,
    )

    assert captured["skill_id"] == "pptx"
    assert captured["skill_selection_mode"] == "manual"
    assert captured["design_system_id"] is None
    assert result["skill_id"] == "pptx"
    assert result["phase"] == "planning"
    assert result["interaction_profile"] == "home_blocking_preflight"


@pytest.mark.asyncio
async def test_create_harness_conversation_persists_design_system_id(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "phase_enabled": True,
                "canvas_explicit": skill_id == "vi-design-guide",
            },
        ),
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-1",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "phase": "planning" if kwargs["skill_id"] else "executing",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_design_system_summary_sync",
        lambda design_system_id: SimpleNamespace(id=design_system_id) if design_system_id == "atelier-zero" else None,
    )

    await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(
            skill_id="pptx",
            mode="fast",
            design_system_id="atelier-zero",
        ),
        db=object(),
        user=user,
    )

    assert captured["design_system_id"] == "atelier-zero"


@pytest.mark.asyncio
async def test_create_harness_conversation_rejects_unknown_design_system(monkeypatch):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "phase_enabled": True,
                "canvas_explicit": False,
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_design_system_summary_sync",
        lambda design_system_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.create_conversation(
            data=CreateHarnessConversationRequest(
                skill_id="pptx",
                mode="fast",
                design_system_id="missing-system",
            ),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Unknown design system: missing-system"


@pytest.mark.asyncio
async def test_create_harness_canvas_conversation_defaults_design_workflow(monkeypatch):
    user = SimpleNamespace(id=9)
    captured: dict[str, object] = {}
    async def _allow_canvas_project(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.skills.get_skill",
        lambda skill_id: SimpleNamespace(id=skill_id),
    )
    monkeypatch.setattr(harness_endpoint, "_validate_harness_skill_id", lambda skill_id: skill_id)
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_capabilities",
        lambda skill_id: {
            "phase_enabled": True,
            "canvas_explicit": skill_id == "vi-design-guide",
        },
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_artifact_mode",
        lambda skill_id: "web",
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-canvas-1",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "phase": "executing",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "runtime_profile": kwargs["runtime_profile"],
            "project_id": kwargs["project_id"],
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )
    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)

    result = await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(
            mode="fast",
            runtime_profile="canvas",
            project_id=18,
        ),
        db=object(),
        user=user,
    )

    assert captured["runtime_profile"] == "canvas"
    assert captured["project_id"] == 18
    assert captured["skill_id"] == "design_workflow"
    assert captured["skill_selection_mode"] == "auto"
    assert result["skill_id"] == "design_workflow"
    assert result["runtime_profile"] == "canvas"
    assert result["interaction_profile"] == "canvas_live_interaction"
    assert result["project_id"] == 18


@pytest.mark.asyncio
async def test_create_harness_canvas_conversation_rejects_invalid_explicit_skill(monkeypatch):
    user = SimpleNamespace(id=7)
    async def _allow_canvas_project(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            capabilities={
                "phase_enabled": True,
                "canvas_explicit": False,
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.catalog.list_skill_summaries_sync",
        lambda: [
            SimpleNamespace(
                id="vi-design-guide",
                capabilities={
                    "phase_enabled": True,
                    "canvas_explicit": True,
                },
            )
        ],
    )
    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.create_conversation(
            data=CreateHarnessConversationRequest(
                mode="fast",
                runtime_profile="canvas",
                project_id=11,
                skill_id="pptx",
            ),
            db=object(),
            user=user,
        )

    assert exc_info.value.status_code == 422
    assert "Canvas harness skill must be one of" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_harness_canvas_conversation_accepts_policy_explicit_skill(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}

    async def _allow_canvas_project(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.skills.get_skill",
        lambda skill_id: SimpleNamespace(
            id=skill_id,
            runtime_capabilities={
                "phase_enabled": True,
                "canvas_explicit": skill_id == "custom-canvas-skill",
            },
        ),
    )
    monkeypatch.setattr(harness_endpoint, "_validate_harness_skill_id", lambda skill_id: skill_id)
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_capabilities",
        lambda skill_id: {
            "phase_enabled": True,
            "canvas_explicit": skill_id == "custom-canvas-skill",
        },
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_artifact_mode",
        lambda skill_id: "web",
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-canvas-custom",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "phase": "planning",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "runtime_profile": kwargs["runtime_profile"],
            "project_id": kwargs["project_id"],
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )
    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)

    result = await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(
            mode="fast",
            runtime_profile="canvas",
            project_id=11,
            skill_id="custom-canvas-skill",
        ),
        db=object(),
        user=user,
    )

    assert captured["skill_id"] == "custom-canvas-skill"
    assert captured["skill_selection_mode"] == "manual"
    assert result["skill_id"] == "custom-canvas-skill"


@pytest.mark.asyncio
async def test_create_harness_canvas_product_hero_infers_image_artifact_mode(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}

    async def _allow_canvas_project(*_args, **_kwargs):
        return None

    def _skill_summary(skill_id):
        return SimpleNamespace(
            id=skill_id,
            artifact_mode="image" if skill_id == "menswear-ecommerce-hero" else "web",
            capabilities={
                "phase_enabled": True,
                "canvas_explicit": skill_id == "menswear-ecommerce-hero",
            },
        )

    monkeypatch.setattr(
        "app.services.agent_harness.catalog.get_skill_summary_sync",
        _skill_summary,
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-canvas-product",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "artifact_mode": kwargs["artifact_mode"],
            "phase": "executing",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "runtime_profile": kwargs["runtime_profile"],
            "project_id": kwargs["project_id"],
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )
    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)

    result = await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(
            mode="fast",
            runtime_profile="canvas",
            project_id=11,
            skill_id="menswear-ecommerce-hero",
        ),
        db=object(),
        user=user,
    )

    assert captured["skill_id"] == "menswear-ecommerce-hero"
    assert captured["skill_selection_mode"] == "manual"
    assert captured["skill_resolution_source"] == "user_selected"
    assert captured["artifact_mode"] == "image"
    assert result["artifact_mode"] == "image"


@pytest.mark.asyncio
async def test_create_harness_canvas_conversation_accepts_vi_design_guide(monkeypatch):
    user = SimpleNamespace(id=7)
    captured: dict[str, object] = {}

    async def _allow_canvas_project(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.skills.get_skill",
        lambda skill_id: SimpleNamespace(id=skill_id),
    )
    monkeypatch.setattr(harness_endpoint, "_validate_harness_skill_id", lambda skill_id: skill_id)
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_capabilities",
        lambda skill_id: {
            "phase_enabled": True,
            "canvas_explicit": skill_id == "vi-design-guide",
        },
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_get_harness_skill_artifact_mode",
        lambda skill_id: "web",
    )

    def _create_harness_conv(**kwargs):
        captured.update(kwargs)
        return {
            "id": "conv-canvas-vi",
            "title": "新会话",
            "skill_id": kwargs["skill_id"],
            "phase": "planning",
            "mode": kwargs["mode"],
            "status": "active",
            "runtime_status": "idle",
            "engine_version": "harness",
            "runtime_profile": kwargs["runtime_profile"],
            "project_id": kwargs["project_id"],
            "run_id": None,
            "started_at": None,
            "finished_at": None,
            "user_interaction": None,
            "created_at": "2026-04-19T00:00:00Z",
            "updated_at": "2026-04-19T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.create_conversation",
        _create_harness_conv,
    )
    monkeypatch.setattr(harness_endpoint, "_require_canvas_project_access", _allow_canvas_project)

    result = await harness_endpoint.create_conversation(
        data=CreateHarnessConversationRequest(
            mode="fast",
            runtime_profile="canvas",
            project_id=11,
            skill_id="vi-design-guide",
        ),
        db=object(),
        user=user,
    )

    assert captured["runtime_profile"] == "canvas"
    assert captured["project_id"] == 11
    assert captured["skill_id"] == "vi-design-guide"
    assert captured["skill_selection_mode"] == "manual"
    assert result["skill_id"] == "vi-design-guide"
