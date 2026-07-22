"""Lightweight zh/en localization for Harness tool schemas."""

from __future__ import annotations

from copy import deepcopy

_TOOL_I18N: dict[str, dict[str, object]] = {
    "ask_user": {
        "description": {
            "zh": "向用户发起选择题交互，不是表单生成器。ask_user 只承接用户决策；如需用户先查看阶段成果、方案、brief、策略或图稿选择依据，必须先用普通 assistant 正文展示完整内容，再调用 ask_user。直接传 title、description（可选）、submit_label、questions、answers（可选）这些顶层参数；description 只能做短提示，不能承载方案、简报、阶段成果或选择依据。问题优先使用 single 或 multiple，UI 会自动提供“其他”输入。input 只能少量使用，每次最多 1 个，仅用于品牌名、URL、邮箱或一行约束等无法推断的短事实；不要用 input 收集长文案、brief 或内容创作。不要传 schema.fields 或长表单。Agent 循环会暂停，直到用户回复后再继续。",
            "en": "Ask the user with choice questions, not a form builder. ask_user only captures the user's decision; if the user must review stage results, a proposal, a brief, a strategy, or artwork-selection rationale first, present the complete content as normal assistant text before calling ask_user. Pass title, description (optional), submit_label, questions, and answers (optional) as top-level arguments. The description field is only short helper text and must not carry proposals, briefs, stage results, or selection rationale. Prefer single or multiple questions, and the UI automatically provides Other input. Use input sparingly, at most once per call, only for short factual details such as a brand name, URL, email, or one-line constraint that cannot be inferred; do not use input for long copy, briefs, or content writing. Do not pass schema.fields or long forms. The agent loop pauses until the user responds.",
        },
        "fields": {
            "title": {"zh": "交互卡标题", "en": "Interaction card title"},
            "description": {"zh": "可选短提示；不得承载方案、简报、阶段成果或选择依据", "en": "Optional short helper text; must not carry proposals, briefs, stage results, or selection rationale"},
            "submit_label": {"zh": "提交按钮文案", "en": "Submit button label"},
            "questions": {"zh": "问题数组，1-5 个；single/multiple 每题 2-4 个选项；input 每次最多 1 个且无选项", "en": "Questions, 1-5 items; single/multiple questions have 2-4 options; input is at most one per call and has no options"},
            "answers": {
                "zh": "可选的历史答案对象，按 question id 组织；没有时可省略或传 null",
                "en": "Optional previous answers object keyed by question id; omit or pass null when there are no prior answers",
            },
        },
        "defs": {
            "AskUserQuestionInput": {
                "id": {"zh": "稳定问题 ID，必须唯一，使用 snake_case", "en": "Stable unique question id in snake_case"},
                "header": {"zh": "短标签，用于问题小标题", "en": "Short header label for the question"},
                "question": {"zh": "用户需要回答的具体选择题", "en": "The concrete choice question for the user"},
                "type": {"zh": "问题类型：single、multiple 或 input；input 少量使用", "en": "Question type: single, multiple, or input; use input sparingly"},
                "max_selections": {"zh": "多选问题的最大可选数量（可选）", "en": "Optional maximum selections for multiple questions"},
                "options": {"zh": "选项数组；不要包含“其他”，UI 会自动提供", "en": "Option array; do not include Other because the UI provides it automatically"},
            },
            "AskUserOptionInput": {
                "label": {"zh": "选项显示文案", "en": "Option label"},
                "value": {"zh": "选项提交值", "en": "Option value"},
                "description": {"zh": "可选的选项补充说明", "en": "Optional option description"},
                "preview_url": {"zh": "可选的预览图地址", "en": "Optional preview image URL"},
                "metadata": {"zh": "可选附加元数据", "en": "Optional extra metadata"},
            },
        },
    },
    "edit_file": {
        "description": {
            "zh": "用 old_text 到 new_text 的批量替换编辑 project/ 下的已有文本文件。每段 old_text 默认必须唯一匹配，"
                  "或在该段设 replace_all=true 替换全部出现（适合重命名）。匹配会自动容忍弯引号/直引号、tab/空格差异，"
                  "按 read 工具显示的样子复制即可。old_text 要用文件当前文本，不要用你刚改成的值。",
            "en": "Edit an existing text file under project/ with batched old_text to new_text replacements. Each "
                  "old_text must match once by default, or set replace_all=true on that edit to replace every "
                  "occurrence (good for renames). Matching tolerates curly/straight quotes and tab/space "
                  "differences — copy text as the read tool shows it. Use the file's current text as old_text, "
                  "not the value you just changed it to.",
        },
        "fields": {
            "file_path": {"zh": "project/ 下的目标文本文件路径，例如 project/foo.py", "en": "Target text file path under project/, such as project/foo.py"},
            "edits": {"zh": "要原子应用的一组文本替换（任一段失败则整批不写）", "en": "Text replacements to apply atomically (if any one fails, none are written)"},
            "old_text": {"zh": "文件中的原始文本；默认唯一匹配，容忍引号与 tab/空格差异", "en": "Original text in the file; unique by default, tolerant of quote and tab/space differences"},
            "new_text": {"zh": "替换后的文本", "en": "Replacement text"},
            "replace_all": {"zh": "替换 old_text 的全部出现而非要求唯一匹配；默认 false", "en": "Replace every occurrence of old_text instead of requiring a unique match; default false"},
        },
        "defs": {
            "TextReplacementInput": {
                "old_text": {"zh": "文件中的原始文本；默认唯一匹配，容忍引号与 tab/空格差异", "en": "Original text in the file; unique by default, tolerant of quote and tab/space differences"},
                "new_text": {"zh": "替换后的文本", "en": "Replacement text"},
                "replace_all": {"zh": "替换 old_text 的全部出现而非要求唯一匹配；默认 false", "en": "Replace every occurrence of old_text instead of requiring a unique match; default false"},
            },
        },
    },
    "analyze_image": {
        "description": {
            "zh": "使用默认图片分析模型分析图片，支持 URL、data URI、本地路径和工作区相对路径。",
            "en": "Analyze an image with the default image-analysis model. Supports URLs, data URIs, local paths, and workspace-relative paths.",
        },
        "fields": {
            "image_url": {"zh": "要分析的图片地址、上传路径或本地/工作区路径", "en": "Image to analyze: URL, upload path, local path, or workspace-relative path"},
            "question": {"zh": "可选分析问题；默认会要求详细描述图片", "en": "Optional analysis question; defaults to a detailed description request"},
        },
    },
    "Agent": {
        "description": {
            "zh": "同步委派一个边界清晰的任务给内置子代理，父代理会等待结果返回。",
            "en": "Synchronously delegate a bounded task to a built-in subagent and wait for the result.",
        },
        "fields": {
            "description": {"zh": "3-5 个词的任务短描述", "en": "Short 3-5 word task description"},
            "prompt": {"zh": "完整交给子代理执行的任务说明", "en": "Complete task prompt for the subagent"},
            "subagent_type": {"zh": "要使用的内置子代理类型", "en": "Built-in subagent profile to use"},
        },
    },
    "capture_artifact_evidence": {
        "description": {
            "zh": "内部 QualityReview 证据工具：为冻结的 artifact entry 捕获受控评审证据。",
            "en": "Internal QualityReview evidence tool: capture controlled evidence for the frozen artifact entry.",
        },
        "fields": {
            "review_id": {"zh": "当前 QualityReview review_id", "en": "Current QualityReview review_id"},
            "entry": {"zh": "冻结的 artifact entry", "en": "Frozen artifact entry"},
            "viewport": {"zh": "证据视口：desktop 或 mobile", "en": "Evidence viewport: desktop or mobile"},
        },
    },
    "exec_command": {
        "description": {
            "zh": "在 CONVERSATION_DIR/project 中执行命令；运行项目文件写 python foo.py，不要写 python project/foo.py。多行脚本或复杂验证先用 write_file 写成脚本文件，再运行 python script.py/node script.js；不要把多行代码内联到 python -c 或 shell 引号中。base 决定执行目录；不要用 ../ 跨工作区根（会被拦截），访问其他根用对应 base 或 $HARNESS_* 路径。要运行 skill 里的脚本，先用 read_file(base=\"skill\")+write_file 把它拷进 work 目录再运行。stdout/stderr 分别最多返回 16384 bytes，超出会保留开头并追加截断提示。",
            "en": "Run commands from CONVERSATION_DIR/project; run project files as python foo.py, not python project/foo.py. For multi-line scripts or complex validation, first use write_file to create a script file, then run python script.py/node script.js; do not inline multi-line code inside python -c or shell quotes. base sets the working directory; never use ../ to cross workspace roots (it is blocked) — reach other roots via the matching base or a $HARNESS_* path. To run a skill script, copy it into the work directory first with read_file(base=\"skill\")+write_file, then run it. stdout/stderr each return up to 16384 bytes; excess output keeps the prefix and appends a truncation notice.",
        },
        "fields": {
            "command": {"zh": "要运行或启动的命令；action=run/start 时必填", "en": "Command to run or start; required for action=run/start"},
            "timeout": {"zh": "等待命令完成或会话输出的秒数，最大 300 秒", "en": "Seconds to wait for command completion or session output, up to 300"},
            "action": {"zh": "命令执行模式；通常保持默认 run，除非系统恢复流程或明确场景要求其他模式", "en": "Command execution mode; usually keep the default run unless recovery flow or a clear scenario requires another mode."},
            "session_id": {"zh": "某些非默认执行模式需要的会话标识", "en": "Session identifier required by some non-default execution modes"},
            "input": {"zh": "某些非默认执行模式需要提供的输入文本", "en": "Input text required by some non-default execution modes"},
        },
    },
    "read_file": {
        "description": {
            "zh": "从 CONVERSATION_DIR 下读取文本文件。默认读取到文件末尾，并在结果元数据中提供 total_lines、start_line 和 num_lines；长文件可用 offset/limit 分页读取。",
            "en": "Read a text file under CONVERSATION_DIR. By default reads to EOF and includes total_lines, start_line, and num_lines in metadata; use offset/limit to page through long files.",
        },
        "fields": {
            "path": {"zh": "文件路径；使用 base 参数时为相对该 base 的路径，不使用 base 时可兼容 project/...、references/...、skill/... 或 published/... 形式", "en": "File path; when base is provided this is relative to that base, otherwise project/..., references/..., skill/..., or published/... forms are accepted"},
            "offset": {"zh": "从第几行开始读取，0 表示文件开头；用于分页读取长文件", "en": "Zero-based line offset; use it to page through long files"},
            "limit": {"zh": "最多返回多少行；省略则读取到文件末尾", "en": "Maximum number of lines to return; omit to read to EOF"},
        },
    },
    "write_file": {
        "description": {
            "zh": "把字符串 content 原样写入工作区文件；用于首次创建文件或整体重写，只改局部时用 edit_file。",
            "en": "Write the string content verbatim to a file in the workspace; use it to create a new file or completely rewrite one. To change only part of an existing file, use edit_file.",
        },
        "fields": {
            "path": {"zh": "文件路径；使用 base 参数时为相对该 base 的路径，默认 base=work 即当前 artifact work directory", "en": "File path; when base is provided this is relative to that base. The default base=work is the current artifact work directory"},
            "content": {"zh": "要写入的完整文件内容（原样写入的字符串）", "en": "Full file content to write (a string written verbatim)"},
            "overwrite": {"zh": "是否允许覆盖已有文件", "en": "Whether to overwrite an existing file"},
        },
    },
    "list_files": {
        "description": {
            "zh": "结构化列出 CONVERSATION_DIR 下的文件和目录。",
            "en": "List files and directories structurally under CONVERSATION_DIR.",
        },
        "fields": {
            "path": {"zh": "目录或文件路径；使用 base 参数时为相对该 base 的路径，省略时列出所选 base", "en": "Directory or file path; when base is provided this is relative to that base, omit to list the selected base"},
            "recursive": {"zh": "是否递归列出子目录", "en": "Whether to recursively list subdirectories"},
            "max_entries": {"zh": "最多返回条目数，范围 1 到 1000", "en": "Maximum number of entries to return, from 1 to 1000"},
        },
    },
    "glob_files": {
        "description": {
            "zh": "按 glob 文件名模式在所选 base 下查找文件；沿用 Claude Code Glob 的结果字段，但路径解析使用当前 harness 的 base/path 语义和只读权限。",
            "en": "Find files by glob pattern under the selected base; keeps Claude Code Glob result fields while using the harness base/path semantics and read permission checks.",
        },
        "fields": {
            "base": {"zh": "语义搜索根：work、project、skill、references、published 或 project:<相对目录>", "en": "Semantic search root: work, project, skill, references, published, or project:<relative-dir>"},
            "path": {"zh": "在所选 base 下搜索的目录；省略时搜索该 base 根目录", "en": "Directory to search under the selected base; omit to search the base root"},
            "pattern": {"zh": "用于匹配文件路径的 glob 模式，例如 **/*.py 或 src/**/*.ts", "en": "Glob pattern used to match file paths, such as **/*.py or src/**/*.ts"},
            "max_results": {"zh": "最多返回多少个匹配文件；默认 100", "en": "Maximum matching files to return; defaults to 100"},
        },
    },
    "grep_files": {
        "description": {
            "zh": "用 ripgrep 正则在所选 base 下搜索文件内容；支持 Claude Code Grep 的文件列表、内容和计数模式，同时保留当前 harness 的 base/path 语义和只读权限。",
            "en": "Search file contents with ripgrep under the selected base; supports Claude Code Grep file-list, content, and count modes while preserving harness base/path semantics and read permission checks.",
        },
        "fields": {
            "base": {"zh": "语义搜索根：work、project、skill、references、published 或 project:<相对目录>", "en": "Semantic search root: work, project, skill, references, published, or project:<relative-dir>"},
            "path": {"zh": "在所选 base 下搜索的文件或目录；省略时搜索该 base 根目录", "en": "File or directory to search under the selected base; omit to search the base root"},
            "pattern": {"zh": "要搜索的正则表达式模式", "en": "Regular expression pattern to search for"},
            "glob": {"zh": "可选文件 glob 过滤，例如 *.js 或 *.{ts,tsx}", "en": "Optional file glob filter, such as *.js or *.{ts,tsx}"},
            "output_mode": {"zh": "输出模式：content 返回匹配行，files_with_matches 返回文件路径，count 返回每个文件的匹配次数", "en": "Output mode: content returns matching lines, files_with_matches returns file paths, count returns match counts per file"},
            "-B": {"zh": "content 模式下每个匹配前返回的上下文行数", "en": "Number of context lines before each match in content mode"},
            "-A": {"zh": "content 模式下每个匹配后返回的上下文行数", "en": "Number of context lines after each match in content mode"},
            "-C": {"zh": "content 模式下每个匹配前后都返回的上下文行数", "en": "Number of context lines before and after each match in content mode"},
            "-n": {"zh": "content 模式下是否显示行号，默认 true", "en": "Whether to show line numbers in content mode; defaults to true"},
            "-i": {"zh": "是否执行大小写不敏感搜索", "en": "Whether to perform case-insensitive search"},
            "file_type": {"zh": "可选 ripgrep 文件类型过滤，例如 js、ts、py、html、css、json、md；仅用于按语言或扩展名过滤文件", "en": "Optional ripgrep file type filter, such as js, ts, py, html, css, json, or md; only filters files by language or extension"},
            "head_limit": {"zh": "最多返回前 N 行或条目；省略时默认 250，传 0 表示不限制", "en": "Limit output to first N lines or entries; defaults to 250 when omitted, pass 0 for unlimited"},
            "offset": {"zh": "先跳过多少行或条目，再应用 head_limit", "en": "Skip this many lines or entries before applying head_limit"},
            "multiline": {"zh": "是否启用跨行匹配模式，使 . 可以匹配换行", "en": "Whether to enable multiline matching where . can match newlines"},
        },
    },
    "workspace_map": {
        "description": {
            "zh": "返回当前会话的 CONVERSATION_DIR 工作区映射、默认命令 cwd 和 v2 路径写法示例。",
            "en": "Return the current CONVERSATION_DIR workspace map, default command cwd, and v2 path-form examples.",
        },
        "fields": {},
    },
    "publish_output": {
        "description": {
            "zh": "发布已经通过 register_artifact 登记的 artifact_manifest.entry；此工具不需要参数。Home open-design HTML 会在发布前执行 HTML lint，P0 问题必须修复后重试。",
            "en": "Publish the artifact_manifest.entry registered by register_artifact; this tool needs no parameters. Home open-design HTML runs HTML lint before publishing, and P0 findings must be repaired before retrying.",
        },
        "fields": {},
    },
    "register_artifact": {
        "description": {
            "zh": "登记最终交付物 manifest。⚠️ 本工具没有 base 参数：所有路径一律相对 project/ 根目录，"
                  "不是 read_file/edit_file 里 base:\"work\" 的工作目录。必须自己带上工作目录前缀，"
                  "例如 open-design-landing-prepared/index.html。entry 是用户最终打开的主文件；"
                  "构建脚本、校验脚本等放 supporting_files。",
            "en": "Register the final deliverable manifest. ⚠️ This tool has NO base parameter: every path is "
                  "relative to the project/ root, NOT the base:\"work\" work dir used by read_file/edit_file. "
                  "You must include the work-folder prefix yourself, e.g. open-design-landing-prepared/index.html. "
                  "entry is the user-facing primary file; build/validation scripts go in supporting_files.",
        },
        "fields": {
            "entry": {
                "zh": "最终主文件，相对 project/ 的完整路径（含工作目录前缀），例如 "
                      "open-design-landing-prepared/index.html。必须是已存在的真实文件，"
                      "不能是目录；禁止绝对路径和 ../。",
                "en": "Final primary file as a full path relative to project/ (include the work-folder prefix), "
                      "e.g. open-design-landing-prepared/index.html. Must be an existing real file, "
                      "not a directory; no absolute paths or ../.",
            },
            "kind": {"zh": "artifact 类型：spreadsheet、document、deck、html、svg、file 或 code", "en": "Artifact kind: spreadsheet, document, deck, html, svg, file, or code"},
            "title": {"zh": "可选用户可见标题；省略时使用文件名", "en": "Optional user-facing title; omit to use the filename"},
            "supporting_files": {
                "zh": "构建/校验等辅助文件路径数组，规则同 entry：每项都是相对 project/ 的完整路径、"
                      "必须逐个指向已存在的【文件】。❌ 不要传目录（如 assets/）——目录会被判为不存在；"
                      "要登记整个目录里的图片就逐个列出文件，否则直接省略本字段。",
                "en": "Array of build/validation helper file paths. Same rule as entry: each item is a full path "
                      "relative to project/ and must point to an existing FILE. ❌ Do NOT pass directories "
                      "(e.g. assets/) — a directory is rejected as 'does not exist'. List individual files, "
                      "or just omit this field.",
            },
        },
    },
    "update_planning_draft": {
        "description": {
            "zh": "更新规划草稿；用于记录当前理解、已确认信息、假设、草稿大纲和未决问题。不会请求用户批准，也不会显示开始执行按钮。",
            "en": "Update the planning draft: current understanding, confirmed inputs, assumptions, draft outline, and open questions. This never requests approval and never shows a start-execution button.",
        },
        "fields": {
            "summary": {"zh": "当前规划理解摘要", "en": "Current planning understanding"},
            "confirmed_inputs": {"zh": "已确认或已推断的信息对象", "en": "Confirmed or inferred inputs"},
            "assumptions": {"zh": "当前草稿假设列表", "en": "Current draft assumptions"},
            "draft_outline": {
                "zh": "必填草稿大纲条目；只读预览、不可执行；每项需有详细 summary",
                "en": "Required draft outline items; read-only preview, not executable; each item needs a detailed summary",
            },
            "open_questions": {"zh": "仍需解决的问题列表", "en": "Open questions still to resolve"},
        },
    },
    "request_plan_approval": {
        "description": {
            "zh": "提交最新规划草稿用于审批。只有所有阻断性问题已解决、用户批准后可直接执行时才能调用；审批大纲来自 planning_draft.draft_outline，调用后会展示开始执行按钮。",
            "en": "Submit the latest planning draft for approval. Use only after all blocking questions are resolved and the plan can be executed immediately after approval; the approval outline comes from planning_draft.draft_outline and this shows the start-execution button.",
        },
        "fields": {
            "title": {"zh": "内部执行计划标题", "en": "Internal execution plan title"},
            "summary": {"zh": "一句话审批计划摘要", "en": "One-line approval plan summary"},
            "user_plan": {"zh": "可选展示与文件元数据；审批大纲来自最新规划草稿", "en": "Optional display and artifact metadata; the approval outline comes from the latest planning draft"},
            "execution_steps": {"zh": "用户批准后的真实执行步骤", "en": "Executable steps after approval"},
            "assumptions": {"zh": "执行阶段采用的默认假设", "en": "Defaults and assumptions for execution"},
            "verification": {"zh": "交付前验证方式", "en": "Verification checks before delivery"},
            "followups": {"zh": "非阻断后续事项", "en": "Non-blocking follow-up items"},
            "open_questions": {"zh": "必须为空；有阻断问题时不能请求审批", "en": "Must be empty; approval cannot be requested with blocking questions"},
        },
    },
    "update_execution_progress": {
        "description": {
            "zh": "更新已批准计划的执行进度。只能更新步骤状态、当前大纲条目和进度说明；不能创建或修改审批大纲。",
            "en": "Update progress for an approved plan. Only updates step status, current outline item, and progress message; it cannot create or revise the approved outline.",
        },
        "fields": {
            "title": {"zh": "可选执行计划标题", "en": "Optional execution plan title"},
            "summary": {"zh": "可选执行摘要", "en": "Optional execution summary"},
            "steps": {"zh": "完整且有序的执行步骤列表", "en": "Full ordered execution step list"},
            "current_item_id": {"zh": "当前正在制作的已批准大纲条目 ID", "en": "Approved outline item currently being produced"},
            "progress_message": {"zh": "面向用户的进度说明", "en": "User-facing progress message"},
            "status": {"zh": "总体执行状态", "en": "Overall execution status"},
            "explanation": {"zh": "可选进度变更说明", "en": "Optional progress explanation"},
        },
    },
    "generate_image": {
        "description": {
            "zh": "根据文本提示词生成图片。输出会注册为 references/generated 下的只读参考素材。",
            "en": "Generate an image from a text prompt. Output is registered as a read-only reference asset under references/generated.",
        },
        "fields": {
            "prompt": {"zh": "详细图片提示词", "en": "Detailed image-generation prompt"},
            "aspect_ratio": {"zh": "图片宽高比，如 1:1、16:9、9:16", "en": "Image aspect ratio such as 1:1, 16:9, or 9:16"},
            "resolution": {"zh": "输出分辨率档位，如 1K、2K、4K", "en": "Output resolution tier such as 1K, 2K, or 4K"},
            "reference_image_urls": {"zh": "参考图片 URL 或相对路径列表", "en": "Reference image URLs or relative paths"},
        },
    },
    "generate_video": {
        "description": {
            "zh": "根据文本提示词生成视频。输出会注册为 references/generated 下的只读参考素材。",
            "en": "Generate a video from a text prompt. Output is registered as a read-only reference asset under references/generated.",
        },
        "fields": {
            "prompt": {"zh": "详细视频提示词", "en": "Detailed video-generation prompt"},
            "aspect_ratio": {"zh": "视频宽高比，如 16:9、9:16、1:1", "en": "Video aspect ratio such as 16:9, 9:16, or 1:1"},
            "duration": {"zh": "视频时长（秒）", "en": "Video duration in seconds"},
            "output": {"zh": "输出控制参数对象", "en": "Output options object"},
            "input": {"zh": "输入模式与参考素材对象", "en": "Input mode and reference inputs object"},
            "model_options": {"zh": "模型专属参数对象", "en": "Model-specific options object"},
            "negative_prompt": {"zh": "负面提示词", "en": "Negative prompt"},
            "watermark": {"zh": "是否添加水印", "en": "Whether to add watermark"},
        },
        "defs": {
            "GenerateVideoOutputOptions": {
                "resolution": {"zh": "视频分辨率，如 720p、1080p", "en": "Video resolution such as 720p or 1080p"},
                "generate_audio": {"zh": "是否生成音频", "en": "Whether to generate audio"},
            },
            "GenerateVideoInputSpec": {
                "mode": {"zh": "输入模式：text、frames 或 references", "en": "Input mode: text, frames, or references"},
                "frames": {"zh": "首尾帧输入对象", "en": "Frame control input object"},
                "references": {"zh": "参考素材输入对象", "en": "Reference input object"},
            },
            "GenerateVideoFrameInput": {
                "first_image_url": {"zh": "首帧图片 URL 或相对路径", "en": "First-frame image URL or relative path"},
                "last_image_url": {"zh": "尾帧图片 URL 或相对路径", "en": "Last-frame image URL or relative path"},
            },
            "GenerateVideoReferenceInput": {
                "image_urls": {"zh": "参考图片列表", "en": "Reference image URLs"},
                "video_urls": {"zh": "参考视频列表", "en": "Reference video URLs"},
                "audio_urls": {"zh": "参考音频列表", "en": "Reference audio URLs"},
            },
            "GenerateVideoModelOptions": {
                "kling": {"zh": "Kling 系列模型专属参数", "en": "Kling-family model options"},
                "kling_v3": {"zh": "Kling 3 专属参数", "en": "Kling 3 options"},
                "seedance_2": {"zh": "Seedance 2.0 专属参数", "en": "Seedance 2.0 options"},
            },
            "GenerateVideoKlingOptions": {
                "mode": {"zh": "Kling 模式", "en": "Kling mode"},
            },
            "GenerateVideoKlingV3Options": {
                "multi_shot": {"zh": "是否启用多镜头", "en": "Whether to enable multi-shot mode"},
                "shot_type": {"zh": "分镜模式", "en": "Shot planning mode"},
                "multi_prompt": {"zh": "自定义分镜列表", "en": "Custom multi-shot prompts"},
                "element_list": {"zh": "主体元素列表", "en": "Tracked subject elements"},
            },
            "GenerateVideoSeedance2Options": {
                "return_last_frame": {"zh": "是否返回尾帧", "en": "Whether to return the last frame"},
            },
        },
    },
    "web_search": {
        "description": {
            "zh": "搜索网络以获取实时信息、近期新闻或训练数据外的新内容。",
            "en": "Search the web for real-time information, recent news, or content outside the training data.",
        },
        "fields": {
            "query": {"zh": "搜索关键词", "en": "Search query"},
            "num_results": {"zh": "返回结果数量，默认 5，最多 10", "en": "Number of results to return, default 5 and maximum 10"},
            "search_type": {"zh": "搜索类型：text 或 image", "en": "Search type: text or image"},
        },
    },
    "fetch_webpage": {
        "description": {
            "zh": "抓取指定网页并根据当前需求压缩页面内容，返回面向任务的小结果。",
            "en": "Fetch a specific webpage and compress its content for the current task into a small result.",
        },
        "fields": {
            "url": {"zh": "要抓取的网页地址（HTTP 或 HTTPS）", "en": "URL of the webpage to fetch (HTTP or HTTPS)"},
            "prompt": {"zh": "希望基于该网页完成的提取或总结任务", "en": "Task to perform against the fetched webpage content"},
        },
    },
    "search_harness_history": {
        "description": {
            "zh": "搜索当前会话的历史上下文、压缩边界、会话快照和工具结果，用于压缩后找回原始记忆。",
            "en": "Search past harness context, compaction boundaries, session snapshots, and tool results to recover original memory after compaction.",
        },
        "fields": {
            "query": {"zh": "搜索关键词，建议使用文件名、错误信息、函数名或用户原话", "en": "Search terms; prefer file names, error messages, function names, or the user's original wording"},
            "sources": {"zh": "可选来源过滤：conversation、tool_results、compactions、collapse_commits", "en": "Optional source filter: conversation, tool_results, compactions, or collapse_commits"},
            "limit": {"zh": "最多返回多少条匹配，默认 8", "en": "Maximum number of matches to return; defaults to 8"},
            "before_seq": {"zh": "只搜索某个序号之前的会话消息", "en": "Only search conversation messages before this sequence number"},
        },
    },
}


def tool_description(tool_name: str, language: str, fallback: str) -> str:
    entry = _TOOL_I18N.get(tool_name, {})
    descriptions = entry.get("description", {})
    if isinstance(descriptions, dict):
        return str(descriptions.get(language) or descriptions.get("zh") or fallback)
    return fallback


def localize_tool_schema(tool_name: str, schema: dict, language: str) -> dict:
    localized = deepcopy(schema)
    entry = _TOOL_I18N.get(tool_name, {})
    field_texts = entry.get("fields", {})
    defs_texts = entry.get("defs", {})

    properties = localized.get("properties", {})
    if isinstance(properties, dict) and isinstance(field_texts, dict):
        for field_name, variants in field_texts.items():
            if field_name in properties and isinstance(variants, dict):
                text = variants.get(language) or variants.get("zh")
                if text:
                    properties[field_name]["description"] = text

    schema_defs = localized.get("$defs", {})
    if isinstance(schema_defs, dict) and isinstance(defs_texts, dict):
        for def_name, fields in defs_texts.items():
            def_schema = schema_defs.get(def_name)
            if not isinstance(def_schema, dict):
                continue
            def_props = def_schema.get("properties", {})
            if not isinstance(def_props, dict) or not isinstance(fields, dict):
                continue
            for field_name, variants in fields.items():
                if field_name in def_props and isinstance(variants, dict):
                    text = variants.get(language) or variants.get("zh")
                    if text:
                        def_props[field_name]["description"] = text

    return localized
