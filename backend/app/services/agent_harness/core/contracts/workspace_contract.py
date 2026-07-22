from __future__ import annotations


class WorkspaceContract:
    """Single source of truth for the semantic harness workspace."""

    TOOL_NAME = "publish_output"
    ROOT_DIR = "CONVERSATION_DIR"
    REFERENCES_DIR = "references"
    PROJECT_DIR = "project"
    PUBLISHED_DIR = "published"

    @staticmethod
    def prompt_section(language: str) -> str:
        if language == "zh":
            return (
                "Workspace contract:\n"
                "- `CONVERSATION_DIR` 是唯一会话工作区根目录；所有语义路径都在这个根目录下。\n"
                "- 模型可见根只有 `project/`、`references/`、`skill/`、`published/`；它们都是真实物理目录名。\n"
                "- `CONVERSATION_DIR/project/` 是唯一可写交付物层；正式交付物先在这里生成，再通过 `register_artifact` 登记、`publish_output` 发布。\n"
                "- 如果本轮存在 active artifact work directory，裸路径和交付物写入都必须落在该目录内；工作区是施工区，不代表交付物身份。\n"
                "- `references/inputs/` 是用户上传原件；`references/sources/` 是检索/解析/RAG 资料；`references/generated/` 是内部工具生成的媒体原件。全部只读。\n"
                "- `CONVERSATION_DIR/published/` 是系统管理的版本化发布层；不要直接写入、重命名、删除或手工放 zip。\n"
                "- `.agent/`、`.meta/`、`logs/` 是系统内部状态；不要作为普通输入、输出或交付物目录。\n"
                "- 写完最终文件后，必须调用 `register_artifact`：只需要 entry/kind；title 和 supporting_files 可选，renderer/exports 由系统推断。\n"
                "- `publish_output` 只发布已登记的 artifact_manifest.entry；不需要参数。\n"
                "- 图片和视频属于 `references/generated/` 参考素材，不作为版本发布交付物；如需在最终页面使用，复制到当前 artifact work directory 内后相对引用。\n"
                "- active skill 正文若已在上下文中加载，以当前上下文为准；`skill/` 仅用于按需读取未预加载的只读 side files。\n"
                "- `base=\"work\"` 是当前 artifact work directory，通常是 `project/<active-skill-id>-prepared/`；`base=\"project\"` 是 `project/` 根；`base=\"project:<relative-dir>\"` 是 project 子目录，写入仍限当前 active work。\n"
                "- `base=\"skill\"` 表示 active skill 只读根。open-design 的 `.od-skills/<template>/` 在这里对应 `skill/`。\n"
                "- 只有当已加载 skill 正文明确引用 side file 且当前任务需要缺失细节时，才读取 `skill/` 下的对应文件。\n"
            )
        return (
            "Workspace contract:\n"
            "- CONVERSATION_DIR is the only workspace root for this conversation; every semantic path lives under it.\n"
            "- The only model-visible roots are `project/`, `references/`, `skill/`, and `published/`; these are real physical directory names.\n"
                "- `CONVERSATION_DIR/project/` is the only writable deliverable layer. Create deliverables here, then register them with `register_artifact` and publish with `publish_output`.\n"
                "- When an active artifact work directory exists, bare paths and deliverable writes must stay inside that directory; the work directory is a construction area, not the deliverable identity.\n"
            "- `references/inputs/` contains user uploads, `references/sources/` contains retrieval/parser/RAG material, and `references/generated/` contains generated media originals. All are read-only.\n"
            "- `CONVERSATION_DIR/published/` is system-managed versioned output. Do not write, rename, delete, or handwrite zip files there.\n"
            "- `.agent/`, `.meta/`, and `logs/` are internal system state, not normal input, output, or deliverable directories.\n"
                "- After writing the final file, call `register_artifact`: only entry/kind are required; title and supporting_files are optional, while renderer/exports are inferred by the system.\n"
            "- `publish_output` only publishes the registered artifact_manifest.entry and takes no parameters.\n"
            "- Images and videos are reference assets under `references/generated/`; to ship them in final HTML, copy them into the current artifact work directory and reference them relatively.\n"
            '- If the active skill body is already loaded in context, treat that context as authoritative; `skill/` is only for on-demand read-only side files.\n'
            '- `base="work"` is the current artifact work directory, usually `project/<active-skill-id>-prepared/`; `base="project"` is the `project/` root; `base="project:<relative-dir>"` is a project subdirectory, while writes stay in active work.\n'
            '- `base="skill"` means the read-only active skill root. open-design `.od-skills/<template>/` maps to `skill/` here.\n'
            "- Read files under `skill/` only when the loaded skill body explicitly references a side file and the current task needs those omitted details.\n"
        )

    @staticmethod
    def new_publish_guidance() -> str:
        return (
            "Create the final file under the current artifact work directory when one is active, register it with register_artifact, then publish the registered entry with publish_output."
        )

    @staticmethod
    def edit_publish_guidance() -> str:
        return (
            "Update the final file under the current artifact work directory when one is active, register it with register_artifact, then publish the registered entry with publish_output."
        )

    @staticmethod
    def generated_path_guidance() -> str:
        return (
            "Generated deliverables live under CONVERSATION_DIR/project, scoped to the current artifact work directory when one is active. Register the final entry with register_artifact and publish through publish_output instead of writing directly into published/."
        )
