from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.runtime.artifacts.manifest import (
    build_artifact_manifest,
    write_artifact_manifest,
)
from app.services.agent_harness.runtime.eventing.event_sink import sink_from_context

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class RegisterArtifactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry: str = Field(..., description="Final deliverable entry path under project/.")
    kind: str = Field(..., description="Artifact kind from the registry, such as spreadsheet, document, deck, html, svg, file, or code.")
    title: str | None = Field(None, description="Optional human-readable artifact title; omit to use the entry filename.")
    supporting_files: list[str] = Field(default_factory=list, description="Supporting project files used to build or validate the entry.")


class RegisterArtifactTool(BaseTool):
    @property
    def name(self) -> str:
        return "register_artifact"

    @property
    def description(self) -> str:
        return (
            "Register the final project deliverable as an artifact manifest. "
            "The entry must be the user-facing deliverable file; scripts and validators belong in supporting_files."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return RegisterArtifactInput

    async def execute(self, params: RegisterArtifactInput, ctx: "HarnessContext") -> ToolResult:
        manifest, errors = build_artifact_manifest(
            ctx,
            entry=params.entry,
            kind=params.kind,
            title=params.title,
            supporting_files=params.supporting_files,
        )
        if manifest is None:
            return ToolResult(
                output="Artifact registration failed: " + "; ".join(errors),
                is_error=True,
                metadata={"reason_code": "artifact_registration_failed", "errors": errors},
            )

        written = write_artifact_manifest(ctx, manifest)
        sink_from_context(ctx).emit(
            "artifact_registered",
            data={"artifact_manifest": written},
            persist=True,
            artifact_id=str(written.get("entry") or ""),
            idempotency_key=f"artifact_registered:{ctx.run_id}:{written.get('entry')}",
        )
        return ToolResult(
            output=json.dumps(
                {
                    "entry": written["entry"],
                    "kind": written["kind"],
                    "renderer": written["renderer"],
                    "exports": written["exports"],
                    "supporting_files": written["supporting_files"],
                    "status": written["status"],
                },
                ensure_ascii=False,
            ),
            metadata={"artifact_manifest": written},
        )
