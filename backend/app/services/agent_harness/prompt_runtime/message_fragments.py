from __future__ import annotations

import json
from typing import Any

from app.services.agent_harness.authoring.planning.user_plan import build_user_plan_repair_prompt
from app.services.agent_harness.runtime.execution_support.failure_contract import normalize_recovery_hint

from .models import PromptBlock, PromptMode, TurnSpec


def _json_block(block_id: str, payload: dict[str, Any]) -> PromptBlock:
    return PromptBlock(
        id=block_id,
        layer="message",
        content=json.dumps(payload, ensure_ascii=False),
        metadata={"payload_fragment": payload},
    )


def build_runtime_time_payload(spec: TurnSpec) -> PromptBlock | None:
    payload = (spec.side_payload or {}).get("runtime_time")
    if payload is None:
        return None
    return _json_block("state.runtime_time_payload", {"runtime_time": payload})


def build_discovery_request(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.PLANNING_SCHEMA_GENERATION:
        return None
    payload = {
        key: value
        for key, value in dict(spec.side_payload or {}).items()
        if key != "runtime_time"
    }
    return _json_block("state.discovery_request", payload)


def build_selection_request(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.SKILL_SELECTION:
        return None
    payload = {
        key: value
        for key, value in dict(spec.side_payload or {}).items()
        if key != "runtime_time"
    }
    return _json_block("state.selection_request", payload)


def build_design_system_request(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.DESIGN_SYSTEM_SELECTION:
        return None
    payload = {
        key: value
        for key, value in dict(spec.side_payload or {}).items()
        if key != "runtime_time"
    }
    return _json_block("state.design_system_request", payload)


def build_side_classifier_request(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.SIDE_CLASSIFIER:
        return None
    return _json_block("state.side_classifier_request", dict(spec.side_payload or {}))


def build_failure_state(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.RECOVERY_TURN:
        return None
    review = dict(spec.recovery_review or {})
    compact = {
        "failure_kind": review.get("failure_kind"),
        "outcome": review.get("outcome"),
        "required_next_action": review.get("required_next_action"),
        "root_cause_hint": review.get("root_cause_hint"),
        "output_excerpt": review.get("output_excerpt"),
        "recovery_hint": review.get("recovery_hint"),
    }
    return PromptBlock(
        id="state.failure_state",
        layer="message",
        content="Failure state:\n" + json.dumps(compact, ensure_ascii=False, separators=(",", ":")),
    )


def build_recovery_delta(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.RECOVERY_TURN:
        return None
    is_zh = str(spec.language or "").lower().startswith("zh")
    lines = ["继续执行，不要询问用户。"] if is_zh else ["Continue executing without asking the user."]
    structured_hint = normalize_recovery_hint((spec.recovery_review or {}).get("recovery_hint"))
    if structured_hint and structured_hint.get("instruction"):
        lines.append(str(structured_hint["instruction"]))
    if spec.recovery_decision == "switch_strategy":
        lines.append(
            "切换策略。不要重复同一失败路径或同一大段生成内容。"
            if is_zh
            else "Switch strategy. Do not repeat the same failing path or same large generated payload."
        )
    elif spec.recovery_decision == "retry":
        lines.append(
            "用最小可靠动作重试这次恢复。"
            if is_zh
            else "Retry with the smallest reliable recovery step."
        )
    elif not structured_hint or not structured_hint.get("instruction"):
        lines.append(
            "用最小可靠动作修复这个具体问题。"
            if is_zh
            else "Fix the specific issue using the smallest reliable action."
        )
    if structured_hint:
        constraints = structured_hint.get("constraints") or []
        if constraints:
            lines.append(("约束：" if is_zh else "Constraints: ") + "; ".join(str(item) for item in constraints))
        preferred_tools = structured_hint.get("preferred_tools") or []
        if preferred_tools:
            lines.append(("优先工具：" if is_zh else "Preferred tools: ") + ", ".join(str(item) for item in preferred_tools))
        avoid_tools = structured_hint.get("avoid_tools") or []
        if avoid_tools:
            lines.append(("避免工具：" if is_zh else "Avoid tools: ") + ", ".join(str(item) for item in avoid_tools))
        ask_user_when = str(structured_hint.get("ask_user_when") or "").strip()
        if ask_user_when:
            label = "仅在以下情况询问用户：" if is_zh else "Ask the user only when: "
            lines.append(f"{label}{ask_user_when}")
        context_patch = structured_hint.get("context_patch")
        if isinstance(context_patch, dict) and context_patch:
            label = "上下文补丁：" if is_zh else "Context patch: "
            lines.append(f"{label}{context_patch}")
    if spec.recovery_hint:
        lines.append(str(spec.recovery_hint))
    if (spec.recovery_review or {}).get("root_cause_hint"):
        label = "根因提示：" if is_zh else "Root cause hint: "
        lines.append(f"{label}{spec.recovery_review['root_cause_hint']}")
    if (spec.recovery_review or {}).get("output_excerpt"):
        label = "最后错误片段：" if is_zh else "Last error excerpt: "
        lines.append(f"{label}{spec.recovery_review['output_excerpt']}")
    return PromptBlock(id="delta.recovery", layer="message", content="\n".join(lines))


def build_pre_final_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.PRE_FINAL_GATE:
        return None
    payload = dict(spec.side_payload or {})
    kind = str(payload.get("kind") or "").strip()
    text = str(payload.get("message") or "").strip()
    if not text and kind == "plan_sync":
        state_text = json.dumps(payload.get("compact_state") or {}, ensure_ascii=False, separators=(",", ":"))
        text = (
            "系统提醒：模型准备给最终回复，但结构化计划或当前大纲仍显示未完成。"
            f"当前紧凑状态：{state_text}\n"
            "请先做最后一次计划状态判定：如果交付物和任务都已经完成，只调用 update_execution_progress，把已完成步骤标记为 completed，将 current_item_id 置空，并确保计划状态为 completed；如果任务尚未完成，请继续执行下一步，并先用 update_execution_progress 将当前步骤的 status 标记为 in_progress。不要直接输出最终回复，除非计划状态已经同步。"
            if str(spec.language or "").lower().startswith("zh")
            else "System reminder: the model is about to send the final answer, but the structured plan or current outline "
            f"still appears unfinished. Compact state: {state_text}\n"
            "Make one final plan-state decision first: if the deliverable and task are complete, call update_execution_progress only, mark completed steps as completed, clear current_item_id, and ensure the plan status is completed; if work remains, continue the next concrete step and first use update_execution_progress to mark the active step status as in_progress. Do not send the final answer directly unless the plan state is synchronized."
        )
    if text:
        return PromptBlock(id="delta.pre_final", layer="message", content=text)
    return None


def build_final_summary_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.FINAL_SUMMARY:
        return None
    payload = dict(spec.side_payload or {})
    text = str(payload.get("message") or "").strip()
    if not text:
        title = str(payload.get("title") or "当前任务").strip()
        artifact_path = str(payload.get("artifact_path") or "").strip()
        summary_context = {
            key: value
            for key, value in {
                "artifact": payload.get("artifact"),
                "publication": payload.get("publication"),
                "outline_items": payload.get("outline_items"),
                "critique": payload.get("critique"),
            }.items()
            if value not in (None, "", [], {})
        }
        context_text = json.dumps(summary_context, ensure_ascii=False, indent=2) if summary_context else "{}"
        if str(spec.language or "").lower().startswith("zh"):
            text = (
                "系统收尾：产物已经发布成功，请直接给用户一段自然、完整的完成总结，不要调用任何工具。\n"
                f"任务标题：{title}。"
                f"{'已发布文件：' + artifact_path + '。' if artifact_path else ''}\n"
                "请输出 200-400 字中文总结，必须包含：生成内容的大致结构（如页数/章节及每部分用途）、"
                "视觉或设计方向、发布产物位置；如有 Design Jury 质量评分，请简要说明评分结果、选定轮次和是否有必须修复项。"
                "如果交付上下文同时包含 publication.open_design_lint 和 critique，请分别描述：open_design_lint 是发布前 lint 结果，"
                "不能用它代替 Design Jury 的 must-fix 状态。"
                "禁止只回复“已完成”式短句，不要追加泛泛的“如果需要我可以继续...”长尾服务话术。\n"
                f"交付上下文 JSON：\n{context_text}"
            )
        else:
            text = (
                "System finalization: the artifact has already been published successfully. "
                "Reply with a natural completion summary only and do not call any tools. "
                f"Task title: {title}. "
                f"{'Published file: ' + artifact_path + '. ' if artifact_path else ''}"
                "Write 200-400 Chinese characters if the user language is Chinese, otherwise 120-220 words. "
                "Cover the generated content structure, visual/design direction, published artifact location, "
                "and any Design Jury score, selected round, or must-fix status. If Delivery context includes both "
                "publication.open_design_lint and critique, describe them separately: open_design_lint is pre-publish lint "
                "and must not be used as a substitute for the Design Jury must-fix status. Do not produce a terse 'done' "
                "reply or generic follow-up upsell.\n"
                f"Delivery context JSON:\n{context_text}"
            )
    if text:
        return PromptBlock(id="delta.final_summary", layer="message", content=text)
    return None


def build_start_execution_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.START_EXECUTION:
        return None
    is_zh = str(spec.language or "").lower().startswith("zh")
    if is_zh:
        content = (
            "用户已开始执行当前大纲。current_outline 是当前内容蓝图，执行中必须严格按照 current_outline 生成交付内容，并继续用 update_execution_progress 更新执行进度。"
            "执行阶段必须基于用户简报、已加载 skill（含 inputs.example.json 等范例）和已选设计系统，自主生成完整、专业的首版文案与内容，"
            "缺失字段一律用契合品牌的高质量内容补齐，不要使用 lorem ipsum 或通用占位。"
            "不要为可以推断或可以合理撰写的内容暂停去询问用户（如标语、品牌介绍、服务、案例方向、关于语、导航名称等都自己写）；"
            "也不要把整轮停下来等用户回复字段。执行阶段不得以补充确认、选择方向或等待用户回复作为最终输出；"
            "如果发现仍有阻断性用户决策，说明审批前规划未完成，应按恢复或失败处理，而不是在执行阶段追问。"
            "沟通方式：用户看不到你的工具调用，只能看到你的文字。每次调用工具前，先用一句话面向用户说明你接下来要做什么；"
            "写入或修改文件后，用一句话说明你做了什么（不要复述文件内容）；执行命令后，简要报告结果。"
            "叙述要简短、用自然语言、不要出现工具名（如 write_file/exec_command），也不要解释你为什么搜索或读取；"
            "这些叙述是普通正文，绝不要写进 <artifact> 交付物里。"
        )
    else:
        content = (
            "The user has started executing the current outline. current_outline is the content blueprint; "
            "generate the deliverable strictly against it and keep using update_execution_progress to sync progress. "
            "During execution you must autonomously author complete, professional first-draft content from the user's brief, "
            "the loaded skill (including worked examples like inputs.example.json), and the selected design system. "
            "Fill every missing field with high-quality, brand-appropriate content; never use lorem ipsum or generic placeholders. "
            "Do not pause to ask the user for anything you can reasonably infer or write yourself. Do not stop the whole turn to wait for the user to fill in fields. "
            "Do not end execution with a request for confirmation, direction, or a user reply; if a blocking user decision remains, treat it as an incomplete planning failure or recovery case instead of asking during execution. "
            "Communication: the user cannot see your tool calls, only your text. Before each tool call, state in one sentence what you're about to do; "
            "after writing or editing a file, state in one sentence what you did (do not restate file contents); after running a command, briefly report the outcome. "
            "Keep narration short and in natural language, never mention tool names (e.g. write_file/exec_command), and do not justify why you search or read; "
            "this narration is ordinary prose and must never go inside the <artifact> deliverable."
        )
    return PromptBlock(
        id="delta.start_execution",
        layer="message",
        content=content,
    )


def build_plan_approval_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.PLAN_APPROVAL:
        return None
    return PromptBlock(
        id="delta.plan_approval",
        layer="message",
        content="用户已确认当前大纲。请严格按照 approved_plan 执行。",
    )


def build_user_plan_repair_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.USER_PLAN_REPAIR:
        return None
    payload = dict(spec.side_payload or {})
    content = build_user_plan_repair_prompt(
        payload.get("plan_state") if isinstance(payload.get("plan_state"), dict) else {},
        mode=str(payload.get("mode") or ""),
        issues=list(payload.get("issues") or []),
        language=spec.language,
    )
    return PromptBlock(id="delta.user_plan_repair", layer="message", content=content)


def build_plan_revision_request_message(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.PLAN_REVISION_REQUEST:
        return None
    instruction = str((spec.side_payload or {}).get("instruction") or "").strip()
    if not instruction:
        return None
    return PromptBlock(
        id="delta.plan_revision_request",
        layer="message",
        content=f"用户要求修改当前大纲：{instruction}\n请先用 update_planning_draft 记录未完成的修订理解；只有修订后的完整 current_outline 可审批时，才调用 request_plan_approval。更新后的大纲会等待用户点击开始执行。",
    )

