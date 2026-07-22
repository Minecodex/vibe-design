from pathlib import Path

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner


def test_harness_billing_summary_tracks_image_analysis_separately(tmp_path: Path):
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        workspace_root=tmp_path,
        skill_id="pptx",
    )

    ctx.record_billing(
        category="multimodal",
        amount=2,
        detail={"model_name": "kimi-k2.5", "elapsed_ms": 1200},
    )
    ctx.record_billing(
        category="image_analysis",
        amount=3,
        detail={"model_name": "gemini-3.1-pro-preview", "elapsed_ms": 800},
    )

    summary = ctx.build_billing_summary()

    assert summary["multimodal_calls"] == 1
    assert summary["image_analysis_calls"] == 1
    assert summary["multimodal_models"] == ["kimi-k2.5"]
    assert summary["image_analysis_models"] == ["gemini-3.1-pro-preview"]
    assert summary["multimodal_model_stats"] == [
        {
            "model_name": "kimi-k2.5",
            "model_label": "Kimi K2.5",
            "calls": 1,
            "success_calls": 1,
            "failed_calls": 0,
        }
    ]
    assert summary["image_analysis_model_stats"] == [
        {
            "model_name": "gemini-3.1-pro-preview",
            "model_label": "Gemini 3.1 Pro",
            "calls": 1,
            "success_calls": 1,
            "failed_calls": 0,
        }
    ]
    assert summary["total_elapsed_ms"] == 2000


def test_harness_billing_summary_zeroes_amounts_in_provider_balance_sync_mode(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.agent_harness.core.context.context.is_provider_balance_sync_enabled",
        lambda: True,
    )
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        workspace_root=tmp_path,
        skill_id="pptx",
    )

    ctx.record_billing(
        category="multimodal",
        amount=99,
        detail={"model_name": "kimi-k2.5", "elapsed_ms": 1200},
    )

    summary = ctx.build_billing_summary()

    assert ctx.accumulated_amount_cents == 0
    assert ctx.billing_breakdown[0]["amount"] == 0
    assert summary["multimodal_calls"] == 1
    assert summary["multimodal_models"] == ["kimi-k2.5"]


def test_subagent_runner_merges_child_billing_into_parent_context(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.core.context.context.is_provider_balance_sync_enabled",
        lambda: False,
    )
    parent_ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="parent-run",
        workspace_root=tmp_path,
        skill_id="pptx",
    )
    child_ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="sub-run-1",
        workspace_root=tmp_path,
        skill_id="pptx",
        parent_run_id="parent-run",
        subagent_run_id="sub-run-1",
        subagent_label="Visual QA",
        subagent_type="explore",
        is_subagent=True,
        subagent_depth=1,
    )
    child_ctx.record_billing(
        category="image_analysis",
        amount=4,
        detail={"model_name": "gemini-3.1-pro-preview", "elapsed_ms": 950},
    )

    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={"id": "conv-1"},
        parent_context=parent_ctx,
        parent_registry=None,
        language="zh",
    )

    runner._merge_child_billing(parent_ctx, child_ctx)
    summary = parent_ctx.build_billing_summary()

    assert parent_ctx.accumulated_amount_cents == 4
    assert len(parent_ctx.billing_breakdown) == 1
    assert summary["image_analysis_calls"] == 1
    assert summary["image_analysis_models"] == ["gemini-3.1-pro-preview"]
    assert summary["image_analysis_model_stats"] == [
        {
            "model_name": "gemini-3.1-pro-preview",
            "model_label": "Gemini 3.1 Pro",
            "calls": 1,
            "success_calls": 1,
            "failed_calls": 0,
        }
    ]
