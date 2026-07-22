from __future__ import annotations

from app.services.agent_harness.capabilities.skills.router import (
    build_mode_contract,
    normalize_artifact_mode,
)
from app.services.agent_harness.capabilities.skill_protocols import ProtocolRuntimeContext, resolve_skill_protocol
from app.services.agent_harness.core.contracts.runtime_capabilities import RuntimeCapabilities
from app.services.agent_harness.core.contracts.workspace_contract import WorkspaceContract
from app.services.agent_harness.runtime.open_design.eligibility import is_home_open_design_html_run

from .models import PromptBlock, PromptMode, TurnSpec


def build_workspace_contract(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    return PromptBlock(
        id="environment.workspace_contract",
        layer="system",
        content=WorkspaceContract.prompt_section(spec.language),
        rule_family="filesystem_runtime_publish",
    )


def build_runtime_capabilities(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    return PromptBlock(
        id="environment.runtime_capabilities",
        layer="system",
        content=RuntimeCapabilities.prompt_section(spec.language),
    )


def build_artifact_mode_contract(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    content = spec.mode_contract_text
    if not content:
        content = build_mode_contract(normalize_artifact_mode(spec.artifact_mode), skill=spec.skill)
    if not str(content or "").strip():
        return None
    return PromptBlock(
        id="environment.artifact_mode",
        layer="system",
        content="Artifact mode contract:\n" + str(content).strip(),
    )


def build_canvas_media_operation_contract(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    runtime_profile = str((spec.conversation or {}).get("runtime_profile") or "").strip().lower()
    artifact_mode = str(spec.artifact_mode or (spec.conversation or {}).get("artifact_mode") or "").strip().lower()
    if runtime_profile != "canvas" or artifact_mode not in {"image", "video"}:
        return None
    return PromptBlock(
        id="environment.canvas_media_operation",
        layer="system",
        content=(
            "Canvas media operation contract:\n"
            "- When the latest user request contains structured media references, treat Structured media references as authoritative tool input data.\n"
            "- For canvas_mark edits, the mark is a local target inside the referenced source image, not a standalone subject.\n"
            "- If the user asks to replace, remove, modify, restyle, extend, generate from, or analyze referenced media, complete the media operation with tools before final text.\n"
            "- For image edits, call generate_image and copy the relevant tool_reference exactly into reference_image_urls. Include the mark label and normalized position in the prompt, and preserve unrelated regions.\n"
            "- When constructing image/video prompts from referenced media, preserve the user's wording and intent. Do not add unrequested visual modifiers, colors, materials, styles, lighting, composition, or object details; if the user says to use the object in the image, refer to the object generically rather than inventing its appearance.\n"
            "- Do not claim an image or video was generated, edited, or analyzed unless the corresponding tool call has completed or returned a usable artifact_ref or result.\n"
            "- If the user asks to analyze the generated result, pass the generated artifact_ref or result to analyze_image after generation.\n"
            "- These canvas media rules override selected skill workflows, confirmation stages, and brand/design planning phases only for how the current media operation itself is carried out (which tool to call, edit vs. generate mechanics, mark/reference handling).\n"
            "- They do NOT remove the post-generation decision gate: once the media operation has completed, if your assistant text asks the user to choose among directions/options or to decide whether to enter a next stage, rule 6 still applies — you must call ask_user in the same turn instead of ending on prose alone."
        ),
    )


def build_artifact_manifest_workflow(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    artifact_mode = str(spec.artifact_mode or "").strip().lower()
    if artifact_mode in {"", "image", "video", "audio"}:
        return None
    is_zh = str(spec.language or "").lower().startswith("zh")
    # Note: the write -> register_artifact -> publish_output sequence, the
    # entry/kind requirement, and "publish_output takes no parameters" are
    # already stated once in WorkspaceContract.prompt_section, and the
    # design-system guidance lives with the injected DESIGN.md body. This block
    # only carries the increments not covered there.
    artifact_rule = _artifact_emission_rule(spec, is_zh=is_zh)
    if is_zh:
        content = (
            "Artifact manifest workflow:\n"
            "- register_artifact.entry 必须是用户最终要打开的主文件。\n"
            "- 辅助脚本、验证脚本、临时文件只能放入 supporting_files，不能登记为 spreadsheet/document/deck/html entry。\n"
            "- 只有用户明确要求交付代码时，才使用 code artifact。\n"
            f"{artifact_rule}\n"
        )
    else:
        content = (
            "Artifact manifest workflow:\n"
            "- register_artifact.entry must be the user-facing primary file.\n"
            "- Build scripts, validators, and temporary helpers belong in supporting_files and must not be registered as spreadsheet/document/deck/html entries.\n"
            "- Use code artifacts only when the user explicitly asked for code as the deliverable.\n"
            f"{artifact_rule}\n"
        )
    return PromptBlock(
        id="environment.artifact_manifest_workflow",
        layer="state",
        content=content,
    )


def build_prepared_workspace_contract(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN or spec.prepared_workspace is None:
        return None
    session = spec.prepared_workspace if isinstance(spec.prepared_workspace, dict) else getattr(spec.prepared_workspace, "to_payload", lambda: None)()
    if not isinstance(session, dict):
        return None
    root = str(session.get("artifact_work_root") or "").replace("\\", "/").strip().strip("/")
    entry_file = str(session.get("entry_file") or "").replace("\\", "/").strip().strip("/")
    if not root:
        return None
    lines = [
        "Prepared workspace:",
        f"- Current artifact work directory: project/{root}/",
        f"- Template default entry: {entry_file or 'none'}",
        "- The prepared workspace is a construction area; register_artifact defines the final deliverable identity.",
    ]
    return PromptBlock(
        id="environment.prepared_workspace",
        layer="delta",
        content="\n".join(lines),
    )


def _artifact_emission_rule(spec: TurnSpec, *, is_zh: bool) -> str:
    if _is_home_open_design_html_spec(spec):
        if is_zh:
            return (
                "- 推荐路径仍是 write_file + register_artifact + publish_output。"
                "若所选 open-design skill 明确要求 `<artifact type=\"text/html\">`，仅在本轮生成新的 canonical HTML 时可输出一个完整 artifact；"
                "artifact body 必须是完整 `<!doctype html>` 文档。编辑已有文件时不要输出 `<artifact>`，只说明修改并继续文件发布流程。"
            )
        return (
            "- The recommended path is still write_file + register_artifact + publish_output. "
            "If the selected open-design skill explicitly asks for `<artifact type=\"text/html\">`, you may emit exactly one complete artifact only when this turn creates new canonical HTML; "
            "the artifact body must be a full `<!doctype html>` document. When editing existing files, do not emit `<artifact>`; summarize the edit and continue the file publishing flow."
        )
    if is_zh:
        return (
            "- 若所选 skill 正文要求用 `<artifact>` / `</artifact>` 标签包裹 HTML，默认仍按本运行时文件发布合同执行："
            "write_file 写入文件，再用 register_artifact + publish_output 交付；非 Home HTML/canvas/media 不要输出 HTML artifact 标签。"
        )
    return (
        "- If the selected skill body asks for `<artifact>` / `</artifact>` HTML wrapping, follow this runtime's file-publish contract by default: "
        "write files, then call register_artifact + publish_output. Non-Home-HTML and canvas/media runs must not emit HTML artifact tags."
    )


def _is_home_open_design_html_spec(spec: TurnSpec) -> bool:
    protocol = None
    if spec.skill is not None:
        try:
            protocol = resolve_skill_protocol(
                spec.skill,
                ProtocolRuntimeContext(
                    artifact_mode=spec.artifact_mode,
                    project_kind=spec.artifact_mode,
                    prepared_workspace=spec.prepared_workspace,
                    workspace_runtime_session=spec.workspace_runtime_session,
                ),
            )
        except Exception:
            protocol = None
    return is_home_open_design_html_run(
        {
            "runtime_profile": (spec.conversation or {}).get("runtime_profile"),
            "artifact_mode": spec.artifact_mode,
        },
        protocol,
    )
