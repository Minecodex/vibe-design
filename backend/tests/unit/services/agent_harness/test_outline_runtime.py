from pathlib import Path

import pytest

from app.services.agent_harness.core.context import create_context
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    get_conversation,
    load_messages,
    update_conversation,
)
from app.services.agent_harness.authoring.planning.outline_runtime import OutlineCoordinator
from app.services.agent_harness.runtime.state.runtime_projection_store import persist_outline_runtime_state
from app.services.agent_harness.runtime.state.store_core import read_outline_runtime_state


def _coordinator(user_id: int, conversation_id: str) -> OutlineCoordinator:
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id="run-1",
        language="zh",
        conversation=get_conversation(user_id, conversation_id),
    )
    return OutlineCoordinator(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id="run-1",
        ctx=ctx,
    )


def test_set_current_outline_persists_planning_ready_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Current outline")
    plan_state = {
        "title": "设计行业洞察",
        "status": "in_progress",
        "user_plan": {
            "artifact_type": "ppt",
            "title": "设计行业洞察",
            "summary": "四页演示文稿",
            "outline": [
                {"id": "slide-1", "title": "封面", "summary": "主题与一句话定位", "order": 1, "status": "pending"},
            ],
        },
    }

    planned = _coordinator(7, conversation["id"]).set_current_outline(plan_state=plan_state, mode="ppt")

    assert planned["current_outline"]["items"][0]["title"] == "封面"
    runtime_state = read_outline_runtime_state(7, conversation["id"])
    assert runtime_state["current_outline"]["items"][0]["title"] == "封面"
    assert runtime_state["execution_run"] is None
    assert runtime_state["last_revision"] is None

    persisted = get_conversation(7, conversation["id"])
    assert persisted["phase"] == "planning_ready"
    assert persisted["outline_runtime"]["current_outline"]["items"][0]["title"] == "封面"
    assert persisted["outline_runtime"]["execution_state"]["outline_version"] == runtime_state["current_outline"]["version"]
    assert "plan_review" not in persisted


def test_patch_current_outline_updates_outline_and_rebuilds_execution(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Patch current outline")
    coordinator = _coordinator(7, conversation["id"])
    coordinator.set_current_outline(
        plan_state={
            "title": "设计行业洞察",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "summary": "四页演示文稿",
                "outline": [
                    {"id": "slide-1", "title": "封面", "summary": "主题与一句话定位", "order": 1, "status": "pending"},
                ],
            },
        },
        mode="ppt",
    )

    patched = coordinator.patch_current_outline(
        plan={
            "artifact_type": "ppt",
            "title": "设计行业洞察",
            "summary": "四页演示文稿",
            "items": [
                {"id": "slide-1", "title": "新封面", "summary": "新的封面说明", "order": 1, "status": "pending"},
                {"id": "slide-2", "title": "趋势页", "summary": "补充行业趋势", "order": 2, "status": "pending"},
            ],
            "constraints": [],
            "style_notes": [],
        }
    )

    assert patched["current_outline"]["items"][0]["title"] == "新封面"
    assert patched["current_outline"]["items"][1]["title"] == "趋势页"
    assert patched["execution_state"]["outline_version"] == patched["current_outline"]["version"]

    runtime_state = read_outline_runtime_state(7, conversation["id"])
    assert runtime_state["current_outline"]["items"][1]["id"] == "slide-2"
    assert runtime_state["last_revision"]["mode"] == "structured_edit"
    messages = [message for message in load_messages(7, conversation["id"]) if str((message.get("metadata") or {}).get("render_key") or "").startswith("home-user-plan:")]
    assert len(messages) == 1
    persisted = get_conversation(7, conversation["id"])
    assert persisted["phase"] == "planning_ready"


def test_start_execution_locks_current_outline_and_creates_execution_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Start execution")
    coordinator = _coordinator(7, conversation["id"])
    coordinator.set_current_outline(
        plan_state={
            "title": "设计行业洞察",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "summary": "四页演示文稿",
                "outline": [
                    {"id": "slide-1", "title": "封面", "summary": "主题与一句话定位", "order": 1, "status": "pending"},
                ],
            },
        },
        mode="ppt",
    )

    started = coordinator.start_execution()

    assert started["current_outline"]["status"] == "executing"
    assert started["execution_state"]["status"] == "in_progress"
    assert started["execution_run"]["status"] == "in_progress"
    assert started["execution_run"]["locked_outline_version"] == started["current_outline"]["version"]
    assert started["execution_run"]["locked_outline_snapshot"]["items"][0]["title"] == "封面"

    persisted = get_conversation(7, conversation["id"])
    assert persisted["phase"] == "executing"
    assert persisted["outline_runtime"]["execution_run"]["locked_outline_version"] == started["current_outline"]["version"]
    messages = [message for message in load_messages(7, conversation["id"]) if str((message.get("metadata") or {}).get("render_key") or "").startswith("home-user-plan:")]
    assert len(messages) == 1
    assert messages[0]["blocks"][0]["payload"]["snapshotStatus"] == "executing"

    with pytest.raises(ValueError, match="已开始执行"):
        coordinator.patch_current_outline(
            plan={
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "summary": "四页演示文稿",
                "items": [{"id": "slide-1", "title": "不能改", "summary": "执行中禁止修改", "order": 1}],
            }
        )


def test_revision_with_no_material_change_is_rejected(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Reject noop revision")
    coordinator = _coordinator(7, conversation["id"])
    original = coordinator.set_current_outline(
        plan_state={
            "title": "中国历年出生人口数据表格",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "excel",
                "title": "中国历年出生人口数据表格",
                "summary": "包含中国出生人口表与趋势分析",
                "outline": [
                    {"id": "sheet-1", "title": "历年出生人口数据", "summary": "中国 1949-2024 数据", "order": 1, "status": "pending"},
                    {"id": "sheet-2", "title": "数据趋势分析", "summary": "趋势与图表", "order": 2, "status": "pending"},
                ],
            },
        },
        mode="excel",
    )

    with pytest.raises(ValueError, match="未体现用户要求的修改"):
        coordinator.set_current_outline(
            plan_state={
                "title": "中国历年出生人口数据表格",
                "status": "in_progress",
                "user_plan": {
                    "artifact_type": "excel",
                    "title": "中国历年出生人口数据表格",
                    "summary": "包含中国出生人口表与趋势分析",
                    "outline": [
                        {"id": "sheet-1", "title": "历年出生人口数据", "summary": "中国 1949-2024 数据", "order": 1, "status": "pending"},
                        {"id": "sheet-2", "title": "数据趋势分析", "summary": "趋势与图表", "order": 2, "status": "pending"},
                    ],
                },
            },
            mode="excel",
            revision_instruction="检索下日本对应的人口数据，然后增加一个日本的人口数据表",
        )

    persisted = get_conversation(7, conversation["id"])
    runtime_state = read_outline_runtime_state(7, conversation["id"])
    assert persisted["phase"] == "planning_ready"
    assert runtime_state["current_outline"]["version"] == original["current_outline"]["version"]
    assert runtime_state["current_outline"]["items"] == original["current_outline"]["items"]


def test_update_execution_uses_finalizing_projection_until_run_completes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Finalize projection")
    coordinator = _coordinator(7, conversation["id"])
    coordinator.set_current_outline(
        plan_state={
            "title": "设计行业洞察",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "ppt",
                "title": "设计行业洞察",
                "summary": "四页演示文稿",
                "outline": [
                    {"id": "slide-1", "title": "封面", "summary": "主题与一句话定位", "order": 1, "status": "pending"},
                ],
            },
        },
        mode="ppt",
    )
    started = coordinator.start_execution()
    completed_execution = {
        **started["execution_state"],
        "status": "completed",
        "current_step": "step-1",
        "steps": [
            {
                "id": "step-1",
                "title": "整理封面内容",
                "description": "完成封面内容整理",
                "status": "completed",
                "outline_item_ids": ["slide-1"],
            }
        ],
    }

    planned = coordinator.update_execution(
        plan_state={
            "status": "completed",
            "execution_state": completed_execution,
        },
        mode="ppt",
    )

    assert planned["outline_runtime"]["execution_state"]["status"] == "completed"
    assert planned["outline_runtime"]["projection_state"]["status"] == "finalizing"


def test_revision_appends_new_snapshot_and_supersedes_previous_snapshot(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Snapshot history")
    coordinator = _coordinator(7, conversation["id"])
    original = coordinator.set_current_outline(
        plan_state={
            "title": "中国历年出生人口数据表格",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "excel",
                "title": "中国历年出生人口数据表格",
                "summary": "中国出生人口表",
                "outline": [
                    {"id": "sheet-1", "title": "中国出生人口", "summary": "中国数据", "order": 1, "status": "pending"},
                ],
            },
        },
        mode="excel",
    )
    revised = coordinator.set_current_outline(
        plan_state={
            "title": "中日历年人口数据对比表",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "excel",
                "title": "中日历年人口数据对比表",
                "summary": "新增日本人口数据表并进行中日人口对比",
                "outline": [
                    {"id": "sheet-1", "title": "中国出生人口", "summary": "中国数据", "order": 1, "status": "pending"},
                    {"id": "sheet-2", "title": "日本人口数据表", "summary": "日本人口数据", "order": 2, "status": "pending"},
                ],
            },
        },
        mode="excel",
        revision_instruction="检索下日本对应的人口数据，然后增加一个日本的人口数据表",
    )

    messages = [message for message in load_messages(7, conversation["id"]) if str((message.get("metadata") or {}).get("render_key") or "").startswith("home-user-plan:")]
    assert len(messages) == 2
    previous_payload = messages[0]["blocks"][0]["payload"]
    latest_payload = messages[1]["blocks"][0]["payload"]
    assert previous_payload["snapshotStatus"] == "superseded"
    assert latest_payload["snapshotStatus"] == "active"
    assert previous_payload["planInstanceId"] == latest_payload["planInstanceId"] == original["current_outline"]["plan_instance_id"]
    assert latest_payload["outlineVersion"] == revised["current_outline"]["version"] == 2


def test_completed_plan_creates_new_plan_instance_for_next_plan(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="New plan instance")
    coordinator = _coordinator(7, conversation["id"])
    started = coordinator.set_current_outline(
        plan_state={
            "title": "第一轮计划",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "excel",
                "title": "第一轮计划",
                "summary": "第一次计划",
                "outline": [{"id": "sheet-1", "title": "第一轮", "summary": "第一轮数据", "order": 1, "status": "pending"}],
            },
        },
        mode="excel",
    )
    runtime_state = read_outline_runtime_state(7, conversation["id"])
    completed_outline = {
        **runtime_state["current_outline"],
        "status": "completed",
        "snapshot_status": "completed",
    }
    from app.services.agent_harness.runtime.state.runtime_projection_store import persist_outline_runtime_state
    persist_outline_runtime_state(7, conversation["id"], current_outline=completed_outline)

    next_plan = coordinator.set_current_outline(
        plan_state={
            "title": "第二轮计划",
            "status": "in_progress",
            "user_plan": {
                "artifact_type": "excel",
                "title": "第二轮计划",
                "summary": "第二次计划",
                "outline": [{"id": "sheet-1", "title": "第二轮", "summary": "第二轮数据", "order": 1, "status": "pending"}],
            },
        },
        mode="excel",
    )

    assert started["current_outline"]["plan_instance_id"] != next_plan["current_outline"]["plan_instance_id"]
    assert next_plan["current_outline"]["version"] == 1
