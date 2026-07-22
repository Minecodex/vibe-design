from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.skills.content_resolver import resolve_skill_content
from app.services.agent_harness.capabilities.skill_protocols import ProtocolRuntimeContext, resolve_skill_protocol
from app.services.agent_harness.runtime.open_design.eligibility import is_home_open_design_html_run

_SUMMARY_MAX_CHARS = 1400
_DESIGN_SUMMARY_MAX_ITEMS = 6
_DESIGN_SECTION_KEYWORDS = (
    "交互规则",
    "客户确认原则",
    "客户端确认原则",
    "生成规则",
    "设计推进原则",
    "视觉推进原则",
    "图片生成确认与依赖硬规则",
    "视觉资产继承规则",
)
_DESIGN_LINE_KEYWORDS = (
    "`ask_user`",
    "`generate_image`",
    "`generate_video`",
    "ask_user",
    "generate_image",
    "generate_video",
    "视觉资产",
    "视觉结果",
    "已确认图片",
    "上一轮结果",
    "上一张图片",
    "继承",
    "设计分支",
    "独立探索",
    "确认",
    "continue from",
    "confirmed image",
    "confirmed visual",
    "design chain",
    "visual result",
)


def _cap_text(value: Any, max_chars: int = _SUMMARY_MAX_CHARS) -> tuple[str, str | None]:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text, None
    omitted = len(text) - max_chars
    return text[:max_chars].rstrip() + f"\n[truncated {omitted} chars]", "truncated"


def _first_sentence(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    first_line = next(
        (
            re.sub(r"^[-*]\s*", "", line.strip().lstrip("#").strip())
            for line in text.splitlines()
            if line.strip() and line.strip() != "---" and line.strip().lstrip("#").strip()
        ),
        "",
    )
    return first_line[:240] if first_line else fallback


def _is_design_skill(skill: Any | None, skill_body: str | None) -> bool:
    if str(getattr(skill, "scenario", "") or "").strip().lower() == "design":
        return True
    tools = [str(tool).strip().lower() for tool in list(getattr(skill, "tools", []) or [])]
    if {"generate_image", "generate_video"} & set(tools):
        return True
    prompt = str(skill_body or "")
    return "视觉资产继承规则" in prompt or "confirmed visual" in prompt or "design chain" in prompt


def _extract_design_skill_constraints(skill_body: str | None) -> list[str]:
    text = str(skill_body or "").strip()
    if not text:
        return []

    notes: list[str] = []
    seen: set[str] = set()
    active_section: str | None = None

    def _push(section: str | None, raw_line: str) -> None:
        normalized = re.sub(r"^(\d+\.\s+|[-*]\s+)", "", raw_line.strip()).strip()
        if not normalized:
            return
        compact = normalized[:220]
        key = compact.casefold()
        if key in seen:
            return
        seen.add(key)
        if section and section not in {"生成规则", "交互规则"}:
            notes.append(f"{section}: {compact}")
        else:
            notes.append(compact)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            active_section = heading if any(keyword in heading for keyword in _DESIGN_SECTION_KEYWORDS) else None
            continue
        if active_section:
            if line.startswith(("-", "*")) or re.match(r"^\d+\.\s+", line):
                _push(active_section, line)
        elif any(keyword in line for keyword in _DESIGN_LINE_KEYWORDS) and (line.startswith(("-", "*")) or re.match(r"^\d+\.\s+", line)):
            _push(None, line)
        if len(notes) >= _DESIGN_SUMMARY_MAX_ITEMS:
            break
    return notes[:_DESIGN_SUMMARY_MAX_ITEMS]


def _render_structured_summary(title: str, fields: dict[str, Any]) -> str:
    lines = [title]
    purpose = str(fields.get("purpose") or "").strip()
    if purpose:
        lines.append(f"Purpose: {purpose}")
    constraints = [str(item).strip() for item in list(fields.get("must_follow_constraints") or []) if str(item).strip()]
    if constraints:
        lines.append("Critical constraints:")
        lines.extend(f"- {item}" for item in constraints)
    instructions = [str(item).strip() for item in list(fields.get("phase_relevant_instructions") or []) if str(item).strip()]
    if instructions:
        lines.append("Phase-relevant instructions:")
        lines.extend(f"- {item}" for item in instructions)
    allowed = [str(item).strip() for item in list(fields.get("allowed_outputs") or []) if str(item).strip()]
    if allowed:
        lines.append("Allowed outputs:")
        lines.extend(f"- {item}" for item in allowed)
    disallowed = [str(item).strip() for item in list(fields.get("disallowed_patterns") or []) if str(item).strip()]
    if disallowed:
        lines.append("Disallowed patterns:")
        lines.extend(f"- {item}" for item in disallowed)
    source_paths = [str(item).strip() for item in list(fields.get("source_paths") or []) if str(item).strip()]
    if source_paths:
        lines.append("Source paths:")
        lines.extend(f"- {item}" for item in source_paths[:6])
    return "\n".join(lines)


def _discovery_preamble(language: str) -> list[str]:
    if str(language).lower().startswith("zh"):
        return [
            "- active skill 通过只读 `skill/` 根暴露；不要把 skill 文件当作普通输出内容。",
            "- 已加载的 skill 正文优先；仅当正文明确引用 side file 且当前任务需要缺失细节时，再按需读取 `skill/`。",
            "- 如需检查 side folder，只对一个明确目录做非递归 listing。",
        ]
    return [
        '- The active skill is exposed through the read-only `skill/` root; do not treat skill files as normal output content.',
        "- Prefer the loaded skill body; read `skill/` side files only when the body explicitly references them and the task needs omitted details.",
        '- If a side folder must be inspected, list one specific folder with `recursive=False`.',
    ]


def _skill_side_file_hints(*, language: str, skill_root: Path | None, helper_files: list[str] | None = None) -> list[str]:
    if skill_root is None:
        return []
    root = Path(skill_root)
    helper_names = [str(item).strip() for item in list(helper_files or []) if str(item).strip()]

    hints: list[str] = ["Skill side-file hints:"]
    if str(language).lower().startswith("zh"):
        if "assets" in helper_names or (root / "assets").is_dir():
            hints.append("- skill/assets/: 包含模板、示例资源或种子素材。")
        if "references" in helper_names or (root / "references").is_dir():
            hints.append("- skill/references/: 包含可按需读取的知识或指导文档。")
        if "scripts" in helper_names or (root / "scripts").is_dir():
            hints.append("- skill/scripts/: 包含可按需复用的脚本。")
    else:
        if "assets" in helper_names or (root / "assets").is_dir():
            hints.append("- skill/assets/: contains templates, sample assets, or seed materials.")
        if "references" in helper_names or (root / "references").is_dir():
            hints.append("- skill/references/: contains optional knowledge or guidance documents.")
        if "scripts" in helper_names or (root / "scripts").is_dir():
            hints.append("- skill/scripts/: contains optional reusable scripts.")
    listed_helper_files = [name for name in helper_names if name not in {"assets", "references", "scripts"}]
    if listed_helper_files:
        hints.append("- Available helper files: " + ", ".join(listed_helper_files) + ".")
    return hints if len(hints) > 1 else []


def _skill_body_heading(language: str) -> str:
    if str(language).lower().startswith("zh"):
        return "Skill 文档正文:"
    return "Skill document body:"


def _runtime_profile(value: str | None) -> str:
    return str(value or "home").strip().lower() or "home"


def _is_canvas_runtime(runtime_profile: str | None) -> bool:
    return _runtime_profile(runtime_profile) == "canvas"


def _is_home_open_design_html_prompt(
    *,
    runtime_profile: str | None,
    artifact_mode: str | None,
    skill: Any | None,
    prepared_workspace: Any | None = None,
    workspace_runtime_session: dict[str, Any] | None = None,
) -> bool:
    protocol = None
    if skill is not None:
        try:
            protocol = resolve_skill_protocol(
                skill,
                ProtocolRuntimeContext(
                    artifact_mode=artifact_mode,
                    project_kind=artifact_mode,
                    prepared_workspace=prepared_workspace,
                    workspace_runtime_session=workspace_runtime_session,
                ),
            )
        except Exception:
            protocol = None
    probe = {
        "runtime_profile": runtime_profile,
        "artifact_mode": artifact_mode,
    }
    return is_home_open_design_html_run(probe, protocol)


def _normalized_summary_items(items: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    for item in list(items or []):
        text = re.sub(r"^[-*]\s*", "", str(item).strip()).strip()
        if text:
            normalized.append(text)
    return normalized


def _internal_hidden_skill_heading(language: str) -> str:
    if str(language).lower().startswith("zh"):
        return "Internal hidden skill instructions:"
    return "Internal hidden skill instructions:"


def _loaded_helper_skill_heading(language: str, skill_name: str) -> str:
    if str(language).lower().startswith("zh"):
        return f"Loaded helper skill: {skill_name}"
    return f"Loaded helper skill: {skill_name}"


class SkillSummaryProvider:
    name = "SkillSummaryProvider"

    def summarize(
        self,
        *,
        language: str,
        phase: str,
        skill: Any | None,
        skill_id: str | None,
        prompt_body: str | None,
        runtime_profile: str | None = None,
        artifact_mode: str | None = None,
        prepared_workspace: Any | None = None,
        workspace_runtime_session: dict[str, Any] | None = None,
        runtime_skill_dir: Path | None = None,
        active_skill_manifest: dict[str, Any] | None = None,
        runtime_contract: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        manifest = active_skill_manifest if isinstance(active_skill_manifest, dict) else None
        resolved_body = str(prompt_body or "").strip()
        frontmatter_status = "unresolved"
        resolved_language = str(language or "zh")
        used_runtime_root = False
        resolved_content = None
        home_open_design_html = _is_home_open_design_html_prompt(
            runtime_profile=runtime_profile,
            artifact_mode=artifact_mode,
            skill=skill,
            prepared_workspace=prepared_workspace,
            workspace_runtime_session=workspace_runtime_session,
        )
        should_resolve_skill_content = skill is not None and (
            manifest is None or not resolved_body or _is_canvas_runtime(runtime_profile) or home_open_design_html
        )
        if should_resolve_skill_content:
            if skill is not None:
                try:
                    resolved_content = resolve_skill_content(
                        skill,
                        language=language,
                        runtime_skill_dir=runtime_skill_dir,
                    )
                except Exception:
                    resolved_content = None
        if manifest is None:
            resolved_body = str(getattr(resolved_content, "body", "") or prompt_body or "").strip()
            frontmatter_status = str(getattr(resolved_content, "frontmatter_status", "unresolved") or "unresolved")
            resolved_language = str(getattr(resolved_content, "resolved_language", language) or language)
            used_runtime_root = bool(getattr(resolved_content, "used_runtime_root", False))
        elif isinstance(manifest, dict):
            resolved_body = str(getattr(resolved_content, "body", "") or resolved_body or "").strip()
            if resolved_content is not None:
                frontmatter_status = str(getattr(resolved_content, "frontmatter_status", "unresolved") or "unresolved")
                resolved_language = str(getattr(resolved_content, "resolved_language", language) or language)
            primary_entry = next(
                (
                    item
                    for item in list(manifest.get("skills") or [])
                    if isinstance(item, dict) and str(item.get("activation_role") or "") == "selected_skill"
                ),
                {},
            )
            used_runtime_root = bool(primary_entry.get("used_runtime_root"))
        summary_fields = self._summary_fields_from_manifest(
            language=language,
            manifest=manifest,
            skill=skill,
            prompt_body=resolved_body or prompt_body,
        )
        if (_is_canvas_runtime(runtime_profile) or home_open_design_html) and resolved_body:
            content = self._render_full_skill_body(
                language=language,
                resolved_body=resolved_body,
                summary_fields=summary_fields,
            )
            injection_mode = "full_skill_body"
        else:
            content = _render_structured_summary("Active skill instructions:", summary_fields)
            injection_mode = "manifest"
        record_as_long_doc_summary = False
        internal_sections = self._render_internal_hidden_skill_sections(
            language=language,
            phase=str(phase or "").strip().lower(),
            runtime_contract=runtime_contract,
            manifest=manifest,
        )
        if internal_sections:
            content = "\n\n".join([content, *internal_sections])
        return content, {
            "provider": self.name,
            "injection_mode": injection_mode,
            "resolved_language": resolved_language,
            "used_runtime_root": used_runtime_root,
            "skill_body_chars": len(resolved_body),
            "frontmatter_status": frontmatter_status,
            "record_as_long_doc_summary": record_as_long_doc_summary,
            "summary_fields": summary_fields,
        }

    def _render_full_skill_body(
        self,
        *,
        language: str,
        resolved_body: str,
        summary_fields: dict[str, Any],
    ) -> str:
        lines = ["Active skill instructions:"]
        purpose = str(summary_fields.get("purpose") or "").strip()
        if purpose:
            lines.append(f"Purpose: {purpose}")
        access_notes = _normalized_summary_items(summary_fields.get("phase_relevant_instructions"))
        if access_notes:
            lines.append("Skill access notes:")
            lines.extend(f"- {item}" for item in access_notes[:3])
        lines.extend([_skill_body_heading(language), resolved_body])
        return "\n".join(lines)

    def _summary_fields_from_manifest(
        self,
        *,
        language: str,
        manifest: dict[str, Any] | None,
        skill: Any | None,
        prompt_body: str | None,
    ) -> dict[str, Any]:
        skills = list((manifest or {}).get("skills") or [])
        primary = next(
            (
                item
                for item in skills
                if isinstance(item, dict) and str(item.get("activation_role") or "") == "selected_skill"
            ),
            skills[0] if skills else {},
        )
        available_side_files = [
            str(item).strip()
            for item in list((primary.get("available_side_files") if isinstance(primary, dict) else []) or [])[:6]
            if str(item).strip()
        ]
        phase_instructions = list(_discovery_preamble(language))
        if available_side_files:
            phase_instructions.append(
                "Side files are optional; read only the specific file needed for omitted details."
                if not str(language).lower().startswith("zh")
                else "Side files 是可选资源；只在需要缺失细节时读取具体文件。"
            )
        purpose = _first_sentence(
            primary.get("purpose") if isinstance(primary, dict) else prompt_body,
            fallback=str(getattr(skill, "description_en", None) or getattr(skill, "description", None) or getattr(skill, "name_en", None) or getattr(skill, "name", None) or "Use the active skill guidance."),
        )
        constraints = [
            str(item).strip()
            for item in list((primary.get("must_follow_constraints") if isinstance(primary, dict) else []) or [])[:8]
            if str(item).strip()
        ]
        constraints = [*list(_discovery_preamble(language)), *constraints]
        if _is_design_skill(skill, str(prompt_body or "")):
            constraints.extend(_extract_design_skill_constraints(prompt_body))
        source_paths = ["skill"]
        return {
            "purpose": purpose,
            "must_follow_constraints": constraints,
            "phase_relevant_instructions": phase_instructions,
            "allowed_outputs": [
                "Use skill files as guidance, templates, and inputs while keeping final deliverables in the workspace contract.",
            ],
            "disallowed_patterns": [
                "Do not recursively crawl the entire skill tree just to understand the skill.",
                "Do not treat skill-local files as the final published output path.",
            ],
            "source_paths": source_paths[:6],
        }

    def _render_internal_hidden_skill_sections(
        self,
        *,
        language: str,
        phase: str,
        runtime_contract: dict[str, Any] | None,
        manifest: dict[str, Any] | None = None,
    ) -> list[str]:
        manifest_hidden = [
            item
            for item in list((manifest or {}).get("skills") or [])
            if isinstance(item, dict) and str(item.get("activation_role") or "") == "internal_helper"
        ]
        hidden_skills = manifest_hidden or list((runtime_contract or {}).get("internal_hidden_skills") or [])
        sections: list[str] = []
        rendered_helpers: list[str] = []
        for item in hidden_skills:
            if not isinstance(item, dict):
                continue
            helper_skill = get_skill(item.get("id"))
            helper_name = str(
                item.get("name")
                or getattr(helper_skill, "name_en", None)
                or getattr(helper_skill, "name", None)
                or item.get("id")
                or ""
            ).strip()
            helper_fields = {
                "purpose": _first_sentence(
                    item.get("purpose"),
                    fallback=str(getattr(helper_skill, "description_en", None) or getattr(helper_skill, "description", None) or helper_name),
                ),
                "must_follow_constraints": [
                    "This helper skill is loaded internally and does not replace the visible selected skill.",
                ],
                "phase_relevant_instructions": [
                    "Use helper side files only when the current task needs that extra specialization.",
                ],
                "allowed_outputs": [
                    "Use this helper skill as internal guidance while keeping the visible selected skill unchanged.",
                ],
                "disallowed_patterns": [
                    "Do not present this helper skill as the user-selected skill in Home.",
                ],
                "source_paths": list(item.get("available_side_files") or [])[:4],
            }
            helper_section = _render_structured_summary(
                _loaded_helper_skill_heading(language, helper_name),
                helper_fields,
            )
            rendered_helpers.append(helper_section)
        if rendered_helpers:
            sections.append("\n".join([_internal_hidden_skill_heading(language), *rendered_helpers]))
        return sections


class ProtocolSummaryProvider:
    name = "ProtocolSummaryProvider"

    def summarize(self, *, language: str, skill: Any | None, artifact_mode: str | None, prepared_workspace: Any | None, workspace_runtime_session: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
        if skill is None:
            return "", {"provider": self.name}
        from app.services.agent_harness.capabilities.skill_protocols import (
            ProtocolRuntimeContext,
            resolve_skill_protocol,
        )

        protocol = resolve_skill_protocol(
            skill,
            ProtocolRuntimeContext(
                artifact_mode=artifact_mode,
                project_kind=artifact_mode,
                prepared_workspace=prepared_workspace,
                workspace_runtime_session=workspace_runtime_session,
            ),
        )
        contract = protocol.execution_contract
        summary_fields = {
            "purpose": f"Follow the active skill protocol for provider={protocol.provider}, family={protocol.family}.",
            "must_follow_constraints": [
                f"provider: {protocol.provider}",
                f"family: {protocol.family}",
            ],
            "phase_relevant_instructions": [],
            "allowed_outputs": ["Generate outputs that satisfy the selected skill protocol and artifact mode."],
            "disallowed_patterns": ["Do not create a parallel main entry when the protocol requires continuing from a prepared seed or shell."],
            "source_paths": [],
        }
        if contract.requires_media_contract:
            summary_fields["must_follow_constraints"].append(
                "- 这是 Open-Design media skill：走媒体生成协议，不要用 HTML artifact 代替媒体结果。"
                if str(language).lower().startswith("zh")
                else "- This is an Open-Design media skill: use the media generation contract instead of an HTML artifact."
            )
        for note in list(contract.prompt_notes or [])[:4]:
            summary_fields["phase_relevant_instructions"].append(_normalize_skill_local_text(str(note)[:200]))
        return _render_structured_summary("Skill protocol contract:", summary_fields), {
            "provider": self.name,
            "summary_fields": summary_fields,
        }


def _model_visible_skill_path(path: str | None) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    if normalized.startswith(("skill/", "project/", "published/")):
        return normalized
    if normalized.startswith(("assets/", "references/", "scripts/")):
        return f"skill/{normalized}"
    return normalized


def _normalize_skill_local_text(text: str | None) -> str:
    normalized = str(text or "")
    for legacy_path in ("assets/template.html", "references/checklist.md", "references/layouts.md"):
        normalized = normalized.replace(legacy_path, _model_visible_skill_path(legacy_path))
    return normalized
