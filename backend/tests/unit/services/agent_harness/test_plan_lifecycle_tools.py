from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.agent_harness.capabilities.tools.plan_lifecycle import (
    ExecutionStepInput,
    PlanningDraftInput,
    RequestPlanApprovalInput,
    RequestPlanApprovalTool,
    UpdateExecutionProgressInput,
    UpdateExecutionProgressTool,
    UpdatePlanningDraftTool,
    UserPlanInput,
    UserPlanOutlineItemInput,
)
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    update_conversation,
)


def _ctx(tmp_path: Path, conversation_id: str) -> HarnessContext:
    return HarnessContext(
        user_id=7,
        conversation_id=conversation_id,
        run_id="run-1",
        workspace_root=tmp_path,
    )


def _approval_input() -> RequestPlanApprovalInput:
    return RequestPlanApprovalInput(
        title="执行计划",
        summary="先制作页面，再验证并发布。",
        user_plan=UserPlanInput(
            artifact_type="html",
            title="落地页大纲",
            summary="生成一个可发布的单页网站。",
            outline=[
                UserPlanOutlineItemInput(
                    id="section-1",
                    title="入参里的错误首屏",
                    summary="这个入参里的首屏大纲不应进入审批计划，因为审批大纲必须来自最新规划草稿。",
                ),
                UserPlanOutlineItemInput(
                    id="section-2",
                    title="入参里的错误内容区",
                    summary="这个入参里的内容区大纲也不应进入审批计划，用于验证草稿大纲才是唯一来源。",
                ),
            ],
            file_path="project/index.html",
            file_name="index.html",
        ),
        execution_steps=[
            ExecutionStepInput(id="step-1", title="生成文件", status="pending"),
            ExecutionStepInput(id="step-2", title="验证交付", status="pending"),
        ],
        assumptions=["缺失品牌色时使用设计系统默认色。"],
        verification=["检查 index.html 存在。"],
        followups=["发布后可继续优化文案。"],
    )


def _draft_state(*, open_questions: list[str] | None = None, draft_outline: list[dict] | None = None) -> dict:
    return {
        "summary": "已确认生成一个可发布的单页网站。",
        "confirmed_inputs": {"artifact": "landing_page"},
        "assumptions": ["缺失品牌色时使用设计系统默认色。"],
        "draft_outline": draft_outline
        if draft_outline is not None
        else [
            {
                "id": "section-1",
                "title": "草稿首屏",
                "summary": "呈现品牌主张、核心视觉和主要行动入口，让用户在首屏理解页面价值并知道下一步操作。",
            },
            {
                "id": "section-2",
                "title": "草稿内容区",
                "summary": "展示功能亮点、案例依据和必要说明信息，帮助用户判断服务是否匹配自己的需求。",
            },
        ],
        "open_questions": list(open_questions or []),
        "updated_at": "2026-06-04T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_update_planning_draft_does_not_create_approval_plan(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Draft")
    update_conversation(7, conversation["id"], phase="planning", activity="planning_outline")

    result = await UpdatePlanningDraftTool().execute(
        PlanningDraftInput(
            summary="正在收集页面目标。",
            confirmed_inputs={"artifact": "landing_page"},
            assumptions=["先按通用 SaaS 首页处理。"],
            draft_outline=[
                UserPlanOutlineItemInput(
                    id="section-1",
                    title="首屏",
                    summary="先基于当前信息规划首屏定位、核心卖点和行动入口，视觉方向确认后再进一步细化表达。",
                )
            ],
            open_questions=["是否已有品牌色？"],
        ),
        _ctx(tmp_path, conversation["id"]),
    )

    assert result.is_error is False
    assert result.metadata is not None
    assert result.metadata["planning_draft"]["open_questions"] == ["是否已有品牌色？"]
    assert "plan_state" not in result.metadata
    assert result.metadata.get("approval_requested") is None


@pytest.mark.asyncio
async def test_request_plan_approval_creates_planning_ready_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Approval")
    update_conversation(
        7,
        conversation["id"],
        phase="planning",
        activity="planning_outline",
        planning_draft=_draft_state(),
    )

    result = await RequestPlanApprovalTool().execute(_approval_input(), _ctx(tmp_path, conversation["id"]))

    plan_state = (result.metadata or {}).get("plan_state")
    assert result.is_error is False
    assert (result.metadata or {}).get("approval_requested") is True
    assert plan_state["status"] == "planning_ready"
    assert plan_state["execution_state"]["status"] == "planning_ready"
    assert plan_state["outline_state"]["items"][0]["id"] == "section-1"
    assert plan_state["outline_state"]["items"][0]["title"] == "草稿首屏"
    assert plan_state["user_plan"]["outline"][0]["title"] == "草稿首屏"
    assert plan_state["user_plan"]["file_path"] == "project/index.html"
    assert plan_state["approval_source"] == "planning_draft"
    assert plan_state["planning_draft_updated_at"] == "2026-06-04T00:00:00+00:00"


@pytest.mark.asyncio
async def test_request_plan_approval_rejects_missing_planning_draft(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Approval")
    update_conversation(7, conversation["id"], phase="planning", activity="planning_outline")

    result = await RequestPlanApprovalTool().execute(_approval_input(), _ctx(tmp_path, conversation["id"]))

    assert result.is_error is True
    assert "planning draft" in result.output


@pytest.mark.asyncio
async def test_request_plan_approval_rejects_draft_open_questions(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Approval")
    update_conversation(
        7,
        conversation["id"],
        phase="planning",
        activity="planning_outline",
        planning_draft=_draft_state(open_questions=["还缺品牌定位"]),
    )

    result = await RequestPlanApprovalTool().execute(_approval_input(), _ctx(tmp_path, conversation["id"]))

    assert result.is_error is True
    assert "open_questions" in result.output


@pytest.mark.asyncio
async def test_request_plan_approval_rejects_empty_draft_outline(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Approval")
    update_conversation(
        7,
        conversation["id"],
        phase="planning",
        activity="planning_outline",
        planning_draft=_draft_state(draft_outline=[]),
    )

    result = await RequestPlanApprovalTool().execute(_approval_input(), _ctx(tmp_path, conversation["id"]))

    assert result.is_error is True
    assert "draft_outline" in result.output


def test_request_plan_approval_rejects_open_questions():
    payload = _approval_input().model_dump()
    payload["open_questions"] = ["还缺一个用户决策"]
    with pytest.raises(ValidationError):
        RequestPlanApprovalInput(**payload)


def test_request_plan_approval_normalizes_empty_open_questions():
    payload = _approval_input().model_dump()

    payload["open_questions"] = None
    assert RequestPlanApprovalInput(**payload).open_questions == []

    payload["open_questions"] = ""
    assert RequestPlanApprovalInput(**payload).open_questions == []

    payload["open_questions"] = "[]"
    assert RequestPlanApprovalInput(**payload).open_questions == []


def test_update_planning_draft_normalizes_empty_open_questions():
    draft = PlanningDraftInput(
        summary="正在整理页面目标和交付范围。",
        confirmed_inputs={"artifact_type": "html"},
        assumptions=[],
        draft_outline=[
            UserPlanOutlineItemInput(
                id="section-1",
                title="首屏",
                summary="规划首屏定位、核心卖点和行动入口，确保用户能快速理解页面价值并继续浏览。",
            ),
            UserPlanOutlineItemInput(
                id="section-2",
                title="内容区",
                summary="规划功能亮点、案例依据和转化说明，帮助用户判断服务是否匹配自己的需求。",
            ),
        ],
        open_questions=None,
    )

    assert draft.open_questions == []


def test_update_planning_draft_requires_outline():
    with pytest.raises(ValidationError):
        PlanningDraftInput(
            summary="正在整理页面目标和交付范围。",
            confirmed_inputs={"artifact_type": "html"},
            assumptions=[],
            open_questions=["是否已有品牌色？"],
        )


def test_update_planning_draft_rejects_short_summary():
    with pytest.raises(ValidationError, match="summary is too short"):
        PlanningDraftInput(
            summary="正在整理页面目标和交付范围。",
            confirmed_inputs={"artifact_type": "excel"},
            assumptions=[],
            draft_outline=[
                UserPlanOutlineItemInput(
                    id="sheet-1",
                    title="汇总表",
                    summary="汇总数据。",
                )
            ],
            open_questions=[],
        )


def test_update_planning_draft_rejects_duplicate_outline_ids():
    with pytest.raises(ValidationError, match="ids must be unique"):
        PlanningDraftInput(
            summary="正在整理页面目标和交付范围。",
            confirmed_inputs={"artifact_type": "html"},
            assumptions=[],
            draft_outline=[
                UserPlanOutlineItemInput(
                    id="section-1",
                    title="首屏",
                    summary="展示页面主张、核心卖点和行动入口，让用户快速理解服务价值并进入下一步。",
                ),
                UserPlanOutlineItemInput(
                    id="section-1",
                    title="服务介绍",
                    summary="说明服务内容、适用对象和核心收益，帮助用户判断是否匹配自己的需求。",
                ),
            ],
            open_questions=[],
        )


def test_update_planning_draft_requires_minimum_items_for_html():
    with pytest.raises(ValidationError, match="at least 2"):
        PlanningDraftInput(
            summary="正在整理页面目标和交付范围。",
            confirmed_inputs={"artifact_type": "html"},
            assumptions=[],
            draft_outline=[
                UserPlanOutlineItemInput(
                    id="section-1",
                    title="首屏",
                    summary="展示页面主张、核心卖点和行动入口，让用户快速理解服务价值并进入下一步。",
                )
            ],
            open_questions=[],
        )


@pytest.mark.asyncio
async def test_update_execution_progress_only_updates_existing_execution_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Execution")
    update_conversation(
        7,
        conversation["id"],
        phase="planning",
        activity="planning_outline",
        planning_draft=_draft_state(),
    )
    approval = await RequestPlanApprovalTool().execute(_approval_input(), _ctx(tmp_path, conversation["id"]))
    approved_plan = (approval.metadata or {})["plan_state"]
    update_conversation(7, conversation["id"], phase="executing", plan_state=approved_plan)

    result = await UpdateExecutionProgressTool().execute(
        UpdateExecutionProgressInput(
            steps=[
                ExecutionStepInput(id="step-1", title="生成文件", status="completed"),
                ExecutionStepInput(id="step-2", title="验证交付", status="in_progress"),
            ],
            current_item_id="section-2",
            progress_message="正在验证页面。",
            status="in_progress",
        ),
        _ctx(tmp_path, conversation["id"]),
    )

    plan_state = (result.metadata or {}).get("plan_state")
    assert result.is_error is False
    assert plan_state["outline_state"]["outline_id"] == approved_plan["outline_state"]["outline_id"]
    assert plan_state["outline_state"]["items"] == approved_plan["outline_state"]["items"]
    assert plan_state["execution_state"]["current_item_id"] == "section-2"
    assert plan_state["execution_state"]["steps"][0]["status"] == "completed"
    assert plan_state["user_plan"]["progress_message"] == "正在验证页面。"
