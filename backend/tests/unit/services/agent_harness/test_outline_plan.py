from __future__ import annotations

import pytest

from app.services.agent_harness.authoring.planning.outline_plan import (
    OutlineLockedError,
    apply_outline_patch,
    build_outline_projection,
    compile_execution_plan,
    create_outline_state,
    execution_state_from_steps,
)
from app.services.agent_harness.runtime.eventing.presentation import normalize_plan_state


def test_create_outline_state_assigns_stable_artifact_item_ids() -> None:
    outline = create_outline_state(
        artifact_type="excel",
        title="人口出生数据表",
        summary="生成 1949-2024 年出生人口 Excel。",
        items=[
            {"title": "出生人口数据", "summary": "主数据表。"},
            {"id": "notes", "title": "数据说明", "summary": "说明数据来源。"},
        ],
    )

    assert "status" not in outline
    assert outline["version"] == 1
    assert outline["items"][0]["id"] == "sheet-1"
    assert outline["items"][1]["id"] == "notes"
    assert "status" not in outline["items"][0]


def test_compile_execution_plan_maps_steps_to_outline_items() -> None:
    outline = create_outline_state(
        artifact_type="excel",
        title="人口出生数据表",
        summary="生成 Excel。",
        items=[
            {"id": "sheet-1", "title": "出生人口数据", "summary": "主数据表。"},
            {"id": "sheet-2", "title": "数据说明", "summary": "来源说明。"},
        ],
    )

    execution = compile_execution_plan(outline)

    assert execution["outline_version"] == 1
    assert [step["type"] for step in execution["steps"]] == [
        "research",
        "validate_data",
        "generate_artifact",
        "publish_artifact",
    ]
    assert execution["steps"][0]["outline_item_ids"] == ["sheet-1", "sheet-2"]
    assert execution["steps"][2]["outline_item_ids"] == ["sheet-1", "sheet-2"]


def test_projection_updates_outline_items_from_internal_steps_and_filters_technical_text() -> None:
    outline = create_outline_state(
        artifact_type="excel",
        title="人口出生数据表",
        summary="生成 Excel。",
        items=[
            {"id": "sheet-1", "title": "出生人口数据", "summary": "主数据表。"},
            {"id": "sheet-2", "title": "数据说明", "summary": "来源说明。"},
        ],
    )
    execution = compile_execution_plan(outline)
    execution["steps"][0]["status"] = "completed"
    execution["steps"][1]["status"] = "in_progress"
    execution["steps"][1]["title"] = "运行脚本校验数据"
    execution["steps"][1]["progress_message"] = "正在校验出生人口数据"

    projection = build_outline_projection(outline, execution)

    # Per-item status/progress now lives on execution_steps (the "card optimization"
    # change stopped surfacing technical progress text on outline items); items
    # expose last_completed_step for cross-referencing.
    assert projection["items"][0]["last_completed_step"] == "step-1"
    active_step = projection["execution_steps"][1]
    assert active_step["status"] == "in_progress"
    assert active_step["progress_message"] == "正在校验出生人口数据"
    # User-facing progress text is sourced from progress_message, not the technical step title.
    assert "脚本" not in active_step["progress_message"]


def test_apply_outline_patch_recompiles_draft_but_rejects_executing_outline() -> None:
    outline = create_outline_state(
        artifact_type="word",
        title="报告",
        summary="生成报告。",
        items=[{"id": "section-1", "title": "背景", "summary": "背景说明。"}],
    )

    patched, execution, projection = apply_outline_patch(
        outline,
        items=[
            {"title": "背景", "summary": "新的背景说明。"},
            {"title": "结论", "summary": "结论说明。"},
        ],
    )

    assert patched["version"] == 2
    assert patched["items"][0]["id"] == "section-1"
    assert patched["items"][1]["id"] == "section-2"
    assert execution["outline_version"] == 2
    assert projection["outline_version"] == 2

    patched["snapshot_status"] = "executing"
    with pytest.raises(OutlineLockedError):
        apply_outline_patch(patched, items=patched["items"])


def test_execution_state_from_steps_computes_elapsed_ms_from_timestamps() -> None:
    outline = create_outline_state(
        artifact_type="excel",
        title="人口出生数据表",
        summary="生成 Excel。",
        items=[{"id": "sheet-1", "title": "出生人口数据", "summary": "主数据表。"}],
    )

    execution = execution_state_from_steps(
        outline_state=outline,
        steps=[
            {
                "id": "step-1",
                "title": "整理数据",
                "status": "completed",
                "started_at": "2026-05-10T09:07:21.000000+00:00",
                "completed_at": "2026-05-10T09:08:45.250000+00:00",
            }
        ],
    )

    assert execution["steps"][0]["elapsed_ms"] == 84_250


def test_normalize_plan_state_computes_elapsed_ms_when_step_completes() -> None:
    previous = {
        "steps": [
            {
                "id": "step-1",
                "status": "in_progress",
                "started_at": "2026-05-10T09:07:21.000000+00:00",
                "elapsed_ms": None,
            }
        ]
    }

    plan = normalize_plan_state(
        title="人口出生数据表",
        summary="生成 Excel。",
        steps=[{"id": "step-1", "title": "整理数据", "status": "completed"}],
        status="in_progress",
        previous_plan_state=previous,
    )

    assert plan["steps"][0]["elapsed_ms"] is not None
    assert plan["steps"][0]["elapsed_ms"] > 1
