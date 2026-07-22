from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import (
    ExecutionContract,
    ProtocolRuntimeContext,
    PublishProfile,
    RuntimeExecutionContract,
    RuntimePrepareRequest,
    RuntimePrepareResult,
    SkillProtocol,
    ValidationProfile,
    WritePolicy,
)
from .materializer import (
    materialize_open_design_prepared_workspace,
    materialize_seed_assets,
)
from .parser import MEDIA_MODES, parse_open_design_facts


class OpenDesignProtocolAdapter:
    provider = "open_design"

    def can_handle(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> bool:
        if skill is None:
            return False
        mode = str(getattr(skill, "mode", "") or "").strip().lower()
        return mode not in {"document", "spreadsheet"}

    def resolve(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> SkillProtocol:
        facts = parse_open_design_facts(skill)
        family = _resolve_family(skill, runtime_context, facts)
        entry_paths = _runtime_entry_paths(runtime_context)

        if family == "harness_full_deck_runtime":
            runtime_contract = _runtime_execution_contract(runtime_context, family)
            return SkillProtocol(
                provider=self.provider,
                family=family,
                mode=facts.mode,
                surface=facts.surface,
                execution_contract=ExecutionContract(
                    kind=family,
                ),
                write_policy=WritePolicy(kind=family, protected_entry_paths=entry_paths, hard_block=False),
                validation_profile=ValidationProfile(kind=family, hard_block=False),
                runtime_execution_contract=runtime_contract,
                metadata={"preflight_paths": facts.preflight_paths, "side_files": facts.side_files},
            )

        if family == "open_design_generic_deck":
            runtime_contract = _runtime_execution_contract(runtime_context, family)
            return SkillProtocol(
                provider=self.provider,
                family=family,
                mode=facts.mode,
                surface=facts.surface,
                execution_contract=ExecutionContract(
                    kind=family,
                ),
                write_policy=WritePolicy(kind=family, protected_entry_paths=entry_paths, hard_block=False),
                validation_profile=ValidationProfile(kind=family, hard_block=False),
                runtime_execution_contract=runtime_contract,
                metadata={"preflight_paths": facts.preflight_paths, "side_files": facts.side_files},
            )

        if family == "open_design_seed_template":
            runtime_contract = _runtime_execution_contract(runtime_context, family)
            return SkillProtocol(
                provider=self.provider,
                family=family,
                mode=facts.mode,
                surface=facts.surface,
                execution_contract=ExecutionContract(
                    kind=family,
                    preflight_paths=facts.preflight_paths,
                ),
                write_policy=WritePolicy(
                    kind=family,
                    protected_entry_paths=entry_paths,
                    hard_block=False,
                ),
                validation_profile=ValidationProfile(
                    kind=family,
                    side_files=facts.side_files,
                    hard_block=False,
                ),
                runtime_execution_contract=runtime_contract,
                metadata={"preflight_paths": facts.preflight_paths, "side_files": facts.side_files},
            )

        if family == "open_design_media":
            return SkillProtocol(
                provider=self.provider,
                family=family,
                mode=facts.mode,
                surface=facts.surface,
                execution_contract=ExecutionContract(kind=family, requires_media_contract=True),
                publish_profile=PublishProfile(kind="media", skip_html_validation=True),
                validation_profile=ValidationProfile(kind=family),
                metadata={"preflight_paths": facts.preflight_paths, "side_files": facts.side_files},
            )

        return SkillProtocol(
            provider=self.provider,
            family=family,
            mode=facts.mode,
            surface=facts.surface,
            execution_contract=ExecutionContract(kind=family, preflight_paths=facts.preflight_paths),
            validation_profile=ValidationProfile(kind="html_dependency"),
            metadata={"preflight_paths": facts.preflight_paths, "side_files": facts.side_files},
        )

    def prepare_runtime(self, request: RuntimePrepareRequest) -> RuntimePrepareResult | None:
        skill_root = request.active_skill_dir
        if skill_root is None:
            return None
        context = ProtocolRuntimeContext(
            artifact_mode=request.artifact_mode,
            project_kind=request.artifact_mode,
            workspace_runtime_session=request.workspace_runtime_session,
            work_dir=request.work_dir,
        )
        protocol = self.resolve(request.skill, context)
        candidate_name = f"{getattr(request.skill, 'id', 'skill')}-prepared"

        if protocol.family != "open_design_media":
            return _prepare_result(
                materialize_open_design_prepared_workspace(
                    skill_root=Path(skill_root).resolve(),
                    work_dir=request.work_dir.resolve(),
                    candidate_name=candidate_name,
                    family=protocol.family,
                    strategy=str(getattr(request.skill, "execution_strategy", "") or protocol.family),
                    skill_id=str(getattr(request.skill, "id", "") or ""),
                    entry_file=getattr(request.skill, "preview_entry", None) or getattr(request.skill, "primary_output", None) or "index.html",
                )
            )

        seed_assets = list(getattr(request.skill, "seed_assets", []) or [])
        if seed_assets:
            prepared = materialize_seed_assets(
                skill_root=Path(skill_root).resolve(),
                work_dir=request.work_dir.resolve(),
                candidate_name=candidate_name,
                seed_assets=seed_assets,
                entry_file=getattr(request.skill, "preview_entry", None) or getattr(request.skill, "primary_output", None),
            )
            return _prepare_result(prepared) if prepared is not None else None
        return None


def _resolve_family(skill: Any, runtime_context: ProtocolRuntimeContext, facts) -> str:
    if _is_full_deck_runtime(skill, runtime_context):
        return "harness_full_deck_runtime"
    project_kind = str(runtime_context.project_kind or runtime_context.artifact_mode or "").strip().lower()
    if facts.mode in MEDIA_MODES or facts.surface in MEDIA_MODES or project_kind in MEDIA_MODES:
        return "open_design_media"
    if facts.has_seed_template:
        return "open_design_seed_template"
    if facts.mode == "deck" or project_kind in {"deck", "slides"}:
        return "open_design_generic_deck"
    if facts.mode == "template":
        return "open_design_template_reference"
    return "open_design_free_web"


def _is_full_deck_runtime(skill: Any, runtime_context: ProtocolRuntimeContext) -> bool:
    session = runtime_context.prepared_workspace
    if session is None:
        capabilities = getattr(skill, "runtime_capabilities", None)
        has_full_decks = bool(capabilities.get("has_full_decks")) if isinstance(capabilities, dict) else False
        skill_dir = getattr(skill, "skill_dir", None)
        has_runtime_asset = bool(skill_dir and (Path(skill_dir) / "assets" / "runtime.js").is_file())
        return str(getattr(skill, "execution_strategy", "") or "") == "template_driven_deck" and has_full_decks and has_runtime_asset
    strategy = str(_session_value(session, "strategy") or "").strip()
    source_root = str(_session_value(session, "source_root") or "").replace("\\", "/").strip("/")
    if strategy != "template_driven_deck" or not source_root.startswith("templates/full-decks/"):
        return False
    if runtime_context.work_dir is None:
        return True
    artifact_work_root = str(_session_value(session, "artifact_work_root") or "").strip().strip("/\\")
    return (Path(runtime_context.work_dir) / artifact_work_root / "assets" / "runtime.js").is_file()


def _runtime_entry_paths(runtime_context: ProtocolRuntimeContext) -> list[str]:
    paths: list[str] = []
    session = runtime_context.prepared_workspace
    if session is not None:
        entry_path = str(_session_value(session, "entry_path") or "").replace("\\", "/").strip().lstrip("/")
        if entry_path:
            paths.append(entry_path)
    workspace_session = runtime_context.workspace_runtime_session
    if isinstance(workspace_session, dict):
        active_entry = str(workspace_session.get("active_entry") or "").replace("\\", "/").strip().lstrip("/")
        if active_entry and active_entry not in paths:
            paths.append(active_entry)
    return paths


def _runtime_execution_contract(runtime_context: ProtocolRuntimeContext, family: str) -> RuntimeExecutionContract | None:
    paths = _runtime_entry_paths(runtime_context)
    active_entry = paths[0] if paths else ""
    session = runtime_context.prepared_workspace
    artifact_work_root = str(_session_value(session, "artifact_work_root") or "").replace("\\", "/").strip().strip("/")
    if not artifact_work_root and active_entry:
        artifact_work_root = active_entry.split("/", 1)[0]
    if not active_entry or not artifact_work_root:
        return None
    return RuntimeExecutionContract(
        active_entry=active_entry,
        artifact_work_root=artifact_work_root,
        writable_roots=[artifact_work_root],
        readonly_roots=["references", "skill", "published"],
        validation_profile=family,
        recovery_hints={
            "readonly_input_write": f"Copy required inputs into the current artifact work directory project/{artifact_work_root}/ before referencing them.",
            "output_root_mismatch": f"Continue edits inside the current artifact work directory project/{artifact_work_root}/.",
            "artifact_work_root_mismatch": f"Move or recreate the deliverable inside project/{artifact_work_root}/ before registering it.",
        },
    )


def _session_value(session: Any, key: str) -> Any:
    if isinstance(session, dict):
        return session.get(key)
    return getattr(session, key, None)


def _prepare_result(prepared) -> RuntimePrepareResult:
    payload = prepared.to_payload()
    contract = RuntimeExecutionContract(
        active_entry=prepared.entry_path,
        artifact_work_root=prepared.artifact_work_root,
        writable_roots=[prepared.artifact_work_root],
        readonly_roots=["references", "skill", "published"],
        validation_profile=prepared.family,
    )
    return RuntimePrepareResult(
        family=prepared.family,
        active_entry=prepared.entry_path,
        prepared_workspace=payload,
        runtime_contract_patch={
            "protocol_family": prepared.family,
            "prepared_entry": prepared.entry_path,
            "runtime_execution_contract": contract.to_payload(),
        },
        events=[
            {
                "event_type": "prepared_workspace_updated",
                "data": {
                    "prepared_workspace": payload,
                },
            }
        ],
    )
