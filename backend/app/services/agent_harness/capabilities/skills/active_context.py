from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skill_protocols.open_design.design_templates import (
    normalize_template_body_for_workspace,
)
from app.services.agent_harness.capabilities.skill_protocols.open_design.parser import (
    PREFLIGHT_PATHS,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    read_runtime_state_payload,
    update_conversation_record,
)

from .content_resolver import resolve_skill_content

SELECTED_SKILL_CONTEXT_BUILDER_VERSION = 2

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#][^)]+)\)")
_HELPER_PREFIXES = ("references/", "scripts/", "assets/")

def build_selected_skill_active_context(
    skill: Any,
    *,
    language: str,
    runtime_skill_dir: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_skill_content(
        skill,
        language=language,
        runtime_skill_dir=runtime_skill_dir,
    )
    source_body = str(resolved.body or "").strip()
    template_capabilities = _template_capabilities(skill)
    if template_capabilities:
        source_body = normalize_template_body_for_workspace(source_body)
    requested_language = str(language or "zh").strip().lower() or "zh"
    preflight_paths = _derive_preflight_paths(source_body)
    on_demand_paths = _on_demand_paths(resolved.helper_files, source_body)
    skill_root_preamble = _build_skill_root_preamble(on_demand_paths, requested_language)
    preflight_note = _build_preflight_note(preflight_paths, requested_language)
    body_parts = [part for part in [skill_root_preamble, source_body, preflight_note] if part]
    runtime_body = "\n\n".join(body_parts)
    truncation_mode = "full"
    omission_kinds: list[str] = []
    source_language = str(resolved.resolved_language or requested_language or "zh")
    source_path = "SKILL.en.md" if source_language == "en" and _has_english_skill(resolved.source_root) else "SKILL.md"
    loaded_path = f"skill/{source_path}"
    artifact = {
        "version": 1,
        "kind": "selected_skill_active_context",
        "skill_id": str(getattr(skill, "id", "") or "").strip() or None,
        "language": requested_language,
        "source_language": source_language,
        "source_path": source_path,
        "source_body": source_body,
        "runtime_body": runtime_body,
        "source_digest": _digest(source_body),
        "truncation_mode": truncation_mode,
        "omission_kinds": omission_kinds,
        "builder_version": SELECTED_SKILL_CONTEXT_BUILDER_VERSION,
        "loaded_paths": [loaded_path],
        "on_demand_paths": on_demand_paths,
        "preflight_paths": preflight_paths,
        "link_targets": _link_targets(source_body),
        "used_runtime_root": bool(resolved.used_runtime_root),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if template_capabilities:
        artifact.update(
            {
                "template_relation": dict(template_capabilities.get("template_relation") or {}),
                "template_preflight": dict(template_capabilities.get("template_preflight") or {}),
                "template_support_state": template_capabilities.get("template_support_state"),
                "template_deferred_reason": template_capabilities.get("template_deferred_reason"),
            }
        )
    return artifact


def persist_selected_skill_active_context(
    user_id: int,
    conversation_id: str,
    skill: Any,
    *,
    language: str,
    runtime_skill_dir: Path | None = None,
) -> dict[str, Any]:
    artifact = build_selected_skill_active_context(
        skill,
        language=language,
        runtime_skill_dir=runtime_skill_dir,
    )
    conversation = read_runtime_state_payload(user_id, conversation_id) or {}
    runtime_state = (
        dict(conversation.get("runtime_state") or {})
        if isinstance(conversation.get("runtime_state"), dict)
        else {}
    )
    runtime_contract = (
        dict(runtime_state.get("runtime_contract") or {})
        if isinstance(runtime_state.get("runtime_contract"), dict)
        else {}
    )
    runtime_contract["active_skill_context"] = artifact
    runtime_state["runtime_contract"] = runtime_contract
    update_conversation_record(user_id, conversation_id, {"runtime_state": runtime_state})
    return artifact


def clear_selected_skill_active_context(user_id: int, conversation_id: str) -> None:
    conversation = read_runtime_state_payload(user_id, conversation_id) or {}
    runtime_state = (
        dict(conversation.get("runtime_state") or {})
        if isinstance(conversation.get("runtime_state"), dict)
        else {}
    )
    runtime_contract = (
        dict(runtime_state.get("runtime_contract") or {})
        if isinstance(runtime_state.get("runtime_contract"), dict)
        else {}
    )
    runtime_contract.pop("active_skill_context", None)
    runtime_state["runtime_contract"] = runtime_contract if runtime_contract else None
    update_conversation_record(user_id, conversation_id, {"runtime_state": runtime_state})


def is_active_skill_context_current(
    artifact: dict[str, Any] | None,
    *,
    skill_id: str | None,
    language: str | None,
    source_digest: str | None,
    builder_version: int = SELECTED_SKILL_CONTEXT_BUILDER_VERSION,
) -> bool:
    if not isinstance(artifact, dict):
        return False
    return (
        str(artifact.get("skill_id") or "") == str(skill_id or "")
        and str(artifact.get("language") or "").lower().startswith(str(language or "").lower()[:2])
        and str(artifact.get("source_digest") or "") == str(source_digest or "")
        and int(artifact.get("builder_version") or 0) == int(builder_version)
    )


def _derive_preflight_paths(source_body: str) -> list[str]:
    body = str(source_body or "")
    paths: list[str] = []
    for ref in PREFLIGHT_PATHS:
        if ref in body:
            paths.append(ref)
    return _dedupe(paths)


def _build_preflight_note(paths: list[str], language: str) -> str:
    if not paths:
        return ""
    is_zh = str(language or "").lower().startswith("zh")
    file_list = "、".join(f"`{p}`" for p in paths) if is_zh else ", ".join(f"`{p}`" for p in paths)
    if is_zh:
        return (
            "**Pre-flight（开始构建前）：** 先通过 `read_file(base=\"skill\", path=\"<relative-path>\")` 读取 "
            f"{file_list}。模板文件定义了可复用的 class 体系与版面骨架；"
            "checklist 是 P0/P1/P2 自检纪律，不是单独的后端 checklist 工具。"
        )
    return (
        "**Pre-flight (before building):** Use `read_file(base=\"skill\", path=\"<relative-path>\")` to read "
        f"{file_list} first. Templates define reusable classes and layout skeletons; "
        "checklists are P0/P1/P2 self-check discipline, not a separate backend checklist tool."
    )


def _build_skill_root_preamble(on_demand_paths: list[str], language: str) -> str:
    relative_paths = [
        path.removeprefix("skill/").strip("/")
        for path in _dedupe(on_demand_paths)
        if str(path or "").startswith("skill/")
    ]
    if not relative_paths:
        return ""
    shown = ", ".join(f"`{path}`" for path in relative_paths[:12])
    if str(language or "").lower().startswith("zh"):
        return (
            "Skill root: `skill/`\n"
            "Read side files using `read_file(base=\"skill\", path=\"<relative-path>\")`.\n"
            f"Known side files: {shown}."
        )
    return (
        "Skill root: `skill/`\n"
        "Read side files using `read_file(base=\"skill\", path=\"<relative-path>\")`.\n"
        f"Known side files: {shown}."
    )


def _digest(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _has_english_skill(root: Path | None) -> bool:
    try:
        return bool(root and (Path(root) / "SKILL.en.md").is_file())
    except Exception:
        return False


def _on_demand_paths(helper_files: list[str] | None, source_body: str) -> list[str]:
    paths: list[str] = []
    for item in list(helper_files or []):
        normalized = str(item or "").replace("\\", "/").strip().strip("/")
        if normalized:
            paths.append(f"skill/{normalized}")
    paths.extend(_link_targets(source_body))
    return _dedupe(paths)


def _link_targets(source_body: str) -> list[str]:
    targets: list[str] = []
    for match in _MARKDOWN_LINK_RE.finditer(str(source_body or "")):
        raw = match.group(1).split("#", 1)[0].strip()
        if not raw or raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        normalized = raw.replace("\\", "/").lstrip("./").strip("/")
        if normalized.startswith(_HELPER_PREFIXES) or normalized in {"example.html", "inputs.example.json", "schema.ts"}:
            targets.append(f"skill/{normalized}")
    return _dedupe(targets)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _template_capabilities(skill: Any) -> dict[str, Any]:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if not isinstance(capabilities, dict) or not capabilities.get("imported_design_template"):
        return {}
    return capabilities

