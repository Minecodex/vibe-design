from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.services.agent_harness.capabilities.skill_protocols.registry import resolve_protocol_for_context
from app.services.agent_harness.capabilities.skill_protocols.tool_guard import (
    ProtocolToolGuard,
    tool_result_from_protocol_failure,
)
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.tools._internal.file_ops import workspace_path_metadata
from app.services.agent_harness.isolation.security.service import get_security_service
from app.services.agent_harness.runtime.artifacts.kind_registry import manifest_publish_mode
from app.services.agent_harness.runtime.artifacts.manifest import (
    mark_artifact_published,
    normalize_project_relative,
    read_artifact_manifest,
    validate_manifest_entry,
)
from app.services.agent_harness.runtime.artifacts.publisher import ArtifactPublisher
from app.services.agent_harness.runtime.eventing.event_sink import sink_from_context
from app.services.agent_harness.runtime.critique.lifecycle import ensure_quality_review_authorized
from app.services.agent_harness.runtime.critique.publish_guard import (
    PublishGuardFailure,
    prepare_critique_publish_selection,
)
from app.services.agent_harness.runtime.open_design.artifact_lint import lint_artifact
from app.services.agent_harness.runtime.open_design.artifact_lint_render import render_findings_for_agent
from app.services.agent_harness.runtime.open_design.contracts import ArtifactLintResult
from app.services.agent_harness.runtime.open_design.design_system_compliance import (
    compliance_context_from_runtime_contract,
    lint_design_system_compliance,
)
from app.services.agent_harness.runtime.open_design.eligibility import is_home_open_design_html_run
from app.services.agent_harness.workspace.generated_content.file_version_store import workspace_file_event_payload
from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class PublishOutputInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublishOutputTool(BaseTool):
    @property
    def name(self) -> str:
        return "publish_output"

    @property
    def description(self) -> str:
        return "Publish the registered artifact_manifest entry as a new versioned deliverable."

    @property
    def input_model(self) -> type[BaseModel]:
        return PublishOutputInput

    async def execute(self, params: PublishOutputInput, ctx: "HarnessContext") -> ToolResult:
        manifest = read_artifact_manifest(ctx.user_id, ctx.conversation_id)
        if not manifest:
            return ToolResult(
                output="No artifact_manifest is registered. Call register_artifact with the final deliverable entry before publish_output.",
                is_error=True,
                metadata={"reason_code": "artifact_manifest_missing", "required_tool": "register_artifact"},
            )

        try:
            manifest_entry = normalize_project_relative(str(manifest.get("entry") or ""))
        except ValueError as exc:
            return ToolResult(
                output=f"Invalid publish path: {exc}",
                is_error=True,
                metadata={"reason_code": "invalid_publish_path"},
            )

        validation = validate_manifest_entry(ctx, manifest)
        if not validation.get("valid"):
            return ToolResult(
                output="Artifact validation failed: " + "; ".join(list(validation.get("errors") or [])),
                is_error=True,
                metadata={"reason_code": "artifact_manifest_validation_failed", **validation},
            )

        protocol = resolve_protocol_for_context(ctx)
        guard_failure = ProtocolToolGuard(ctx, protocol).check_publish_entry(manifest_entry)
        if guard_failure is not None:
            return tool_result_from_protocol_failure(
                guard_failure,
                metadata={
                    "path": f"project/{manifest_entry}",
                    "file_path": manifest_entry,
                    "protocol_family": protocol.family,
                    "protocol_provider": protocol.provider,
                },
            )

        publish_mode = manifest_publish_mode(manifest)
        publisher = ArtifactPublisher(ctx, protocol)

        open_design_lint: dict | None = None
        design_system_compliance: dict | None = None

        resolved, resolved_mode, runtime_entry, publisher_validation = _resolve_publish_source(
            ctx=ctx,
            publisher=publisher,
            manifest_entry=manifest_entry,
            publish_mode=publish_mode,
        )
        if not publisher_validation.get("valid"):
            return _artifact_validation_error(ctx, resolved=resolved, validation=publisher_validation)

        early_lint_error, _, _ = _run_open_design_lint(
            ctx=ctx,
            protocol=protocol,
            manifest=manifest,
            manifest_entry=manifest_entry,
            resolved=resolved,
            resolved_mode=resolved_mode,
        )
        if early_lint_error is not None:
            return early_lint_error

        critique_failure = await ensure_quality_review_authorized(
            ctx=ctx,
            manifest_entry=manifest_entry,
        )
        if critique_failure is not None:
            return ToolResult(
                output=critique_failure.message,
                is_error=True,
                metadata={
                    "reason_code": critique_failure.reason_code,
                    **(critique_failure.metadata or {}),
                },
            )

        critique_selection = prepare_critique_publish_selection(ctx, manifest_entry=manifest_entry)
        if isinstance(critique_selection, PublishGuardFailure):
            return ToolResult(
                output=critique_selection.message,
                is_error=True,
                metadata={
                    "reason_code": critique_selection.reason_code,
                    **(critique_selection.metadata or {}),
                },
            )
        critique_publish_status = critique_selection.status if critique_selection is not None else None
        manifest = read_artifact_manifest(ctx.user_id, ctx.conversation_id) or manifest
        resolved, resolved_mode, runtime_entry, publisher_validation = _resolve_publish_source(
            ctx=ctx,
            publisher=publisher,
            manifest_entry=manifest_entry,
            publish_mode=publish_mode,
        )
        if critique_selection is not None:
            publisher_validation = {
                **publisher_validation,
                "critique_selection": {
                    "status": critique_selection.status,
                    "selected_round": critique_selection.selected_round,
                    "selected_score": critique_selection.selected_score,
                    "selected_snapshot_relpath": critique_selection.selected_snapshot_relpath,
                    "restored_snapshot": critique_selection.restored_snapshot,
                },
            }
        if not publisher_validation.get("valid"):
            return _artifact_validation_error(ctx, resolved=resolved, validation=publisher_validation)

        lint_error, open_design_lint, design_system_compliance = _run_open_design_lint(
            ctx=ctx,
            protocol=protocol,
            manifest=manifest,
            manifest_entry=manifest_entry,
            resolved=resolved,
            resolved_mode=resolved_mode,
        )
        if lint_error is not None:
            return lint_error

        publish_task = EphemeralTaskKey.build(
            domain="artifact-export",
            kind=resolved_mode,
            resource_parts=[
                ctx.user_id,
                ctx.conversation_id,
                manifest_entry,
                str(manifest.get("registered_at") or ""),
            ],
            version=_source_version(resolved),
        )
        coordinator = EphemeralTaskCoordinator()
        lease = await coordinator.start(publish_task, owner_prefix="publish")
        if not lease.acquired:
            snapshot = lease.snapshot
            if snapshot is not None and snapshot.status == "done" and isinstance(snapshot.result, dict):
                payload = dict(snapshot.result.get("payload") or snapshot.result)
                manifest = mark_artifact_published(ctx, publish_payload=payload)
                metadata = _publish_metadata(
                    payload,
                    manifest=manifest,
                    resolved=resolved,
                    ctx=ctx,
                    deduplicated=True,
                    critique_status=critique_publish_status,
                )
                return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=metadata)
            pending = {"status": "pending", "deduplicated": True, "entry": manifest_entry}
            return ToolResult(output=json.dumps(pending, ensure_ascii=False), metadata=pending)

        try:
            payload = publisher.publish(
                source_path=f"project/{manifest_entry}",
                entry_path=manifest_entry,
                validation={
                    **publisher_validation,
                    **({"open_design_lint": open_design_lint} if open_design_lint is not None else {}),
                    **({"design_system_compliance": design_system_compliance} if design_system_compliance is not None else {}),
                },
                publish_mode=resolved_mode,
                entry=runtime_entry,
                note=None,
            )
        except Exception as exc:
            await coordinator.fail(lease, error_type=type(exc).__name__)
            raise

        if open_design_lint is not None:
            payload = {**payload, "open_design_lint": open_design_lint}
        if design_system_compliance is not None:
            payload = {**payload, "design_system_compliance": design_system_compliance}
        manifest = mark_artifact_published(ctx, publish_payload=payload)
        payload = {
            **payload,
            "entry": manifest["entry"],
            "kind": manifest["kind"],
            "renderer": manifest["renderer"],
            "exports": manifest["exports"],
            "supporting_files": manifest.get("supporting_files") or [],
            "artifact_manifest": manifest,
            **({"open_design_lint": open_design_lint} if open_design_lint is not None else {}),
            **({"design_system_compliance": design_system_compliance} if design_system_compliance is not None else {}),
        }
        await coordinator.finish(lease, status="done", result={"payload": payload})
        sink_from_context(ctx).emit(
            "artifact_publish_validated",
            data={"artifact_manifest": manifest},
            persist=True,
            artifact_id=str(manifest.get("entry") or ""),
            idempotency_key=f"artifact_publish_validated:{ctx.run_id}:{manifest.get('entry')}",
        )
        sink_from_context(ctx).emit(
            "file_version_created",
            data=workspace_file_event_payload(payload),
            persist=True,
        )
        metadata = _publish_metadata(
            payload,
            manifest=manifest,
            resolved=resolved,
            ctx=ctx,
            critique_status=critique_publish_status,
        )
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=metadata)


def _source_version(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _resolve_publish_source(
    *,
    ctx: "HarnessContext",
    publisher: ArtifactPublisher,
    manifest_entry: str,
    publish_mode: str | None,
) -> tuple[Path, str, str | None, dict]:
    decision = get_security_service().check_read_path(ctx, location="root", path=f"project/{manifest_entry}")
    if not decision.allowed or decision.resolved_path is None:
        return (
            Path(ctx.project_dir) / manifest_entry,
            str(publish_mode or "file"),
            None,
            {
                "valid": False,
                "reason_code": "invalid_publish_path",
                "errors": [decision.reason or f"Path escapes workspace: {manifest_entry}"],
            },
        )
    resolved = decision.resolved_path
    resolved_mode, runtime_entry = publisher.resolve_publish_mode(
        entry_relative_path=manifest_entry,
        resolved_path=resolved,
        requested_mode=publish_mode,
    )
    publisher_validation = publisher.validate(resolved_path=resolved, publish_mode=resolved_mode)
    return resolved, resolved_mode, runtime_entry, publisher_validation


def _artifact_validation_error(ctx: "HarnessContext", *, resolved: Path, validation: dict) -> ToolResult:
    metadata = dict(validation)
    try:
        metadata["path"] = resolved.resolve().relative_to(ctx.conversation_dir.resolve()).as_posix()
    except ValueError:
        metadata["path"] = str(resolved)
    return ToolResult(
        output="Artifact validation failed: " + "; ".join(metadata.get("errors") or []),
        is_error=True,
        metadata=metadata,
    )


def _run_open_design_lint(
    *,
    ctx: "HarnessContext",
    protocol,
    manifest: dict,
    manifest_entry: str,
    resolved: Path,
    resolved_mode: str,
) -> tuple[ToolResult | None, dict | None, dict | None]:
    if not _should_run_open_design_lint(
        ctx=ctx,
        protocol=protocol,
        manifest=manifest,
        manifest_entry=manifest_entry,
        resolved_mode=resolved_mode,
    ):
        return None, None, None

    artifact_html = resolved.read_text(encoding="utf-8")
    findings = lint_artifact(artifact_html)
    lint_result = ArtifactLintResult(findings=findings)
    open_design_lint = lint_result.to_payload()
    compliance_result = lint_design_system_compliance(
        artifact_html,
        active_design_system_context=_active_design_system_context(ctx),
    )
    design_system_compliance = compliance_result.to_payload()
    combined_findings = [*findings, *compliance_result.findings]
    combined_lint_result = ArtifactLintResult(findings=combined_findings)
    if not combined_lint_result.blocks_publish:
        return None, open_design_lint, design_system_compliance

    reason_code = (
        "design_system_contract_failed"
        if compliance_result.blocks_publish and not lint_result.blocks_publish
        else "open_design_artifact_lint_failed"
    )
    return (
        ToolResult(
            output=render_findings_for_agent(combined_findings),
            is_error=True,
            metadata={
                "reason_code": reason_code,
                "failure_kind": "design_system_contract_failed" if compliance_result.blocks_publish else "artifact_lint_failed",
                "lint_findings": combined_lint_result.to_payload()["findings"],
                "p0_count": combined_lint_result.p0_count,
                "open_design_lint": open_design_lint,
                "design_system_compliance": design_system_compliance,
                "recovery_hint": {
                    "instruction": "Repair P0 findings, then register_artifact and publish_output again.",
                    "preferred_tools": [
                        "read_file",
                        "edit_file",
                        "exec_command",
                        "register_artifact",
                        "publish_output",
                    ],
                },
            },
        ),
        open_design_lint,
        design_system_compliance,
    )


def _publish_metadata(
    payload: dict,
    *,
    manifest: dict,
    resolved: Path,
    ctx: "HarnessContext",
    deduplicated: bool = False,
    critique_status: str | None = None,
) -> dict:
    entry = str(manifest.get("entry") or "")
    path_metadata = workspace_path_metadata(ctx, resolved, location="project", file_path=entry)
    metadata = {
        **payload,
        "artifact_manifest": manifest,
        "entry": entry,
        "kind": manifest.get("kind"),
        "renderer": manifest.get("renderer"),
        "exports": manifest.get("exports") or [],
        "supporting_files": manifest.get("supporting_files") or [],
        "published_file": path_metadata,
    }
    if deduplicated:
        metadata["deduplicated"] = True
    # Surface the critique outcome that authorized this publish so the workflow can
    # tell a clean "shipped" publish (finalize the run) from a fail-open "degraded"/
    # "failed" publish (let the model keep iterating instead of summarizing early).
    if critique_status is not None:
        metadata["critique_publish_status"] = critique_status
    return metadata


def _should_run_open_design_lint(
    *,
    ctx: "HarnessContext",
    protocol,
    manifest: dict,
    manifest_entry: str,
    resolved_mode: str,
) -> bool:
    if not is_home_open_design_html_run(ctx, protocol):
        return False
    if resolved_mode != "html_bundle":
        return False
    suffix = Path(manifest_entry).suffix.lower()
    if suffix not in {".html", ".htm"}:
        return False
    kind = str(manifest.get("kind") or "").lower()
    renderer = str(manifest.get("renderer") or "").lower()
    return kind in {"html", "web", "deck", "slides"} or renderer in {"html", "html_bundle", "browser"}


def _active_design_system_context(ctx: "HarnessContext") -> dict | None:
    payload = read_runtime_state_payload(ctx.user_id, ctx.conversation_id) or {}
    runtime_state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), dict) else {}
    runtime_contract = runtime_state.get("runtime_contract") if isinstance(runtime_state, dict) else None
    if not isinstance(runtime_contract, dict):
        snapshot = payload.get("runtime_snapshot_json") if isinstance(payload.get("runtime_snapshot_json"), dict) else {}
        runtime_contract = snapshot.get("runtime_contract") if isinstance(snapshot, dict) else None
    return compliance_context_from_runtime_contract(runtime_contract if isinstance(runtime_contract, dict) else None)
