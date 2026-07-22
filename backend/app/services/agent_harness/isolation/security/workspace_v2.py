from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class WorkspacePathIntent(StrEnum):
    READ = "read"
    LIST = "list"
    WRITE = "write"
    EDIT = "edit"
    EXEC_CWD = "exec_cwd"
    PUBLISH = "publish"
    PREVIEW = "preview"
    PROJECT_SCAN = "project_scan"


class WorkspaceRootKind(StrEnum):
    PROJECT = "project"
    REFERENCES = "references"
    REFERENCE_INPUTS = "references.inputs"
    REFERENCE_SOURCES = "references.sources"
    REFERENCE_GENERATED = "references.generated"
    SKILL = "skill"
    PUBLISHED = "published"
    AGENT = "agent"
    META = "meta"
    LOGS = "logs"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WorkspacePathDecision:
    allowed: bool
    normalized_path: str | None = None
    resolved_path: Path | None = None
    root_kind: WorkspaceRootKind = WorkspaceRootKind.UNKNOWN
    readonly: bool = False
    writable: bool = False
    hidden: bool = False
    previewable: bool = False
    publishable: bool = False
    reason: str | None = None
    reason_code: str | None = None
    metadata: dict[str, Any] | None = None


class WorkspacePathResolver:
    """Resolve model-visible v2 workspace paths by intent.

    V2 paths are physical, conversation-root-relative paths. The only writable
    deliverable root is project/. references/, skill/, and published/ are
    readable reference or system roots. Hidden roots are denied to model-facing
    access.
    """

    _HIDDEN_ROOTS = {
        ".agent": WorkspaceRootKind.AGENT,
        ".meta": WorkspaceRootKind.META,
        "logs": WorkspaceRootKind.LOGS,
    }
    _READ_INTENTS = {
        WorkspacePathIntent.READ,
        WorkspacePathIntent.LIST,
        WorkspacePathIntent.PREVIEW,
        WorkspacePathIntent.PROJECT_SCAN,
    }
    _WRITE_INTENTS = {
        WorkspacePathIntent.WRITE,
        WorkspacePathIntent.EDIT,
    }

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.workspace_root = Path(ctx.conversation_dir).resolve()

    def resolve(self, path: str, intent: WorkspacePathIntent | str) -> WorkspacePathDecision:
        resolved_intent = WorkspacePathIntent(str(intent))
        normalized, error_code, error_message, normalization = self._normalize(path)
        normalization["operation_type"] = resolved_intent.value
        if error_code:
            normalization["rejected"] = True
            normalization["reason_code"] = error_code
            return WorkspacePathDecision(
                allowed=False,
                normalized_path=normalized,
                reason=error_message,
                reason_code=error_code,
                metadata={"intent": resolved_intent.value, "path_normalization": normalization},
            )

        assert normalized is not None
        root_kind = self._root_kind(normalized)
        hidden = root_kind in {WorkspaceRootKind.AGENT, WorkspaceRootKind.META, WorkspaceRootKind.LOGS}
        readonly = root_kind in {
            WorkspaceRootKind.REFERENCES,
            WorkspaceRootKind.REFERENCE_INPUTS,
            WorkspaceRootKind.REFERENCE_SOURCES,
            WorkspaceRootKind.REFERENCE_GENERATED,
            WorkspaceRootKind.SKILL,
            WorkspaceRootKind.PUBLISHED,
        }
        writable = root_kind == WorkspaceRootKind.PROJECT
        publishable = root_kind == WorkspaceRootKind.PROJECT
        previewable = root_kind in {
            WorkspaceRootKind.PROJECT,
            WorkspaceRootKind.REFERENCES,
            WorkspaceRootKind.REFERENCE_INPUTS,
            WorkspaceRootKind.REFERENCE_SOURCES,
            WorkspaceRootKind.REFERENCE_GENERATED,
            WorkspaceRootKind.PUBLISHED,
        }

        if normalized == "work" or normalized.startswith("work/"):
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                reason_code="legacy_work_path",
                reason="Agent Runtime Protocol v2 uses project-relative paths. Use the current artifact work directory or project/ paths, not work/ paths.",
            )
        if hidden:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                hidden=True,
                reason_code="hidden_root",
                reason=f"{normalized.split('/', 1)[0]} is an internal system root and is not model-visible.",
            )
        if root_kind == WorkspaceRootKind.UNKNOWN:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                reason_code="unknown_root",
                reason="V2 workspace paths must start with project/, references/, skill/, or published/.",
            )
        if resolved_intent in self._WRITE_INTENTS and not writable:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                readonly=readonly,
                reason_code="readonly_root",
                reason=f"{normalized.split('/', 1)[0]} is read-only. Write deliverables under project/.",
            )
        if resolved_intent == WorkspacePathIntent.PUBLISH and root_kind != WorkspaceRootKind.PROJECT:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                readonly=readonly,
                previewable=previewable,
                reason_code="publish_outside_project",
                reason="Only files under project/ can be published.",
            )
        if resolved_intent == WorkspacePathIntent.EXEC_CWD and root_kind != WorkspaceRootKind.PROJECT:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                readonly=readonly,
                reason_code="cwd_outside_project",
                reason="Command cwd must be the workspace root or a directory under project/.",
            )

        if root_kind == WorkspaceRootKind.SKILL:
            skill_root = Path(getattr(self.ctx, "active_skill_dir", None) or getattr(self.ctx, "skill_dir", self.workspace_root / "skill")).resolve()
            skill_relative = normalized.split("/", 1)[1] if "/" in normalized else ""
            candidate = (skill_root / skill_relative).resolve()
            try:
                candidate.relative_to(skill_root)
            except ValueError:
                return self._deny(
                    normalized=normalized,
                    root_kind=root_kind,
                    reason_code="path_outside_workspace",
                    reason="Path escapes skill root.",
                )
            return WorkspacePathDecision(
                allowed=True,
                normalized_path=normalized,
                resolved_path=candidate,
                root_kind=root_kind,
                readonly=readonly,
                writable=writable,
                hidden=hidden,
                previewable=previewable,
                publishable=publishable,
                metadata={"intent": resolved_intent.value, "path_normalization": normalization},
            )

        candidate = (self.workspace_root / normalized).resolve()
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError:
            return self._deny(
                normalized=normalized,
                root_kind=root_kind,
                reason_code="path_outside_workspace",
                reason="Path escapes workspace.",
            )

        return WorkspacePathDecision(
            allowed=True,
            normalized_path=normalized,
            resolved_path=candidate,
            root_kind=root_kind,
            readonly=readonly,
            writable=writable,
            hidden=hidden,
            previewable=previewable,
            publishable=publishable,
            metadata={"intent": resolved_intent.value, "path_normalization": normalization},
        )

    def _normalize(self, raw_path: str) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
        raw_original = str(raw_path or "")
        raw = raw_original.strip().replace("\\", "/")
        audit: dict[str, Any] = {
            "original_path": raw_original,
            "normalized_path": None,
            "normalization_kind": "identity",
            "confidence": "high",
            "correction_applied": False,
            "rejected": False,
        }
        if not raw:
            return None, "empty_path", "Path is required.", audit
        decoded = unquote(raw)
        if decoded != raw:
            audit["normalization_kind"] = "url_decoded"
            audit["correction_applied"] = True
        if "\x00" in decoded:
            audit["normalized_path"] = decoded
            return decoded, "null_byte", "Path contains a null byte.", audit
        path = decoded.strip().lstrip("/")
        if not path or path == ".":
            path = "project"
        if _looks_absolute(decoded):
            audit["normalized_path"] = path
            return path, "absolute_path", "Absolute paths are not allowed; use a workspace-relative v2 path.", audit
        parts = tuple(part for part in path.split("/") if part not in {"", "."})
        if any(part == ".." for part in parts):
            normalized = "/".join(parts)
            audit["normalized_path"] = normalized
            return normalized, "path_traversal", "Parent traversal is not allowed in workspace paths.", audit
        collapsed = _collapse_duplicate_semantic_root(parts)
        if collapsed != parts:
            audit["normalization_kind"] = "duplicate_semantic_root"
            audit["correction_applied"] = True
        elif "\\" in raw_original:
            audit["normalization_kind"] = "separator_normalized"
            audit["correction_applied"] = True
        normalized = "/".join(collapsed)
        audit["normalized_path"] = normalized
        audit["semantic_root"] = normalized.split("/", 1)[0] if normalized else None
        return normalized, None, None, audit

    def _root_kind(self, normalized: str) -> WorkspaceRootKind:
        first = normalized.split("/", 1)[0]
        if first == "project":
            return WorkspaceRootKind.PROJECT
        if first == "references":
            second = normalized.split("/", 2)[1] if "/" in normalized else ""
            if second == "inputs":
                return WorkspaceRootKind.REFERENCE_INPUTS
            if second == "sources":
                return WorkspaceRootKind.REFERENCE_SOURCES
            if second == "generated":
                return WorkspaceRootKind.REFERENCE_GENERATED
            return WorkspaceRootKind.REFERENCES
        if first == "skill":
            return WorkspaceRootKind.SKILL
        if first == "published":
            return WorkspaceRootKind.PUBLISHED
        return self._HIDDEN_ROOTS.get(first, WorkspaceRootKind.UNKNOWN)

    @staticmethod
    def _deny(
        *,
        normalized: str | None,
        root_kind: WorkspaceRootKind,
        reason_code: str,
        reason: str,
        readonly: bool = False,
        hidden: bool = False,
        previewable: bool = False,
    ) -> WorkspacePathDecision:
        return WorkspacePathDecision(
            allowed=False,
            normalized_path=normalized,
            root_kind=root_kind,
            readonly=readonly,
            hidden=hidden,
            previewable=previewable,
            reason=reason,
            reason_code=reason_code,
        )


def _looks_absolute(path: str) -> bool:
    candidate = Path(path)
    if candidate.is_absolute():
        return True
    if len(path) >= 3 and path[1] == ":" and path[2] in {"/", "\\"}:
        return True
    return path.startswith("//")


def _collapse_duplicate_semantic_root(parts: tuple[str, ...]) -> tuple[str, ...]:
    if len(parts) >= 2 and parts[0] == parts[1] and parts[0] in {"project", "references", "skill", "published"}:
        return (parts[0], *parts[2:])
    return parts
