from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.design_systems import get_design_system
from app.services.agent_harness.capabilities.design_systems.active_context import (
    build_active_design_system_context,
)
from app.services.agent_harness.capabilities.skill_protocols import (
    RuntimePrepareRequest,
    prepare_skill_runtime,
)
from app.services.agent_harness.capabilities.skill_protocols.base import RuntimeExecutionContract
from app.services.agent_harness.capabilities.skill_protocols.open_design.design_templates import (
    normalize_template_body_for_workspace,
)
from app.services.agent_harness.capabilities.skills.active_context import (
    build_selected_skill_active_context,
)
from app.services.agent_harness.workspace.skill_staging_v2 import stage_active_skill_v2


@dataclass(slots=True)
class StagedSkillDescriptor:
    ok: bool
    staged_root: str = "skill"
    source_path: str | None = None
    target_path: str | None = None
    linked_dependencies: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "staged_root": self.staged_root,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "linked_dependencies": list(self.linked_dependencies),
            "reason": self.reason,
        }


@dataclass(slots=True)
class ActiveSkillRuntimeResult:
    staged_skill: StagedSkillDescriptor
    active_skill_context: dict[str, Any]
    normalized_execution_body: str
    dependency_manifest: dict[str, Any]
    prepared_workspace: dict[str, Any] | None
    prepared_runtime_result: Any | None
    runtime_contract_patch: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PathDialectNormalization:
    body: str
    warnings: list[str] = field(default_factory=list)


class ActiveSkillRuntime:
    """Prepare one selected skill for Harness Runtime Protocol v2 execution."""

    def prepare(
        self,
        *,
        ctx: Any,
        skill: Any,
        conversation: dict[str, Any],
        latest_user_request: str,
    ) -> ActiveSkillRuntimeResult:
        staged_skill = self._stage(ctx=ctx, skill=skill)
        runtime_root = Path(getattr(ctx, "active_skill_dir", None) or getattr(ctx, "skill_dir")).resolve()
        _ensure_runtime_skill_markdown(runtime_root, skill)
        active_context = build_selected_skill_active_context(
            skill,
            language=str(getattr(ctx, "language", "zh") or "zh"),
            runtime_skill_dir=runtime_root,
        )
        prepared = prepare_skill_runtime(
            skill,
            RuntimePrepareRequest(
                skill=skill,
                conversation=conversation,
                latest_user_request=latest_user_request,
                work_dir=Path(getattr(ctx, "work_dir")).resolve(),
                active_skill_dir=runtime_root,
                artifact_mode=getattr(ctx, "artifact_mode", None),
                workspace_runtime_session=getattr(ctx, "workspace_runtime_session", None),
            ),
        )
        prepared_workspace = dict(prepared.prepared_workspace) if prepared is not None else None
        runtime_contract_payload = self._runtime_execution_contract_payload(prepared)
        active_design_system_id = (
            str(getattr(ctx, "design_system_id", "") or "").strip()
            or str(conversation.get("design_system_id") or "").strip()
            or None
        )
        active_design_system_context = _build_active_design_system_context(active_design_system_id)
        body_normalization = normalize_open_design_execution_body_with_warnings(
            str(active_context.get("runtime_body") or active_context.get("source_body") or ""),
            active_design_system_id=active_design_system_id,
        )
        normalized_body = body_normalization.body
        active_context = dict(active_context)
        active_context["runtime_body"] = normalized_body
        active_context["truncation_mode"] = "full" if active_context.get("truncation_mode") == "full" else active_context.get("truncation_mode")

        dependency_manifest = build_dependency_manifest(runtime_root, staged_skill=staged_skill)
        dependency_manifest["warnings"] = _dedupe([*list(dependency_manifest.get("warnings") or []), *body_normalization.warnings])
        rollout = _rollout_decision(skill)
        runtime_contract_patch: dict[str, Any] = {
            "active_skill_context": active_context,
            "skill_dependency_manifest": dependency_manifest,
            "active_skill_runtime": {
                "selected_skill_id": str(getattr(skill, "id", "") or ""),
                "staged_root": "skill",
                "prompt_body_mode": active_context.get("truncation_mode"),
                "dependency_count": len(dependency_manifest.get("side_files") or []),
                "rollout_state": rollout["state"],
                "rollout_reason": rollout.get("reason"),
            },
        }
        if active_design_system_id:
            runtime_contract_patch["design_system_id"] = active_design_system_id
        if prepared is not None:
            runtime_contract_patch.update(prepared.runtime_contract_patch)
            runtime_contract_patch["runtime_execution_contract"] = runtime_contract_payload
        elif runtime_contract_payload:
            runtime_contract_patch["runtime_execution_contract"] = runtime_contract_payload
        if active_design_system_context is not None:
            runtime_contract_patch["active_design_system_context"] = active_design_system_context

        trace = {
            "selected_skill_id": str(getattr(skill, "id", "") or ""),
            "staged_root": "skill",
            "linked_dependencies": list(staged_skill.linked_dependencies),
            "side_file_count": len(dependency_manifest.get("side_files") or []),
            "prepared_family": prepared.family if prepared is not None else None,
            "active_entry": runtime_contract_payload.get("active_entry"),
            "prompt_body_mode": active_context.get("truncation_mode"),
            "rollout_state": rollout["state"],
            "rollout_reason": rollout.get("reason"),
            "active_design_system_id": active_design_system_id,
            "active_design_system_context": bool(active_design_system_context),
        }
        runtime_contract_patch["active_skill_runtime_trace"] = dict(trace)

        return ActiveSkillRuntimeResult(
            staged_skill=staged_skill,
            active_skill_context=active_context,
            normalized_execution_body=normalized_body,
            dependency_manifest=dependency_manifest,
            prepared_workspace=prepared_workspace,
            prepared_runtime_result=prepared,
            runtime_contract_patch=runtime_contract_patch,
            events=list(prepared.events) if prepared is not None else [],
            trace=trace,
        )

    def _stage(self, *, ctx: Any, skill: Any) -> StagedSkillDescriptor:
        source_skill_dir = getattr(skill, "skill_dir", None)
        skill_id = str(getattr(skill, "id", "") or "").strip()
        if not source_skill_dir or not skill_id:
            raise ValueError("Active skill must provide both id and skill_dir")
        result = stage_active_skill_v2(
            ctx,
            Path(source_skill_dir).resolve(),
            linked_master_ids=_declared_linked_master_ids(skill),
        )
        if not result.get("ok"):
            reason = str(result.get("reason") or result.get("error") or "failed to stage active skill")
            raise RuntimeError(reason)
        runtime_root = Path(getattr(ctx, "skill_dir")).resolve()
        ctx.active_skill_dir = runtime_root
        ctx.skill_runtime_dir = runtime_root
        return StagedSkillDescriptor(
            ok=True,
            staged_root="skill",
            source_path=str(result.get("source") or ""),
            target_path=str(result.get("target") or ""),
            linked_dependencies=sorted(
                str(item).strip() for item in list(result.get("linked_templates") or []) if str(item).strip()
            ),
        )

    @staticmethod
    def _runtime_execution_contract_payload(prepared: Any | None) -> dict[str, Any]:
        if prepared is not None:
            contract = prepared.runtime_contract_patch.get("runtime_execution_contract")
            if isinstance(contract, dict):
                return dict(contract)
            session = dict(prepared.prepared_workspace or {})
            active_entry = str(session.get("entry_path") or prepared.active_entry or "").replace("\\", "/").strip("/")
            artifact_work_root = str(session.get("artifact_work_root") or "").replace("\\", "/").strip("/")
            if active_entry and artifact_work_root:
                return RuntimeExecutionContract(
                    active_entry=active_entry,
                    artifact_work_root=artifact_work_root,
                    writable_roots=[artifact_work_root],
                    readonly_roots=["references", "skill", "published"],
                    validation_profile=prepared.family,
                ).to_payload()
        return {}


def normalize_open_design_execution_body(body: str, *, active_entry: str | None = None) -> str:
    del active_entry
    return normalize_open_design_execution_body_with_warnings(body).body


def normalize_open_design_execution_body_with_warnings(
    body: str,
    *,
    active_design_system_id: str | None = None,
) -> PathDialectNormalization:
    warnings: list[str] = []
    text = normalize_template_body_for_workspace(body)
    text = _rewrite_skill_local_paths(text)
    text = _rewrite_design_document(text, active_design_system_id=active_design_system_id, warnings=warnings)
    text = text.replace("<SKILL_ROOT>", "skill")
    return PathDialectNormalization(body=text, warnings=_dedupe(warnings))


def build_dependency_manifest(skill_root: Path, *, staged_skill: StagedSkillDescriptor) -> dict[str, Any]:
    root = Path(skill_root)
    side_files: list[str] = []
    linked: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel == "SKILL.md" or rel == "SKILL.en.md":
                continue
            model_path = f"skill/{rel}"
            if rel.startswith("_linked/"):
                parts = rel.split("/")
                if len(parts) >= 3 and parts[-1] in {"SKILL.md", "SKILL.en.md"}:
                    linked.append(
                        {
                            "id": parts[1],
                            "path": model_path,
                            "role": "linked_master",
                            "source_identity": parts[1],
                            "read_policy": "readonly",
                            "write_policy": "project_only",
                        }
                    )
                continue
            side_files.append(model_path)
    return {
        "staged_root": staged_skill.staged_root,
        "source_name": Path(staged_skill.source_path or "").name if staged_skill.source_path else None,
        "staged_path": staged_skill.staged_root,
        "side_files": side_files,
        "linked_dependencies": linked,
        "warnings": [],
        "read_policy": "readonly",
        "write_policy": "project_only",
    }


def _rewrite_skill_local_paths(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group(1).replace("\\", "/").strip("/")
        return path if path.startswith("skill/") else f"skill/{path}"

    return re.sub(
        r"(?<![\w/.-])((?:assets|references|scripts|templates)/[A-Za-z0-9_./-]+)",
        replace,
        text,
    )


def _rewrite_design_document(
    text: str,
    *,
    active_design_system_id: str | None,
    warnings: list[str],
) -> str:
    if "DESIGN.md" not in text:
        return text
    replacement = f"design_system:{active_design_system_id}" if active_design_system_id else "references/DESIGN.md"
    if not active_design_system_id:
        warnings.append("ambiguous_design_document")
    return re.sub(r"(?<![\w/.-])DESIGN\.md(?![\w/-])", replacement, text)


def _rollout_decision(skill: Any) -> dict[str, str | None]:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if isinstance(capabilities, dict):
        support_state = str(capabilities.get("template_support_state") or "").strip()
        if support_state:
            reason = str(capabilities.get("template_deferred_reason") or "").strip() or None
            return {"state": support_state, "reason": reason}
    mode = str(getattr(skill, "mode", "") or "").strip().lower()
    if mode in {"image", "video", "audio"}:
        return {"state": "deferred", "reason": f"unsupported_media_mode:{mode}"}
    return {"state": "supported", "reason": None}


def _declared_linked_master_ids(skill: Any) -> list[str]:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if not isinstance(capabilities, dict):
        return []
    relation = capabilities.get("template_relation")
    if not isinstance(relation, dict):
        return []
    values: list[str] = []
    primary = str(relation.get("primary_master_id") or "").strip()
    if primary:
        values.append(primary)
    refs = relation.get("references")
    if isinstance(refs, list):
        values.extend(str(item).strip() for item in refs if str(item).strip())
    return _dedupe(values)


def _ensure_runtime_skill_markdown(runtime_root: Path, skill: Any) -> None:
    skill_path = Path(runtime_root) / "SKILL.md"
    if skill_path.is_file():
        return
    body = str(getattr(skill, "system_prompt", "") or getattr(skill, "description", "") or "").strip()
    if not body:
        body = f"Run the selected skill `{getattr(skill, 'id', 'skill')}`."
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(body, encoding="utf-8")


def _build_active_design_system_context(design_system_id: str | None) -> dict[str, Any] | None:
    design_system = get_design_system(design_system_id)
    if design_system is None:
        return None
    return build_active_design_system_context(design_system)


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
