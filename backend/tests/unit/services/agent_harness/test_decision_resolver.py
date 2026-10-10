from __future__ import annotations

import json

import pytest

from app.services.agent_harness.catalog import SkillSummary
from app.services.agent_harness.authoring.planning import decision_resolver


@pytest.fixture(autouse=True)
def _planning_user_key(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.decision_resolver.resolve_user_apimart_key_for_context",
        AsyncMock(return_value="test-key"),
    )


def _skill_summary(
    skill_id: str,
    *,
    name: str,
    description: str,
    triggers: list[str] | None = None,
    artifact_mode: str | None = "web",
    featured: int | None = None,
    capabilities: dict | None = None,
) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name=name,
        name_en=name,
        name_zh=name,
        description=description,
        description_en=description,
        description_zh=description,
        icon="",
        color="",
        triggers=list(triggers or []),
        mode="prototype",
        surface="web",
        platform=None,
        scenario=None,
        artifact_mode=artifact_mode,
        default_for=[],
        featured=featured,
        preview_type="html",
        preview_entry=None,
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider="open_design",
        protocol_family="open_design_free_web",
        protocol_metadata={},
        capabilities={
            "selection_enabled": True,
            "phase_enabled": True,
            **dict(capabilities or {}),
        },
        example_prompt=None,
        has_example_html=False,
    )


def _patch_skill_summaries(monkeypatch, skills: list[SkillSummary] | None = None) -> None:
    async def _read_skill_summaries():
        return skills or [
            _skill_summary(
                "web",
                name="Web",
                description="Build web artifacts.",
                triggers=["web"],
                featured=1,
            )
        ]

    monkeypatch.setattr(decision_resolver, "read_skill_summaries", _read_skill_summaries)


@pytest.mark.asyncio
async def test_call_selection_model_accepts_openai_function_tool_call(monkeypatch):
    class _Chunk:
        usage = {"input_tokens": 10, "output_tokens": 4}
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "resolve_selection",
                    "arguments": json.dumps(
                        {
                            "skill": {
                                "id": "web",
                                "confidence": 0.9,
                                "reasoning_summary": "Best fit.",
                                "should_replace_current": False,
                            },
                            "internal_skill_ids": ["critique"],
                        }
                    ),
                },
            }
        ]
        content = None

    class _Provider:
        async def chat_stream(self, **kwargs):
            yield _Chunk()

    monkeypatch.setattr(decision_resolver, "create_harness_model_provider", lambda api_key: _Provider())

    result = await decision_resolver._call_selection_model(  # noqa: SLF001
        system_prompt="Resolve.",
        user_prompt="{}",
        model_name="configured-model",
                       api_key="test-key",
    )

    assert result.decision is not None
    assert result.decision.skill is not None
    assert result.decision.skill.id == "web"
    assert result.decision.internal_skill_ids == ["critique"]


@pytest.mark.asyncio
async def test_resolve_selection_includes_runtime_time_in_prompt(monkeypatch):
    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        payload = json.loads(user_prompt)
        assert "runtime_time" in payload
        assert payload["runtime_time"]["current_date"]
        assert payload["runtime_time"]["timezone"]
        assert "Use the provided runtime time context" in system_prompt
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate(  # noqa: SLF001
                {
                    "skill": {
                        "id": None,
                        "confidence": 0.0,
                        "reasoning_summary": "",
                        "should_replace_current": False,
                    }
                }
            ),
            usage={"input_tokens": 12, "output_tokens": 3},
            elapsed_ms=45,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(monkeypatch)
    result = await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="今天想做一个落地页",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert result.skill is not None
    assert result.preflight_model_calls is not None
    assert result.preflight_model_calls[0].kind == "selection_resolver"


@pytest.mark.asyncio
async def test_resolve_selection_persists_prompt_bundle_trace_when_context_is_provided(monkeypatch):
    traces: list[dict] = []

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate({"skill": None}),  # noqa: SLF001
            usage={"input_tokens": 6, "output_tokens": 1},
            elapsed_ms=12,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(monkeypatch)
    monkeypatch.setattr(
        decision_resolver,
        "persist_prompt_bundle_trace",
        lambda user_id, conversation_id, run_id, bundle, summary=None: traces.append(
            {"user_id": user_id, "conversation_id": conversation_id, "run_id": run_id, "trace_type": "prompt_bundle_assembled", "payload": bundle.trace, "summary": summary}
        ),
    )

    await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="做一个落地页",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
        user_id=7,
        conversation_id="conv-side",
        run_id="run-side-1",
    )

    assert traces
    assert traces[0]["trace_type"] == "prompt_bundle_assembled"
    assert traces[0]["payload"]["mode"] == "skill_selection"


@pytest.mark.asyncio
async def test_resolve_selection_returns_skill_only_and_records_single_preflight_call(monkeypatch):
    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate(  # noqa: SLF001
                {
                    "skill": {
                        "id": "saas-landing",
                        "confidence": 0.9,
                        "reasoning_summary": "Landing-page request benefits from the landing-page skill.",
                        "should_replace_current": True,
                    }
                }
            ),
            usage={"input_tokens": 14, "output_tokens": 4},
            elapsed_ms=52,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(
        monkeypatch,
        [
            _skill_summary(
                "saas-landing",
                name="SaaS Landing",
                description="Design a SaaS landing page.",
                triggers=["landing"],
                featured=2,
            )
        ],
    )

    result = await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="做一个设计公司的落地页",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert result.skill is not None
    assert result.skill.id == "saas-landing"
    assert result.design_system_recommendations == []
    assert result.preflight_model_calls is not None
    assert [call.kind for call in result.preflight_model_calls] == ["selection_resolver"]


@pytest.mark.asyncio
async def test_resolve_selection_model_failure_returns_defaultable_empty_decision(monkeypatch):
    async def _failing_call(*, system_prompt: str, user_prompt: str, model_name: str):
        raise RuntimeError("selection model unavailable")

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _failing_call)
    _patch_skill_summaries(monkeypatch)

    result = await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="生成一个设计公司的落地页",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert result.skill is not None
    assert result.skill.id is None
    assert result.skill.confidence == 0.0
    assert result.preflight_model_calls is not None
    assert [call.kind for call in result.preflight_model_calls] == ["selection_resolver"]


@pytest.mark.asyncio
async def test_resolve_selection_includes_non_entry_mode_candidates(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        captured["user_prompt"] = json.loads(user_prompt)
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate(  # noqa: SLF001
                {
                    "skill": {
                        "id": "pricing-page",
                        "confidence": 0.8,
                        "reasoning_summary": "Landing-page request benefits from pricing-page.",
                        "should_replace_current": True,
                    }
                }
            ),
            usage={"input_tokens": 10, "output_tokens": 2},
            elapsed_ms=31,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(
        monkeypatch,
        [
            _skill_summary(
                "pricing-page",
                name="Pricing Page",
                description="Design a pricing page.",
                triggers=["pricing"],
                featured=2,
            ),
            _skill_summary(
                "critique",
                name="Critique",
                description="Review and critique the draft.",
                triggers=["critique", "review"],
                artifact_mode=None,
                capabilities={
                    "helper_eligible": True,
                    "rollout_state": "loaded_hidden",
                    "semantic_kind": "functional",
                },
            )
        ],
    )

    result = await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="做一个包含定价区块的落地页",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert result.skill is not None
    assert result.skill.id == "pricing-page"
    assert captured["user_prompt"]["skill_candidates"] == [
        {
            "id": "pricing-page",
            "name": "Pricing Page",
            "description": "Design a pricing page.",
            "triggers": ["pricing"],
        }
    ]
    assert captured["user_prompt"]["internal_skill_candidates"] == [
        {
            "id": "critique",
            "name": "Critique",
            "description": "Review and critique the draft.",
            "triggers": ["critique", "review"],
        }
    ]


@pytest.mark.asyncio
async def test_resolve_selection_uses_policy_helper_eligibility_for_internal_candidates(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        captured["user_prompt"] = json.loads(user_prompt)
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate({"skill": None}),  # noqa: SLF001
            usage={"input_tokens": 10, "output_tokens": 2},
            elapsed_ms=31,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(
        monkeypatch,
        [
            _skill_summary(
                "policy-helper",
                name="Policy Helper",
                description="Assist selected artifact workflows.",
                triggers=["assist"],
                artifact_mode=None,
                capabilities={
                    "helper_eligible": True,
                    "rollout_state": "loaded_hidden",
                    "semantic_kind": "unclassified",
                },
            ),
            _skill_summary(
                "functional-but-not-helper",
                name="Functional Hidden",
                description="Should not be offered as a helper.",
                triggers=["hidden"],
                artifact_mode=None,
                capabilities={
                    "helper_eligible": False,
                    "rollout_state": "loaded_hidden",
                    "semantic_kind": "functional",
                },
            ),
        ],
    )

    await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="需要 assist 当前稿件",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert captured["user_prompt"]["internal_skill_candidates"] == [
        {
            "id": "policy-helper",
            "name": "Policy Helper",
            "description": "Assist selected artifact workflows.",
            "triggers": ["assist"],
        }
    ]


@pytest.mark.asyncio
async def test_resolve_selection_returns_internal_hidden_skill_ids(monkeypatch):
    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        return decision_resolver._ResolverModelResult(  # noqa: SLF001
            decision=decision_resolver._ResolverToolInput.model_validate(  # noqa: SLF001
                {
                    "skill": {
                        "id": "saas-landing",
                        "confidence": 0.9,
                        "reasoning_summary": "Landing-page request benefits from the landing-page skill.",
                        "should_replace_current": True,
                    },
                    "internal_skill_ids": ["critique", "unknown-hidden"],
                }
            ),
            usage={"input_tokens": 12, "output_tokens": 3},
            elapsed_ms=45,
        )

    monkeypatch.setattr(decision_resolver, "_call_selection_model", _fake_call)
    _patch_skill_summaries(
        monkeypatch,
        [
            _skill_summary(
                "saas-landing",
                name="SaaS Landing",
                description="Design a SaaS landing page.",
                triggers=["landing"],
                featured=2,
            ),
            _skill_summary(
                "critique",
                name="Critique",
                description="Review and critique the draft.",
                triggers=["critique", "review"],
                artifact_mode=None,
                capabilities={
                    "helper_eligible": True,
                    "rollout_state": "loaded_hidden",
                    "semantic_kind": "functional",
                },
            )
        ],
    )

    result = await decision_resolver.resolve_selection(
        artifact_mode="web",
        prompt="做一个设计公司的落地页，并顺便点评当前草稿",
        attachments=None,
        current_skill_id=None,
        resolve_skill=True,
        model_preferences={"multimodal_model": "gpt-4.1"},
    )

    assert result.skill is not None
    assert result.skill.id == "saas-landing"
    assert result.internal_skill_ids == ["critique"]
