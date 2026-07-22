from __future__ import annotations

from app.services.agent_harness.authoring.planning.user_plan import (
    normalize_artifact_type,
    normalize_user_plan_for_storage,
    validate_user_plan,
)
from app.services.agent_harness.authoring.planning.user_projection import build_user_plan, build_user_progress


def test_build_user_plan_returns_model_supplied_outline_without_content_generation() -> None:
    plan_state = {
        "title": "设计行业PPT",
        "summary": "创建一个四页的设计行业主题演示文稿",
        "status": "pending_approval",
        "current_step": "step-1",
        "steps": [
            {"id": "step-1", "title": "封面页", "description": "设计行业主题封面，包含标题和副标题", "status": "in_progress"},
        ],
        "user_plan": {
            "artifact_type": "ppt",
            "title": "设计行业PPT",
            "summary": "四页设计行业演示文稿",
            "outline": [
                {"id": "slide-1", "title": "封面", "summary": "说明主题、受众和一句话定位。"},
                {"id": "slide-2", "title": "行业概述", "summary": "介绍定义、范围和价值。"},
            ],
        },
    }

    user_plan = build_user_plan(plan_state, mode="ppt")

    assert user_plan["artifact_type"] == "ppt"
    assert user_plan["outline"][0]["summary"] == "说明主题、受众和一句话定位。"
    assert len(user_plan["outline"]) == 2


def test_build_user_plan_returns_empty_when_outline_is_missing() -> None:
    plan_state = {
        "title": "设计行业PPT",
        "summary": "创建一个四页的设计行业主题演示文稿",
        "status": "pending_approval",
        "current_step": "step-1",
        "steps": [
            {"id": "step-1", "title": "封面页", "status": "in_progress"},
            {"id": "step-2", "title": "行业概述", "status": "pending"},
        ],
    }

    user_plan = build_user_plan(plan_state, mode="ppt")

    assert user_plan == {}


def test_validate_user_plan_accepts_placeholder_like_content() -> None:
    plan_state = {
        "title": "设计行业PPT",
        "summary": "创建一个四页的设计行业主题演示文稿",
        "status": "pending_approval",
        "current_step": "step-1",
        "steps": [{"id": "step-1", "title": "封面页", "status": "in_progress"}],
        "user_plan": {
            "artifact_type": "ppt",
            "outline": [
                {"title": "封面", "summary": "围绕封面展开内容"},
            ],
        },
    }

    validation = validate_user_plan(plan_state, mode="ppt")

    assert validation.valid is True
    assert validation.issues == []


def test_build_user_progress_prefers_user_plan_progress_message_then_neutral_default() -> None:
    plan_state = {
        "title": "设计行业PPT",
        "summary": "创建一个四页的设计行业主题演示文稿",
        "status": "pending_approval",
        "current_step": "step-1",
        "steps": [{"id": "step-1", "title": "生成代码", "status": "in_progress"}],
        "user_plan": {
            "artifact_type": "ppt",
            "progress_message": "正在完善第 1 页封面说明",
            "outline": [{"title": "封面", "summary": "说明主题、受众和一句话定位。"}],
        },
    }

    progress = build_user_progress(plan_state, mode="ppt")
    assert progress["message"] == "正在完善第 1 页封面说明"

    del plan_state["user_plan"]["progress_message"]
    progress = build_user_progress(plan_state, mode="ppt")
    assert progress["message"] == "正在执行"


def test_build_user_progress_uses_generic_execution_default_when_no_model_progress_exists() -> None:
    plan_state = {
        "title": "设计行业PPT",
        "summary": "创建一个四页的设计行业主题演示文稿",
        "status": "in_progress",
        "current_step": "step-1",
        "steps": [{"id": "step-1", "title": "生成代码", "status": "in_progress"}],
        "user_plan": {
            "artifact_type": "ppt",
            "outline": [{"title": "封面", "summary": "说明主题、受众和一句话定位。"}],
        },
    }

    progress = build_user_progress(plan_state, mode="ppt")

    assert progress["status"] == "in_progress"
    assert progress["message"] == "正在执行"


def test_normalize_user_plan_for_storage_preserves_flat_outline_array() -> None:
    normalized = normalize_user_plan_for_storage(
        {
            "artifact_type": "word",
            "outline": [
                {"title": "第一章 背景", "description": "交代背景、目标和范围。"},
            ],
        },
        plan_state={"title": "文档计划", "summary": "撰写文档", "status": "pending"},
        mode="word",
    )

    assert normalized["outline"][0]["summary"] == "交代背景、目标和范围。"


def test_normalize_artifact_type_accepts_html_mime_type() -> None:
    assert normalize_artifact_type("text/html") == "html"
    assert normalize_artifact_type("text_html") == "html"


def test_validate_user_plan_reports_missing_outline_without_fallback() -> None:
    validation = validate_user_plan(
        {
            "title": "季度复盘",
            "summary": "生成复盘文档",
            "status": "pending_approval",
            "steps": [{"id": "step-1", "title": "整理资料", "status": "in_progress"}],
        },
        mode="word",
    )

    assert validation.valid is False
    assert "missing_user_plan" in validation.issues
    assert "missing_outline_items" in validation.issues
