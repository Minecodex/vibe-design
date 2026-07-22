from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .commands import (
    absolute_hidden_root_diagnostic,
    ambiguous_project_path_diagnostic,
    destructive_absolute_project_path_diagnostic,
    destructive_project_path_diagnostic,
    extract_command_diagnostics,
    literal_env_cwd_error,
    normalize_current_project_absolute_command,
    normalize_project_cwd_command,
    validate_command_text,
)
from .command_policy import analyze_command
from .command_policy.types import CommandVerdict
from app.services.agent_harness.isolation.sandbox.sandbox_manager import auto_allow_if_sandboxed
from .paths import (
    artifact_work_project_path,
    normalize_tool_base,
    read_text_file,
    resolve_command_cwd,
    resolve_semantic_path,
    resolve_project_file_path,
    resolve_work_file_path,
    workspace_path_for_base_tool,
    workspace_path_for_location,
    workspace_path_for_project_tool,
    resolve_workspace_file_path,
    sha256_text,
    validate_allowed_cwd,
)
from .types import NormalizationEntry, SecurityDecision, SecurityVerdict
from .workspace_v2 import WorkspacePathIntent, WorkspacePathResolver


class HarnessSecurityService:
    def check_read_path(self, ctx, *, location: str, path: str) -> SecurityDecision:
        decision = WorkspacePathResolver(ctx).resolve(
            workspace_path_for_location(location, path, ctx),
            WorkspacePathIntent.READ,
        )
        if not decision.allowed or decision.resolved_path is None:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=decision.reason or f"Path is not readable: {path}",
                reason_code=decision.reason_code or "path_outside_workspace",
                metadata=decision.metadata or {},
            )
        warnings = _normalization_warnings(decision.metadata)
        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            normalized_value=decision.normalized_path,
            resolved_path=decision.resolved_path,
            warnings=warnings,
            metadata=decision.metadata or {},
        )

    def check_write_path(self, ctx, *, location: str, path: str, base: str | None = None) -> SecurityDecision:
        if location != "project":
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=f"Unsupported write location: {location}",
                reason_code="unsupported_write_location",
            )
        if base is not None:
            try:
                normalized_base = normalize_tool_base(base, default="work")
            except ValueError as exc:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=str(exc),
                    reason_code="invalid_base",
                )
            if normalized_base in {"skill", "references", "published"}:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=f"base={normalized_base!r} is read-only and cannot be used for writes.",
                    reason_code="read_only_base",
                )
        workspace_path = (
            workspace_path_for_base_tool(base, path, ctx, default_base="work")
            if base
            else workspace_path_for_project_tool(path, ctx)
        )
        decision = WorkspacePathResolver(ctx).resolve(
            workspace_path,
            WorkspacePathIntent.WRITE,
        )
        work_root = artifact_work_project_path(ctx)
        if not decision.allowed or decision.resolved_path is None or not str(decision.normalized_path or "").startswith("project/"):
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=decision.reason or (
                    f"Writable files must live under {work_root or 'project/'}. Use the current artifact work directory for deliverables, not {path}."
                ),
                reason_code=decision.reason_code or "path_outside_workspace",
                metadata=decision.metadata or {},
            )
        if work_root:
            normalized_path = str(decision.normalized_path or "").replace("\\", "/").strip("/")
            if normalized_path != work_root and not normalized_path.startswith(f"{work_root}/"):
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=(
                        f"Writable deliverable paths must stay inside the current artifact work directory: {work_root}/. "
                        f"Use a work-directory-relative path like foo.html or {work_root}/foo.html, not {path}."
                    ),
                    reason_code="artifact_work_root_mismatch",
                    metadata={
                        **(decision.metadata or {}),
                        "artifact_work_root": work_root,
                        "normalized_path": normalized_path,
                    },
                )
        project_relative = str(decision.normalized_path).split("/", 1)[1]
        warnings = _normalization_warnings(decision.metadata, normalized_value=project_relative)
        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            normalized_value=project_relative,
            resolved_path=decision.resolved_path,
            warnings=warnings,
            metadata=decision.metadata or {},
        )

    def check_patch_targets(self, ctx, *, paths: list[str]) -> SecurityDecision:
        warning_entries: list[NormalizationEntry] = []
        resolved_paths: list[Path] = []
        for path in paths:
            decision = self.check_write_path(ctx, location="project", path=path)
            if not decision.allowed:
                return decision
            assert decision.resolved_path is not None
            resolved_paths.append(decision.resolved_path)
            warning_entries.extend(decision.warnings)
        metadata = {"resolved_paths": resolved_paths}
        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            warnings=tuple(warning_entries),
            metadata=metadata,
        )

    def check_command(self, ctx, *, command: str, cwd: str) -> SecurityDecision:
        cwd_error = literal_env_cwd_error(cwd)
        if cwd_error:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=cwd_error,
                reason_code="workspace_configuration_error",
            )

        validation_error, reason_code = validate_command_text(command)
        if validation_error:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=validation_error,
                reason_code=reason_code,
            )

        warnings: tuple[NormalizationEntry, ...] = ()
        normalized_value = command
        if cwd in {"", ".", "project", "work"}:
            effective_cwd = _command_effective_cwd(ctx, cwd)
            hidden_diagnostic = absolute_hidden_root_diagnostic(ctx, command)
            if hidden_diagnostic:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=hidden_diagnostic,
                    reason_code="hidden_root",
                    normalized_value=command,
                    metadata={
                        "cwd": effective_cwd,
                        "shell_path_diagnostic": {
                            "effective_cwd": effective_cwd,
                            "correction_applied": False,
                            "reason_code": "hidden_root",
                        },
                    },
                )
            destructive_absolute_diagnostic = destructive_absolute_project_path_diagnostic(ctx, command)
            if destructive_absolute_diagnostic:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=destructive_absolute_diagnostic,
                    reason_code="destructive_path_rewrite_blocked",
                    normalized_value=command,
                    metadata={
                        "cwd": effective_cwd,
                        "shell_path_diagnostic": {
                            "effective_cwd": effective_cwd,
                            "correction_applied": False,
                            "reason_code": "destructive_path_rewrite_blocked",
                        },
                    },
                )
            destructive_diagnostic = destructive_project_path_diagnostic(command)
            if destructive_diagnostic:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=destructive_diagnostic,
                    reason_code="destructive_path_rewrite_blocked",
                    normalized_value=command,
                    metadata={
                        "cwd": effective_cwd,
                        "shell_path_diagnostic": {
                            "effective_cwd": effective_cwd,
                            "correction_applied": False,
                            "reason_code": "destructive_path_rewrite_blocked",
                        },
                    },
                )
            ambiguous_diagnostic = ambiguous_project_path_diagnostic(command)
            if ambiguous_diagnostic:
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=ambiguous_diagnostic,
                    reason_code="ambiguous_shell_path",
                    normalized_value=command,
                    metadata={
                        "cwd": effective_cwd,
                        "shell_path_diagnostic": {
                            "effective_cwd": effective_cwd,
                            "correction_applied": False,
                            "reason_code": "ambiguous_shell_path",
                        },
                    },
                )
            normalized = normalize_project_cwd_command(command)
            if normalized is not None:
                normalized_value, warning = normalized
                warnings = (warning,)
            else:
                normalized_absolute = normalize_current_project_absolute_command(ctx, command)
                if normalized_absolute is not None:
                    normalized_value, warning = normalized_absolute
                    warnings = (warning,)

        command_report = analyze_command(normalized_value, cwd=cwd, ctx=ctx)
        report_metadata = {
            "command_security_report": command_report.to_metadata(),
            "risk_tags": list(command_report.risk_tags),
            "normalized_command": command_report.normalized_command,
        }

        # Verdict handling mirrors claude-code's headless+sandbox behaviour:
        #   block -> deny (genuinely dangerous; never auto-allowed)
        #   ask   -> auto-allow when the OS sandbox is in force (autoAllowBashIfSandboxed),
        #            otherwise deny (no human in the loop to approve)
        #   allow -> allow
        if command_report.verdict == CommandVerdict.BLOCK:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=command_report.reason,
                reason_code=command_report.reason_code,
                warnings=warnings,
                normalized_value=normalized_value,
                metadata=report_metadata,
            )

        if command_report.verdict == CommandVerdict.ASK:
            if not auto_allow_if_sandboxed():
                return SecurityDecision(
                    verdict=SecurityVerdict.DENY,
                    reason=command_report.reason,
                    reason_code=command_report.reason_code,
                    warnings=warnings,
                    normalized_value=normalized_value,
                    metadata={**report_metadata, "auto_allow_sandboxed": False},
                )
            report_metadata = {**report_metadata, "auto_allow_sandboxed": True}

        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            normalized_value=normalized_value,
            warnings=warnings,
            metadata=report_metadata,
        )

    def check_command_session_cwd(self, ctx, *, cwd: str) -> SecurityDecision:
        cwd_error = literal_env_cwd_error(cwd)
        if cwd_error:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=cwd_error,
                reason_code="workspace_configuration_error",
            )
        resolved = resolve_command_cwd(ctx, cwd)
        if resolved is None:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=f"cwd escapes workspace: {cwd}",
                reason_code="cwd_outside_workspace",
            )
        denied_reason = validate_allowed_cwd(ctx, resolved)
        if denied_reason:
            return SecurityDecision(
                verdict=SecurityVerdict.DENY,
                reason=denied_reason,
                reason_code="cwd_outside_workspace",
            )
        return SecurityDecision(
            verdict=SecurityVerdict.ALLOW,
            resolved_cwd=resolved,
        )

    def attach_normalization_warning(
        self,
        *,
        output: str,
        metadata: dict[str, Any],
        warnings: list[str] | tuple[str, ...],
        normalized_value: str | None = None,
        original: str | None = None,
        kind: str = "normalization",
    ) -> tuple[str, dict[str, Any]]:
        merged = dict(metadata or {})
        if not warnings:
            return output, merged
        warning_text = warnings[0]
        merged["normalization_kind"] = kind
        merged["normalization_warning"] = warning_text
        if normalized_value:
            merged["normalized_value"] = normalized_value
        if original:
            merged["original_input"] = original
        prefix = json.dumps(
            {
                "warning": warning_text,
                **({"normalized_value": normalized_value} if normalized_value else {}),
            },
            ensure_ascii=False,
        )
        return f"{prefix}\n{output}" if output else prefix, merged


def get_security_service() -> HarnessSecurityService:
    return _SERVICE


def _command_effective_cwd(ctx, cwd: str) -> str:
    if ctx is None:
        return str(cwd or "project")
    resolved = resolve_command_cwd(ctx, cwd)
    return str(resolved) if resolved is not None else str(cwd or "project")


def _normalization_warnings(
    metadata: dict[str, Any] | None,
    *,
    normalized_value: str | None = None,
) -> tuple[NormalizationEntry, ...]:
    normalization = (metadata or {}).get("path_normalization")
    if not isinstance(normalization, dict) or not normalization.get("correction_applied"):
        return ()
    normalized = normalized_value or str(normalization.get("normalized_path") or "")
    original = str(normalization.get("original_path") or "")
    kind = str(normalization.get("normalization_kind") or "path_normalization")
    warning = (
        f"Normalized structured workspace path from {original!r} to {normalized!r} "
        f"({kind}, confidence={normalization.get('confidence') or 'high'})."
    )
    return (
        NormalizationEntry(
            warning=warning,
            normalized_value=normalized,
            original_value=original,
            kind="path_normalization",
        ),
    )


__all__ = [
    "HarnessSecurityService",
    "extract_command_diagnostics",
    "get_security_service",
    "read_text_file",
    "resolve_semantic_path",
    "resolve_workspace_file_path",
    "sha256_text",
]


_SERVICE = HarnessSecurityService()
