from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.runtime.artifacts.manifest import project_file
from app.services.agent_harness.runtime.critique.evidence_renderer import capture_artifact_screenshot
from app.services.agent_harness.runtime.critique.work_root import normalize_relpath
from app.services.agent_harness.runtime.open_design.design_system_compliance import (
    compliance_context_from_runtime_contract,
    lint_design_system_compliance,
)

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class CaptureArtifactEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(..., min_length=1)
    entry: str = Field(..., min_length=1)
    viewport: str = Field(default="desktop", pattern="^(desktop|mobile)$")


class CaptureArtifactEvidenceTool(BaseTool):
    @property
    def name(self) -> str:
        return "capture_artifact_evidence"

    @property
    def description(self) -> str:
        return (
            "Internal QualityReview tool. Capture deterministic evidence for the frozen artifact entry. "
            "This tool never writes inside the artifact work root."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return CaptureArtifactEvidenceInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return False

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, CaptureArtifactEvidenceInput)
        packet = _quality_review_packet(ctx)
        if not packet:
            return "capture_artifact_evidence is only available during an internal QualityReview run."
        if str(packet.get("review_id") or "") != params.review_id:
            return "review_id does not match the active QualityReview packet."
        expected = normalize_relpath((packet.get("artifact") or {}).get("active_entry"))
        if normalize_relpath(params.entry) != expected:
            return "entry does not match the active QualityReview artifact."
        return None

    async def execute(self, params: CaptureArtifactEvidenceInput, ctx: "HarnessContext") -> ToolResult:
        packet = _quality_review_packet(ctx)
        assert packet is not None
        entry = normalize_relpath(params.entry)
        source = project_file(ctx, entry).resolve()
        conversation_dir = Path(ctx.conversation_dir).resolve()
        try:
            source.relative_to(conversation_dir)
        except ValueError:
            return ToolResult(
                output=json.dumps({"error": "artifact entry escapes conversation directory"}, ensure_ascii=False),
                is_error=True,
                metadata={"reason_code": "artifact_entry_escape"},
            )
        if not source.is_file():
            return ToolResult(
                output=json.dumps({"error": "artifact entry not found", "entry": entry}, ensure_ascii=False),
                is_error=True,
                metadata={"reason_code": "artifact_entry_missing", "entry": entry},
            )

        evidence_dir = _evidence_dir(ctx, params.review_id)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".txt"
        html_copy = evidence_dir / f"{params.viewport}-{uuid.uuid4().hex[:8]}{suffix}"
        shutil.copy2(source, html_copy)
        relpath = html_copy.relative_to(conversation_dir).as_posix()
        screenshot = await capture_artifact_screenshot(
            ctx=ctx,
            entry=entry,
            viewport=params.viewport,
            evidence_dir=evidence_dir,
        )
        warnings = []
        if screenshot.warning:
            warnings.append(screenshot.warning)
        design_system_compliance = None
        active_design_system_context = _active_design_system_context(packet)
        if screenshot.screenshot_ref and active_design_system_context is not None:
            screenshot_path = conversation_dir / screenshot.screenshot_ref
            design_system_compliance = lint_design_system_compliance(
                source.read_text(encoding="utf-8"),
                active_design_system_context=active_design_system_context,
                screenshot_path=screenshot_path,
            ).to_payload()
        payload: dict[str, Any] = {
            "review_id": params.review_id,
            "entry": entry,
            "viewport": params.viewport,
            "evidence_ref": relpath,
            "screenshot_ref": screenshot.screenshot_ref,
            "design_system_compliance": design_system_compliance,
            "warnings": warnings,
        }
        with (evidence_dir / "evidence.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False),
            metadata={"kind": "artifact_evidence", **payload},
        )


def _quality_review_packet(ctx: "HarnessContext") -> dict[str, Any] | None:
    packet = getattr(ctx, "quality_review_packet", None)
    return packet if isinstance(packet, dict) else None


def _active_design_system_context(packet: dict[str, Any]) -> dict[str, Any] | None:
    artifact = packet.get("artifact") if isinstance(packet.get("artifact"), dict) else {}
    active_ctx = artifact.get("active_design_system_context") if isinstance(artifact, dict) else None
    if isinstance(active_ctx, dict):
        return active_ctx
    runtime_contract = artifact.get("runtime_contract") if isinstance(artifact, dict) else None
    return compliance_context_from_runtime_contract(runtime_contract if isinstance(runtime_contract, dict) else None)


def _evidence_dir(ctx: "HarnessContext", review_id: str) -> Path:
    safe_review_id = "".join(ch for ch in str(review_id) if ch.isalnum() or ch in {"-", "_"})[:96] or "review"
    return Path(ctx.conversation_dir).resolve() / "critique" / safe_review_id / "evidence"
