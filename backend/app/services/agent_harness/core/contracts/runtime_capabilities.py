from __future__ import annotations


class RuntimeCapabilities:
    """Single source of truth for model-facing runtime capabilities."""

    DEFAULT_OFFICE_AUTHOR = "Harness"

    @staticmethod
    def prompt_section(language: str) -> str:
        if language == "zh":
            return (
                "Runtime capability profile:\n"
                "- exec_command 默认 `base=\"work\"`，即当前 artifact work directory，通常是 `project/<active-skill-id>-prepared/`。运行当前文件用 `python foo.py`，不要写 `python project/foo.py` 或 `cd project && ...`。\n"
                "- 工具支持 `base`: `work`、`project`、`skill`、`references`、`published`、`project:<relative-dir>`；写入仍只允许当前 active work。\n"
                "- 从 active skill 拷贝模板时用 `base=\"skill\"`，目标写入 `$HARNESS_ARTIFACT_WORK_DIR`。\n"
                "- 跨可见根（project/skill/references/published）不要用 `../` 或父级绝对路径遍历——会被 preflight 拦为 path_outside_workspace；访问其他根用对应 `base=` 或 `$HARNESS_*` 环境变量。\n"
                "- 要运行 active skill 里的脚本，先用 `read_file(base=\"skill\")` + `write_file` 把脚本拷进当前 work 目录，再用 exec_command 运行；不要 `cd ../skill` 或 `../skill/...`。\n"
                "- 环境提供 CONVERSATION_DIR、HARNESS_PROJECT_DIR、HARNESS_ARTIFACT_WORK_DIR、HARNESS_ARTIFACT_WORK_ROOT、HARNESS_REFERENCES_DIR、HARNESS_REFERENCE_INPUTS_DIR、HARNESS_REFERENCE_SOURCES_DIR、HARNESS_REFERENCE_GENERATED_DIR、HARNESS_PUBLISHED_DIR、HARNESS_SKILL_ROOT。\n"
                "- 脚本读取素材时用 `$HARNESS_REFERENCES_DIR/...` 或更具体的 `$HARNESS_REFERENCE_INPUTS_DIR/...`；读取 active skill 下的资源（assets/manifest 等）用 `$HARNESS_SKILL_ROOT/...`。不要假设 project cwd 下存在 `references/...` 或 `skill/...`，也不要用 `parents[..]` 之类相对推断去拼 skill 路径。\n"
                "- write_file 用于首次创建完整文件，edit_file 用于编辑已有文本文件，exec_command 用于运行或验证已有命令/脚本。\n"
                "- Python/Node/Shell 逻辑包含多行、循环、函数或复杂转义时，先写入当前 artifact work directory 下的脚本文件，再用 exec_command 执行该文件。\n"
                "- 不要用 shell heredocs、cat > file、echo >> file、printf >> file，或 `python -c`/`node -e` 的长内联脚本来创建或修改较长文件内容。edit_file 使用 old_text/new_text 精确替换已有文本。\n"
                "- 常用 Office/网页处理依赖由运行时预配置；先检查可用性，只在缺失且确有需要时安装到 project/user 范围。\n"
                "- Default Office author is `Harness`; scripts can read HARNESS_AUTHOR_NAME for tracked changes and comments.\n"
            )
        return (
            "Runtime capability profile:\n"
            "- exec_command defaults to `base=\"work\"`: the current artifact work directory, usually `project/<active-skill-id>-prepared/`. Run files as `python foo.py`, not `python project/foo.py` or `cd project && ...`.\n"
            "- Tools support `base`: `work`, `project`, `skill`, `references`, `published`, and `project:<relative-dir>`; writes are still limited to the active work directory.\n"
            "- Use `base=\"skill\"` to copy/read active skill templates and write targets under `$HARNESS_ARTIFACT_WORK_DIR`.\n"
            "- Do not traverse across visible roots (project/skill/references/published) with `../` or parent absolute paths — preflight blocks it as path_outside_workspace; reach other roots via the matching `base=` or a `$HARNESS_*` env var.\n"
            "- To run a script from the active skill, first copy it into the current work directory with `read_file(base=\"skill\")` + `write_file`, then run it with exec_command; do not `cd ../skill` or use `../skill/...`.\n"
            "- The environment provides CONVERSATION_DIR, HARNESS_PROJECT_DIR, HARNESS_ARTIFACT_WORK_DIR, HARNESS_ARTIFACT_WORK_ROOT, HARNESS_REFERENCES_DIR, HARNESS_REFERENCE_INPUTS_DIR, HARNESS_REFERENCE_SOURCES_DIR, HARNESS_REFERENCE_GENERATED_DIR, HARNESS_PUBLISHED_DIR, and HARNESS_SKILL_ROOT.\n"
            "- Scripts should read reference material through `$HARNESS_REFERENCES_DIR/...` or a more specific reference env var; read active-skill resources (assets/manifest, etc.) through `$HARNESS_SKILL_ROOT/...`. Do not assume `references/...` or `skill/...` exists under the project cwd, and do not infer skill paths with `parents[..]`-style relative math.\n"
            "- Use write_file for first-time full-file creation, edit_file for edits to existing text files, and exec_command to run or validate existing commands/scripts.\n"
            "- When Python/Node/Shell logic spans multiple statements, loops, function definitions, or complex escaping, write it to a script under the current artifact work directory first, then execute that file with exec_command.\n"
            "- Do not create or modify longer file contents with shell heredocs, cat > file, echo >> file, printf >> file, or long inline `python -c` / `node -e` scripts. edit_file uses exact old_text/new_text replacements against existing text.\n"
            "- Common Office/web processing dependencies are runtime-provisioned; check availability first and install only missing task-specific packages into project/user scope.\n"
            "- Default Office author is `Harness`; scripts can read HARNESS_AUTHOR_NAME for tracked changes and comments.\n"
        )
