from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent_harness.workspace.generated_content.entry_validation_service import (
    validate_entry_path,
    validate_html_bundle_entry_path,
)
from app.services.agent_harness.workspace.generated_content.job_workspace_service import JobWorkspaceService

if TYPE_CHECKING:
    from app.services.agent_harness.capabilities.skill_protocols.base import SkillProtocol
    from app.services.agent_harness.core.context import HarnessContext


class ArtifactPublisher:
    """Manifest-driven publishing facade."""

    def __init__(self, ctx: "HarnessContext", protocol: "SkillProtocol") -> None:
        self.ctx = ctx
        self.protocol = protocol

    def resolve_publish_mode(
        self,
        *,
        entry_relative_path: str,
        resolved_path: Path,
        requested_mode: str | None,
    ) -> tuple[str, str | None]:
        del entry_relative_path
        requested = str(requested_mode or "").strip().lower()
        if requested:
            mode = requested
        elif resolved_path.suffix.lower() in {".html", ".htm"}:
            mode = "html_bundle"
        else:
            mode = "file"
        entry = resolved_path.name if mode == "html_bundle" else None
        return mode, entry

    def validate(self, *, resolved_path: Path, publish_mode: str) -> dict[str, Any]:
        mode = str(publish_mode or "").strip().lower() or "file"
        if (
            getattr(getattr(self.protocol, "publish_profile", None), "skip_html_validation", False)
            and mode == "html_bundle"
        ):
            return {
                "valid": False,
                "kind": "media",
                "errors": ["media protocol outputs must not be published as html_bundle"],
                "protocol_family": getattr(self.protocol, "family", None),
                "protocol_provider": getattr(self.protocol, "provider", None),
            }
        if mode == "html_bundle":
            return validate_html_bundle_entry_path(resolved_path)
        return validate_entry_path(resolved_path)

    def publish(
        self,
        *,
        source_path: str,
        entry_path: str,
        validation: dict[str, Any],
        publish_mode: str,
        entry: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        service = JobWorkspaceService(
            user_id=self.ctx.user_id,
            conversation_id=self.ctx.conversation_id,
            run_id=self.ctx.run_id,
            conversation_dir=self.ctx.conversation_dir,
        )
        return service.publish_output(
            source_path=source_path,
            entry_path=entry_path,
            validation=validation,
            mode=publish_mode,
            entry=entry,
            note=note,
        )
