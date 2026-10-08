from __future__ import annotations

import json

import pytest

from app.services.agent_harness.catalog import DesignSystemSummary
from app.services.agent_harness.authoring.planning import design_system_selection_resolver as resolver


@pytest.fixture(autouse=True)
def _planning_user_key(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.planning.design_system_selection_resolver.resolve_user_apimart_key_for_context",
        AsyncMock(return_value="test-key"),
    )


def _fake_design_system(index: int) -> DesignSystemSummary:
    return DesignSystemSummary(
        id=f"system-{index:02d}",
        title=f"Design System Inspired by System {index:02d}",
        description=f"Category: Product & SaaS {index:02d}",
        category="Product & SaaS",
        palette=["#111111", "#FFFFFF"],
        sections=["Color", "Typography"],
        preview=None,
        featured=index + 1,
        is_default=index == 0,
        resolver_summary=f"system-{index:02d} summary",
        resolver_tags=["product", "structured"],
        preferred_for=["landing-page", "product-page"],
        avoid_for=[],
        tone="professional",
        density="balanced",
    )


def test_build_recalled_candidates_limits_results_to_top_thirty():
    systems = [_fake_design_system(index) for index in range(35)]

    recalled = resolver._build_recalled_candidates(  # noqa: SLF001
        design_systems=systems,
        artifact_mode="slides",
        prompt="做一个品牌设计趋势分享PPT",
        discovery_brief={
            "output": "品牌趋势演示文稿",
            "audience": "客户/甲方",
            "tone": "professional_restrained",
        },
        skill=None,
    )

    assert len(recalled) == 30
    assert recalled[0].id == "system-00"
    assert recalled[-1].id == "system-29"


@pytest.mark.asyncio
async def test_call_design_system_selection_model_uses_configured_model_max_tokens(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, int] = {}

    class _Chunk:
        usage = {"input_tokens": 10, "output_tokens": 4}
        tool_calls = [
            {
                "name": "recommend_design_systems",
                "arguments": {
                    "recommendations": [
                        {"id": "system-01", "confidence": 0.9, "reasoning_summary": "Best fit."},
                    ],
                },
            }
        ]
        content = None

    class _Provider:
        async def chat_stream(self, **kwargs):
            captured["max_tokens"] = kwargs["max_tokens"]
            yield _Chunk()

    monkeypatch.setattr(resolver, "resolve_effective_max_tokens", lambda model_name, requested: 4096)
    monkeypatch.setattr(resolver, "create_harness_model_provider", lambda api_key: _Provider())

    result = await resolver._call_design_system_selection_model(  # noqa: SLF001
        system_prompt="Pick candidates.",
        user_prompt="{}",
        model_name="configured-model",
                       api_key="test-key",
    )

    assert captured["max_tokens"] == 4096
    assert result.decision is not None
    assert result.decision.recommendations[0].id == "system-01"


@pytest.mark.asyncio
async def test_call_design_system_selection_model_accepts_openai_function_tool_call(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Chunk:
        usage = {"input_tokens": 10, "output_tokens": 4}
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "recommend_design_systems",
                    "arguments": json.dumps(
                        {
                            "recommendations": [
                                {"id": "system-02", "confidence": 0.91, "reasoning_summary": "Strong fit."},
                            ],
                        }
                    ),
                },
            }
        ]
        content = None

    class _Provider:
        async def chat_stream(self, **kwargs):
            yield _Chunk()

    monkeypatch.setattr(resolver, "create_harness_model_provider", lambda api_key: _Provider())

    result = await resolver._call_design_system_selection_model(  # noqa: SLF001
        system_prompt="Pick candidates.",
        user_prompt="{}",
        model_name="configured-model",
                       api_key="test-key",
    )

    assert result.decision is not None
    assert result.decision.recommendations[0].id == "system-02"


@pytest.mark.asyncio
async def test_resolve_design_system_selection_sends_thirty_candidates_and_returns_six(monkeypatch: pytest.MonkeyPatch):
    systems = [_fake_design_system(index) for index in range(35)]

    async def _read_design_system_summaries():
        return systems

    monkeypatch.setattr(resolver, "read_design_system_summaries", _read_design_system_summaries)

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        payload = json.loads(user_prompt)
        candidate_ids = [item["id"] for item in payload["design_system_candidates"]]

        assert "Choose exactly six design systems" in system_prompt
        assert len(candidate_ids) == 30
        assert candidate_ids[0] == "system-00"
        assert candidate_ids[-1] == "system-29"

        return resolver._ResolverModelResult(  # noqa: SLF001
            decision=resolver._RecommendationToolInput.model_validate(  # noqa: SLF001
                {
                    "recommendations": [
                        {"id": "system-03", "confidence": 0.95, "reasoning_summary": "Best primary fit."},
                        {"id": "system-07", "confidence": 0.9, "reasoning_summary": "Strong alternative."},
                        {"id": "system-11", "confidence": 0.86, "reasoning_summary": "Good editorial fallback."},
                        {"id": "system-13", "confidence": 0.82, "reasoning_summary": "Balanced option."},
                        {"id": "system-17", "confidence": 0.78, "reasoning_summary": "Good structured choice."},
                        {"id": "system-19", "confidence": 0.74, "reasoning_summary": "Useful backup."},
                    ]
                }
            ),
            usage={"input_tokens": 120, "output_tokens": 32},
            elapsed_ms=245,
        )

    monkeypatch.setattr(resolver, "_call_design_system_selection_model", _fake_call)

    result = await resolver.resolve_design_system_selection(
        artifact_mode="slides",
        prompt="生成一份给客户看的设计趋势PPT",
        discovery_brief={
            "output": "设计趋势PPT",
            "audience": "客户/甲方",
            "tone": "professional_restrained",
        },
        skill_id=None,
        model_preferences={"multimodal_model": "kimi-k2.5"},
    )

    assert [item.id for item in result.recommendations] == [
        "system-03",
        "system-07",
        "system-11",
        "system-13",
        "system-17",
        "system-19",
    ]
    assert [item.rank for item in result.recommendations] == [1, 2, 3, 4, 5, 6]
    assert result.model_name == "kimi-k2.5"
    assert result.usage == {"input_tokens": 120, "output_tokens": 32}
    assert result.elapsed_ms == 245


@pytest.mark.asyncio
async def test_resolve_design_system_selection_persists_prompt_bundle_trace(monkeypatch: pytest.MonkeyPatch):
    systems = [_fake_design_system(index) for index in range(3)]
    traces: list[dict] = []

    async def _read_design_system_summaries():
        return systems

    monkeypatch.setattr(resolver, "read_design_system_summaries", _read_design_system_summaries)
    monkeypatch.setattr(
        resolver,
        "persist_prompt_bundle_trace",
        lambda user_id, conversation_id, run_id, bundle, summary=None: traces.append(
            {"user_id": user_id, "conversation_id": conversation_id, "run_id": run_id, "trace_type": "prompt_bundle_assembled", "payload": bundle.trace, "summary": summary}
        ),
    )

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, api_key: str = ""):
        return resolver._ResolverModelResult(  # noqa: SLF001
            decision=resolver._RecommendationToolInput.model_validate({"recommendations": []}),  # noqa: SLF001
            usage={"input_tokens": 8, "output_tokens": 2},
            elapsed_ms=20,
        )

    monkeypatch.setattr(resolver, "_call_design_system_selection_model", _fake_call)

    await resolver.resolve_design_system_selection(
        artifact_mode="web",
        prompt="生成产品页",
        discovery_brief={},
        model_preferences={"multimodal_model": "gpt-4.1"},
        user_id=7,
        conversation_id="conv-ds",
        run_id="run-ds-1",
    )

    assert traces
    assert traces[0]["trace_type"] == "prompt_bundle_assembled"
    assert traces[0]["payload"]["mode"] == "design_system_selection"
