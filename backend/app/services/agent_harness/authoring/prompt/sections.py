from __future__ import annotations


class PromptSections:
    @staticmethod
    def _deliverable_plan_rules(language: str) -> str:
        if language == "zh":
            return (
                "用户可见的计划必须描述产物本身：PPT 要说明几页内容，Word 要说明章节结构，"
                "Excel 要说明工作表结构，HTML 要说明页面区块，不要把写代码、调工具、发布目录这类技术步骤直接展示给用户。"
                "凡调用 update_planning_draft，必须提供 draft_outline；即使仍有 open_questions，也要基于当前信息给出临时草稿大纲。"
                "草稿大纲只是只读预览，不代表已可执行。最终可审批大纲来自最新的 update_planning_draft.draft_outline；"
                "请求审批前必须先把草稿大纲更新为准确版本。"
                "draft_outline 每项只使用 id、title、summary、order、artifact_ref；不要填写或新增 status、progress_message 等进度字段。"
                "summary 是该大纲项最终产物内容的说明，必须写清这一页/章节/工作表/页面区块会呈现什么、为什么需要、关键呈现点是什么；"
                "每项写 1-3 句具体内容说明，中文不少于 20 个字，英文不少于 40 个字符。"
                f"{PromptSections._user_plan_examples('zh')}"
            )
        return (
            "The user-facing plan must describe the deliverable itself: For PPT, describe the slide outline; "
            "For Word, describe the chapter structure; For Excel, describe the worksheet structure; "
            "For HTML, describe the page sections. Do not expose code-writing, tool-running, or publish-folder steps as the user plan. "
            "Every update_planning_draft call must include draft_outline; even when open_questions remain, provide a temporary draft outline from the current information. "
            "The draft outline is a read-only preview and is not executable. The approval outline is derived from the latest update_planning_draft.draft_outline; before requesting approval, "
            "update that draft outline to the exact approval-ready version. "
            "Each draft_outline item may only use id, title, summary, order, and artifact_ref; do not fill or add progress fields such as status or progress_message. "
            "summary explains the final deliverable content for that outline item: what this slide/chapter/worksheet/page section will contain, why it belongs there, and the key points to present. "
            "Write 1-3 concrete sentences per item, at least 20 Chinese characters or 40 English characters. "
            f"{PromptSections._user_plan_examples('en')}"
        )

    @staticmethod
    def _user_plan_examples(language: str) -> str:
        if language == "zh":
            return (
                "示例：update_planning_draft.draft_outline 始终是数组。PPT 例如 "
                "{\"draft_outline\":[{\"id\":\"slide-1\",\"title\":\"封面\",\"summary\":\"说明主题、目标受众和一句话定位，并明确整套内容想让读者形成的第一印象。\"},"
                "{\"id\":\"slide-2\",\"title\":\"核心问题\",\"summary\":\"概括背景、主要痛点和为什么现在值得解决，为后续方案和数据论证建立清晰上下文。\"}]}。"
                "HTML 例如 "
                "{\"draft_outline\":[{\"id\":\"section-1\",\"title\":\"Hero 区\",\"summary\":\"展示品牌定位、核心卖点和主行动按钮，让用户在首屏理解产品价值并知道下一步可以做什么。\"},"
                "{\"id\":\"section-2\",\"title\":\"服务介绍\",\"summary\":\"说明服务内容、适用对象、核心收益和转化入口，帮助用户快速判断是否匹配自己的需求。\"}]}。"
                "不要为不相关产物类型填写 N/A 占位条目。"
            )
        return (
            "Example: update_planning_draft.draft_outline is always an array. PPT example: "
            "{\"draft_outline\":[{\"id\":\"slide-1\",\"title\":\"Cover\",\"summary\":\"State the topic, audience, and one-line positioning, and clarify the first impression the deck should create.\"},"
            "{\"id\":\"slide-2\",\"title\":\"Core problem\",\"summary\":\"Summarize the context, main pain points, and why the problem matters now so the later solution has clear grounding.\"}]}. "
            "HTML example: "
            "{\"draft_outline\":[{\"id\":\"section-1\",\"title\":\"Hero section\",\"summary\":\"Present the brand positioning, key value props, and primary CTA so visitors understand the offer and know what to do next.\"},"
            "{\"id\":\"section-2\",\"title\":\"Services section\",\"summary\":\"Explain the service offer, target clients, key benefits, and conversion path so visitors can judge fit quickly.\"}]}. "
            "Do not add N/A placeholder items for unrelated deliverable types."
        )

    @staticmethod
    def plan_gate(
        *,
        phase: str,
        language: str,
        has_skill: bool,
        has_plan: bool,
        execution_locked: bool,
    ) -> str:
        if language == "zh":
            if phase == "planning" and has_skill and not has_plan and not execution_locked:
                return (
                    "当前是专业模式的首轮规划阶段。当前已加载所选 skill；先基于已加载 skill、"
                    "用户输入和参考资料理解清楚交付物要求。先判断所选 skill 是否声明了必须在制作前"
                    "收集的业务输入、品牌输入、结构选择或交付约束；如果这些输入缺失，且会显著影响"
                    "成品真实性或无法从当前上下文合理推断，请先调用 ask_user，用少量分组字段收集"
                    "最小必要信息，不要把这些必需问题延后到用户点击开始执行之后。"
                    "如果仍在整理理解但尚未可审批，请调用 update_planning_draft 记录当前理解、假设、草稿大纲和未决问题；draft_outline 必填，草稿不会展示开始执行按钮。"
                    "只有当所有阻断性问题已经解决，计划可以被用户批准后直接执行时，才调用 request_plan_approval。"
                    "request_plan_approval 会提交最新草稿大纲用于审批；如果大纲还要调整，先调用 update_planning_draft。"
                    "注意：不要只提交 execution_steps；审批前必须已有完整的 update_planning_draft.draft_outline。"
                    f"{PromptSections._deliverable_plan_rules('zh')}"
                )
            if phase == "revising_plan":
                return (
                    "当前是计划修订阶段。把 current_outline 修订为完整的新大纲；"
                    "如仍需整理或询问，先用 update_planning_draft 或 ask_user；只有修订后的大纲已可审批时才调用 request_plan_approval，等待用户点击开始执行。不要只用普通文本描述修订结果。"
                    "request_plan_approval 会提交最新草稿大纲用于审批；如果大纲还要调整，先调用 update_planning_draft。"
                    "注意：不要只提交 execution_steps；审批前必须已有完整的 update_planning_draft.draft_outline。"
                    f"{PromptSections._deliverable_plan_rules('zh')}"
                )
            if phase == "planning":
                return (
                    "当前是规划阶段。需要记录草稿时调用 update_planning_draft，且必须提供 draft_outline；需要用户决策时调用 ask_user；"
                    "只有完整且可执行的大纲准备好后，才通过 request_plan_approval 提交并等待用户点击开始执行。"
                    "request_plan_approval 会提交最新草稿大纲用于审批；如果大纲还要调整，先调用 update_planning_draft。"
                    "注意：不要只提交 execution_steps；审批前必须已有完整的 update_planning_draft.draft_outline。"
                    f"{PromptSections._deliverable_plan_rules('zh')}"
                )
            if has_plan and execution_locked:
                return (
                    "用户已经开始执行，请按 current_outline 执行。"
                    "当用户可见里程碑或完成状态发生变化时，用 `update_execution_progress` 同步计划卡片。"
                    "执行阶段不得以补充确认、选择方向或等待用户回复作为最终输出；若发现仍有阻断性用户决策，说明规划阶段未完成，应按恢复/失败处理。"
                )
            return (
                "由你判断是否需要计划。简单请求可以直接回答或执行；复杂、多步骤、会生成重要产物或需要用户确认方向的任务，应先用 ask_user 或 update_planning_draft 完成规划，再用 request_plan_approval 提交可审批大纲。"
            )

        if phase == "planning" and has_skill and not has_plan and not execution_locked:
            return (
                "This is the first planning turn for a specialized mode. The selected skill is already loaded; understand the deliverable "
                "from the loaded skill, user request, and references first. Decide whether the selected skill declares business inputs, "
                "brand inputs, structure choices, or delivery constraints that must be collected before production. If those inputs are missing "
                "and would materially affect artifact authenticity or cannot be reasonably inferred from the current context, call ask_user first "
                "with a small grouped schema for the minimum necessary information; do not defer those required questions until after the user starts execution. "
                "If you are still consolidating the plan and it is not approval-ready, call update_planning_draft with the current understanding, assumptions, draft outline, and open questions; draft_outline is required. "
                "Only call request_plan_approval when all blocking questions are resolved and the plan can be executed immediately after approval. "
                "request_plan_approval submits the latest draft outline for approval; if the outline needs changes, call update_planning_draft first. "
                "Do not submit execution_steps only; a complete update_planning_draft.draft_outline must already exist before approval. "
                f"{PromptSections._deliverable_plan_rules('en')}"
            )
        if phase == "revising_plan":
            return (
                "This is the plan revision phase. Rewrite current_outline as the complete revised outline; "
                "use update_planning_draft or ask_user while it is still unresolved, and call request_plan_approval only when the revised plan is approval-ready. Do not describe the revision only in normal prose. "
                "request_plan_approval submits the latest draft outline for approval; if the outline needs changes, call update_planning_draft first. "
                "Do not submit execution_steps only; a complete update_planning_draft.draft_outline must already exist before approval. "
                f"{PromptSections._deliverable_plan_rules('en')}"
            )
        if phase == "planning":
            return (
                "This is the planning phase. Use update_planning_draft for draft understanding with a required draft_outline, ask_user for user-only decisions, "
                "and request_plan_approval only when the complete outline is ready for approval and immediate execution after approval. "
                "request_plan_approval submits the latest draft outline for approval; if the outline needs changes, call update_planning_draft first. "
                "Do not submit execution_steps only; a complete update_planning_draft.draft_outline must already exist before approval. "
                f"{PromptSections._deliverable_plan_rules('en')}"
            )
        if has_plan and execution_locked:
            return (
                "The user has started execution. Execute against current_outline. "
                "Use `update_execution_progress` when user-visible milestones or completion state change so the plan card stays aligned. "
                "Use `update_execution_progress` when user-visible execution state changes or major milestones complete. "
                "When a step starts, mark it in_progress; when a step finishes, mark it completed. "
                "Normal assistant progress text does not count as a plan update. "
                "Do not end execution with a request for confirmation, direction, or a user reply; if a blocking user decision remains, treat it as an incomplete planning failure or recovery case. "
                "Before the final user-facing answer, if the task is complete, synchronize completed steps with `update_execution_progress`."
            )
        return (
            "Decide whether a plan is needed. Simple requests may proceed directly; complex, multi-step, important-output, or direction-sensitive tasks should use ask_user or update_planning_draft during planning, then call request_plan_approval when the outline is ready for execution approval."
        )
