from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent_harness.capabilities.skill_protocols.base import ProtocolFailure
from app.services.agent_harness.isolation.security.paths import active_artifact_work_root

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


_PROTECTED_ROOTS = ("references", "skill", "published", ".meta", ".agent", "logs")


class ToolPolicyService:
    """Manifest-era artifact work-root policy."""

    def __init__(self, ctx: "HarnessContext") -> None:
        self.ctx = ctx
        self.artifact_work_root = active_artifact_work_root(ctx)

    @property
    def active(self) -> bool:
        return bool(self.artifact_work_root)

    def check_write_target(self, normalized_path: str, *, operation: str = "write") -> ProtocolFailure | None:
        del operation
        target = _project_relative(normalized_path)
        protected = _protected_root(normalized_path)
        if protected is not None:
            return _failure(
                "readonly_root_write" if protected in {"references", "skill"} else "system_root_write",
                target=normalized_path,
                artifact_work_root=self.artifact_work_root,
                next_tool="exec_command",
            )
        if not self.artifact_work_root or _is_inside(target, self.artifact_work_root):
            return None
        return _failure(
            "artifact_work_root_mismatch",
            target=target,
            artifact_work_root=self.artifact_work_root,
            next_tool="write_file",
        )

    def check_publish_entry(self, entry_relative_path: str) -> ProtocolFailure | None:
        target = _project_relative(entry_relative_path)
        if self.artifact_work_root and not _is_inside(target, self.artifact_work_root):
            return _failure(
                "artifact_work_root_mismatch",
                target=target,
                artifact_work_root=self.artifact_work_root,
                next_tool="register_artifact",
            )
        return None

    def check_changed_conversation_path(self, conversation_path: str) -> ProtocolFailure | None:
        protected = _protected_root(conversation_path)
        if protected is not None:
            return _failure(
                "readonly_root_write" if protected in {"references", "skill"} else "system_root_write",
                target=conversation_path,
                artifact_work_root=self.artifact_work_root,
                next_tool="exec_command",
            )
        if not str(conversation_path or "").replace("\\", "/").lstrip("/").startswith("project/"):
            return None
        target = _project_relative(conversation_path)
        if self.artifact_work_root and not _is_inside(target, self.artifact_work_root):
            return _failure(
                "artifact_work_root_mismatch",
                target=target,
                artifact_work_root=self.artifact_work_root,
                next_tool="write_file",
            )
        return None


def _failure(
    failure_kind: str,
    *,
    target: str,
    artifact_work_root: str | None,
    next_tool: str,
) -> ProtocolFailure:
    root = f"project/{artifact_work_root}/" if artifact_work_root else "the current artifact work directory"
    if failure_kind == "readonly_root_write":
        message = f"{target} is read-only input material and cannot be modified as deliverable output."
        action = f"Copy needed inputs into {root} before editing or referencing them."
    elif failure_kind == "system_root_write":
        message = f"{target} is a system-managed root and cannot be written by tools."
        action = f"Write deliverable files inside {root}, then register_artifact and publish_output."
    else:
        message = f"{target} is outside the current artifact work directory ({root})."
        action = f"Move or recreate the deliverable inside {root}, then register the manifest entry."
    return ProtocolFailure(
        failure_kind=failure_kind,
        message=message,
        allowed_artifact_work_root=artifact_work_root,
        suggested_next_tool=next_tool,
        suggested_action=action,
        protocol_family="manifest",
    )


def _protected_root(path: str) -> str | None:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    first = normalized.split("/", 1)[0]
    return first if first in _PROTECTED_ROOTS else None


def _project_relative(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    if normalized.startswith("project/"):
        normalized = normalized[8:]
    return normalized.strip("/")


def _is_inside(path: str, root: str | None) -> bool:
    normalized = _project_relative(path)
    normalized_root = _project_relative(root or "")
    return bool(normalized_root) and (normalized == normalized_root or normalized.startswith(f"{normalized_root}/"))
