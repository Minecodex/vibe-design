from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_ARTIFACT_TYPE_ALIASES = {
    "ppt": "ppt",
    "pptx": "ppt",
    "powerpoint": "ppt",
    "slides": "ppt",
    "word": "word",
    "doc": "word",
    "docx": "word",
    "document": "word",
    "excel": "excel",
    "xlsx": "excel",
    "spreadsheet": "excel",
    "sheet": "excel",
    "html": "html",
    "text_html": "html",
    "text/html": "html",
    "web": "html",
    "website": "html",
}

_REPAIR_EXAMPLE_BY_ARTIFACT = {
    "ppt": '[{"title":"封面","summary":"说明主题、对象与一句话结论。"}]',
    "word": '[{"title":"第一章 背景","summary":"交代背景、目标与范围。"}]',
    "excel": '[{"title":"汇总表","summary":"展示核心指标、统计口径与关键结论。"}]',
    "html": '[{"title":"Hero 区","summary":"展示品牌定位、核心卖点与主 CTA。"},{"title":"服务介绍","summary":"说明品牌设计、网站设计与创意服务内容。"}]',
    "other": '[{"title":"主要内容","summary":"说明这一部分最终要交付什么。"}]',
}

@dataclass(slots=True)
class UserPlanValidationResult:
    valid: bool
    normalized_plan: dict[str, Any]
    issues: list[str]


def normalize_artifact_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return _ARTIFACT_TYPE_ALIASES.get(normalized, normalized or "other")


def repair_outline_example(artifact_type: str) -> str:
    normalized = normalize_artifact_type(artifact_type)
    return _REPAIR_EXAMPLE_BY_ARTIFACT.get(normalized, _REPAIR_EXAMPLE_BY_ARTIFACT["other"])


def _item_content(value: dict[str, Any]) -> str:
    for key in ("summary", "description", "purpose", "details", "content", "text"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _is_placeholder_content(text: str) -> bool:
    return not str(text or "").strip()


def _normalize_outline_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("name") or "").strip()
        content = _item_content(raw)
        item: dict[str, Any] = {
            "id": str(raw.get("id") or f"item-{index}"),
            "title": title,
        }
        if content:
            item["summary"] = content
        items.append(item)
    return items


def _normalize_outline(raw_outline: Any) -> list[dict[str, Any]]:
    return _normalize_outline_items(raw_outline)


def normalize_user_plan_for_storage(
    raw_user_plan: dict[str, Any] | None,
    *,
    plan_state: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = raw_user_plan if isinstance(raw_user_plan, dict) else {}
    artifact_type = normalize_artifact_type(base.get("artifact_type") or mode)
    return {
        "artifact_type": artifact_type,
        "title": str(base.get("title") or plan_state.get("title") or "任务计划"),
        "summary": str(base.get("summary") or plan_state.get("summary") or ""),
        "status": str(plan_state.get("status") or base.get("status") or "in_progress"),
        "progress_message": base.get("progress_message"),
        "outline": _normalize_outline(base.get("outline")),
        "file_path": base.get("file_path"),
        "file_name": base.get("file_name"),
    }


def validate_user_plan(
    plan_state: dict[str, Any],
    *,
    mode: str,
) -> UserPlanValidationResult:
    raw_user_plan = plan_state.get("user_plan") if isinstance(plan_state.get("user_plan"), dict) else None
    normalized = normalize_user_plan_for_storage(raw_user_plan, plan_state=plan_state, mode=mode)
    artifact_type = normalized["artifact_type"]
    items = normalized["outline"] if isinstance(normalized["outline"], list) else []
    issues: list[str] = []

    if raw_user_plan is None:
        issues.append("missing_user_plan")
    if not isinstance(items, list) or not items:
        issues.append("missing_outline_items")
    else:
        for item in items:
            title = str(item.get("title") or "").strip()
            content = _item_content(item)
            if not title:
                issues.append("missing_item_title")
                continue
            if _is_placeholder_content(content):
                issues.append("empty_item_content")
                break

    return UserPlanValidationResult(
        valid=not issues,
        normalized_plan=normalized,
        issues=issues,
    )


def build_user_plan_repair_prompt(
    plan_state: dict[str, Any],
    *,
    mode: str,
    issues: list[str],
    language: str,
) -> str:
    artifact_type = normalize_artifact_type(((plan_state.get("user_plan") or {}).get("artifact_type")) or mode)
    outline_example = repair_outline_example(artifact_type)
    issue_labels_zh = {
        "missing_user_plan": "缺少 user_plan",
        "missing_outline_items": "outline 为空",
        "missing_item_title": "存在条目缺少标题",
        "empty_item_content": "存在条目说明为空或过于模板化",
    }
    issue_labels_en = {
        "missing_user_plan": "user_plan is missing",
        "missing_outline_items": "outline is empty",
        "missing_item_title": "an item is missing a title",
        "empty_item_content": "an item description is empty or templated",
    }
    if language == "zh":
        issues_text = "、".join(issue_labels_zh.get(issue, issue) for issue in issues) or "用户计划不合格"
        return (
            "系统校验提醒：你刚才提交的用户计划不合格，问题包括："
            f"{issues_text}。请立刻调用 update_planning_draft 修正 `draft_outline`，"
            "保持执行步骤和步骤状态不变，然后重新调用 request_plan_approval。"
            "`update_planning_draft.draft_outline` 必须是数组，"
            "每个条目都要有标题和 1-2 句具体内容说明，描述最终产物本身，"
            "不要写代码、工具、脚本、目录、发布或 patch。"
            "不要为无关产物类型填写 N/A 占位条目。"
            "请直接按下面这种最小合法结构传参后重试："
            f"`update_planning_draft={{\"summary\":\"修正后的可审批大纲\",\"draft_outline\":{outline_example},\"open_questions\":[]}}`。"
        )
    issues_text = ", ".join(issue_labels_en.get(issue, issue) for issue in issues) or "the user plan is invalid"
    return (
        "System validation reminder: the user plan you just submitted is invalid because "
        f"{issues_text}. Call update_planning_draft immediately to repair `draft_outline`, keep "
        "execution steps and step statuses unchanged, then call request_plan_approval again. "
        "`update_planning_draft.draft_outline` must be an array. "
        "Every item must include a title and 1-2 concrete sentences describing the final deliverable itself, "
        "not code, tools, scripts, folders, publishing, or patch work. "
        "Do not add N/A placeholder items for unrelated deliverable types. "
        "Retry with this minimum valid shape: "
        f"`update_planning_draft={{\"summary\":\"Repaired approval-ready outline\",\"draft_outline\":{outline_example},\"open_questions\":[]}}`."
    )
