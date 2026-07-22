from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.db.harness_session import harness_sync_session_scope
from app.services.agent_harness.capabilities.subagents.types import SubagentRequest, SubagentResult, SubagentTaskSpec
from app.services.agent_harness.runtime.artifacts.manifest import normalize_project_relative, read_artifact_manifest
from app.services.agent_harness.runtime.eventing.event_sink import sink_from_context
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.publisher import publish_presentation_event_async
from app.services.agent_harness.runtime.open_design.design_system_compliance import (
    compliance_context_from_runtime_contract,
    lint_design_system_compliance,
)
from app.services.agent_harness.runtime.open_design.eligibility import is_home_open_design_html_run
from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload

from .config import load_critique_config
from .contracts import CritiqueFinding, CritiqueWarning
from .eligibility import critique_eligibility_diagnostics, should_critique_manifest_entry, should_run_critique
from .publish_guard import PublishGuardFailure
from .repository import (
    create_run,
    finalize_run,
    get_run_for_harness_run,
    insert_round,
    list_rounds,
    mark_review_started,
    reopen_run_for_review,
    update_run_payload,
)
from .scoreboard import compute_composite, decide_round, select_fallback_round
from .workspace_snapshots import snapshot_round
from .work_root import safe_work_root, work_root_from_entry

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

logger = logging.getLogger(__name__)

REQUIRED_SCORING_ROLES = ("critic", "brand", "a11y", "copy")
QUALITY_REVIEW_DIMENSIONS: tuple[dict[str, str], ...] = (
    {"key": "visual-hierarchy", "role": "critic", "description": "Visual priority, focal path, and information hierarchy."},
    {"key": "layout-and-spacing", "role": "critic", "description": "Layout structure, spacing, density, and alignment."},
    {"key": "responsive-adaptation", "role": "critic", "description": "Desktop and mobile adaptation quality."},
    {"key": "typography-readability", "role": "critic", "description": "Typography scale, rhythm, line length, and readability."},
    {"key": "contrast-and-legibility", "role": "a11y", "description": "Contrast, foreground/background separation, and legibility."},
    {"key": "color-and-brand-fit", "role": "brand", "description": "Color system and fit with the intended brand tone."},
    {"key": "component-consistency", "role": "critic", "description": "Consistency of repeated components, controls, and states."},
    {"key": "interaction-clarity", "role": "a11y", "description": "Clarity of interactive targets, affordances, and feedback."},
    {"key": "keyboard-and-focus-support", "role": "a11y", "description": "Keyboard navigation and visible focus support."},
    {"key": "motion-and-user-preferences", "role": "a11y", "description": "Motion comfort and respect for user motion preferences."},
    {"key": "semantic-structure", "role": "a11y", "description": "Semantic HTML structure, landmarks, headings, and labels."},
    {"key": "content-clarity", "role": "copy", "description": "Plainness, specificity, and understandability of visible content."},
    {"key": "tone-consistency", "role": "copy", "description": "Tone consistency with audience and product intent."},
    {"key": "value-proposition-clarity", "role": "copy", "description": "Clarity of the core offer or value proposition."},
    {"key": "conversion-clarity", "role": "copy", "description": "Action path, CTA clarity, and conversion readiness."},
)
QUALITY_REVIEW_DIMENSION_KEYS = frozenset(item["key"] for item in QUALITY_REVIEW_DIMENSIONS)
QUALITY_REVIEW_PROTOCOL_VERSION = 2


class QualityReviewDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["critic", "brand", "a11y", "copy"]
    name: str = Field(..., min_length=1)
    score: float
    note: str = Field(..., min_length=1)


class QualityReviewRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    summary: str = Field(..., min_length=1)
    must_fix: list[str] = Field(default_factory=list)
    dimensions: list[QualityReviewDimension] = Field(default_factory=list)


class QualityReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., min_length=1)
    path: str | None = None
    note: str = Field(..., min_length=1)


class QualityReviewWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class QualityReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    review_id: str = Field(..., min_length=1)
    artifact_entry: str = Field(..., min_length=1)
    designer_notes: str = Field(..., min_length=1)
    critic: QualityReviewRole
    brand: QualityReviewRole
    a11y: QualityReviewRole
    copy_review: QualityReviewRole = Field(..., alias="copy")
    must_fix: list[str] = Field(default_factory=list)
    repair_instruction: str = ""
    evidence: list[QualityReviewEvidence] = Field(default_factory=list)
    warnings: list[QualityReviewWarning] = Field(default_factory=list)

    @field_validator("must_fix")
    @classmethod
    def _trim_must_fix(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()]


async def ensure_quality_review_authorized(
    *,
    ctx: "HarnessContext",
    manifest_entry: str,
) -> PublishGuardFailure | None:
    cfg = load_critique_config(settings)
    review_request: SubagentRequest | None = None
    review_result: Any = None
    review_packet: dict[str, Any] | None = None
    if not should_run_critique(
        cfg,
        runtime_profile=ctx.runtime_profile,
        artifact_mode=ctx.artifact_mode,
        skill_id=ctx.skill_id,
    ):
        return None
    manifest = read_artifact_manifest(ctx.user_id, ctx.conversation_id)
    work_root = safe_work_root(ctx.artifact_work_root) or work_root_from_entry(manifest_entry)
    if not should_critique_manifest_entry(manifest, artifact_work_root=work_root):
        await _finalize_not_critiqueable(ctx, cfg, manifest=manifest, artifact_work_root=work_root)
        return None

    try:
        fingerprint = _artifact_fingerprint(ctx, artifact_work_root=work_root)
        packet = _build_review_packet(
            ctx,
            cfg=cfg,
            manifest=manifest or {},
            manifest_entry=manifest_entry,
            artifact_work_root=work_root,
            artifact_fingerprint=fingerprint,
        )
        review_packet = packet
        with harness_sync_session_scope() as session:
            run = get_run_for_harness_run(session, ctx.run_id)
            if run is None:
                run = create_run(
                    session,
                    critique_run_id=packet["review_id"],
                    harness_run_id=ctx.run_id,
                    conversation_id=ctx.conversation_id,
                    user_id=ctx.user_id,
                    artifact_mode=ctx.artifact_mode,
                    artifact_work_root=work_root,
                    protocol_version=QUALITY_REVIEW_PROTOCOL_VERSION,
                    max_rounds=cfg.max_rounds,
                    score_scale=cfg.score_scale,
                    score_threshold=cfg.score_threshold,
                    fallback_policy=cfg.fallback_policy,
                )
            elif run.status != "running" and run.artifact_fingerprint == fingerprint:
                return None
            elif run.status != "running":
                if len(list_rounds(session, run.critique_run_id)) >= cfg.max_rounds:
                    return None
                run = reopen_run_for_review(session, critique_run_id=run.critique_run_id) or run
            packet["review_id"] = run.critique_run_id
            packet["round"] = len(list_rounds(session, run.critique_run_id)) + 1
            review_packet = packet
            update_run_payload(
                session,
                critique_run_id=run.critique_run_id,
                values={
                    "artifact_fingerprint": fingerprint,
                    "packet_hash": _hash_json(packet),
                    "latest_packet": packet,
                    "status": "running",
                },
            )
            mark_review_started(session, run.critique_run_id)
        await _emit_critique_event(ctx, "critique.started", _started_payload(packet, cfg))

        review_request, result = await _run_quality_review_subagent(ctx, packet)
        review_result = result
        if result.status != "completed":
            await _finalize_quality_review_subagent(
                ctx,
                request=review_request,
                result=result,
                status="degraded",
                reason_code="quality_review_subagent_failed",
            )
            return await _fail_open(ctx, cfg, packet, reason="quality_review_subagent_failed")
        try:
            review = _parse_review_output(_assistant_text(result.result), packet=packet, cfg=cfg)
        except Exception:
            logger.exception("QualityReview returned invalid output: run_id=%s", ctx.run_id)
            await _finalize_quality_review_subagent(
                ctx,
                request=review_request,
                result=result,
                status="degraded",
                reason_code="quality_review_invalid_output",
            )
            return await _fail_open(ctx, cfg, packet, reason="quality_review_invalid_output")
        failure = await _apply_review(ctx, cfg=cfg, packet=packet, review=review, manifest=manifest or {})
        await _finalize_quality_review_subagent(
            ctx,
            request=review_request,
            result=result,
            status="completed",
            reason_code=None,
            display_summary=_quality_review_display_summary(review),
        )
        return failure
    except Exception:
        logger.exception("QualityReview failed open: run_id=%s", ctx.run_id)
        if review_request is not None:
            await _finalize_quality_review_subagent(
                ctx,
                request=review_request,
                result=review_result,
                status="degraded",
                reason_code="quality_review_internal_error",
            )
        return await _fail_open(ctx, cfg, review_packet, reason="quality_review_internal_error")


def _build_review_packet(
    ctx: "HarnessContext",
    *,
    cfg: Any,
    manifest: dict[str, Any],
    manifest_entry: str,
    artifact_work_root: str,
    artifact_fingerprint: str,
) -> dict[str, Any]:
    history = ctx.history_summary if isinstance(ctx.history_summary, dict) else {}
    user_brief = (
        str(history.get("summary") or "")
        or str((ctx.conversation_state or {}).get("summary") if isinstance(ctx.conversation_state, dict) else "")
        or str((getattr(ctx, "conversation", None) or {}).get("title") if isinstance(getattr(ctx, "conversation", None), dict) else "")
    )
    design_system_compliance = _design_system_compliance_packet(ctx, manifest_entry=manifest_entry)
    active_design_system_context = compliance_context_from_runtime_contract(_runtime_contract_payload(ctx))
    return {
        "review_id": f"critique-{uuid.uuid4().hex}",
        "round": 1,
        "protocol_version": QUALITY_REVIEW_PROTOCOL_VERSION,
        "response_language": str(ctx.language or "zh").strip() or "zh",
        "user_brief": user_brief[:4000],
        "skill_context": {
            "skill_id": ctx.skill_id,
            "artifact_mode": ctx.artifact_mode,
        },
        "artifact": {
            "manifest": manifest,
            "active_entry": manifest_entry,
            "artifact_work_root": artifact_work_root,
            "fingerprint": artifact_fingerprint,
            "design_system_compliance": design_system_compliance,
            "active_design_system_context": active_design_system_context,
        },
        "evidence_request": {
            "tool": "capture_artifact_evidence",
            "viewports": ["desktop", "mobile"],
        },
        "rubric": {
            "score_scale": cfg.score_scale,
            "score_threshold": cfg.score_threshold,
            "roles": list(REQUIRED_SCORING_ROLES),
            "fixed_dimensions": list(QUALITY_REVIEW_DIMENSIONS),
            "weights": {"critic": 0.4, "brand": 0.2, "a11y": 0.2, "copy": 0.2},
            "pass_rule": "backend decides pass when composite >= threshold and must_fix is empty; design_system_compliance P0 findings are mandatory must-fix items",
        },
        "output_schema": {
            "review_id": "string",
            "artifact_entry": manifest_entry,
            "designer_notes": "string",
            "critic|brand|a11y|copy": {
                "score": f"0..{cfg.score_scale}",
                "summary": "string",
                "must_fix": ["string"],
                "dimensions": [{"role": "role", "name": "string", "score": f"0..{cfg.score_scale}", "note": "string"}],
            },
            "must_fix": ["string"],
            "repair_instruction": "string",
            "evidence": [{"kind": "string", "path": "string|null", "note": "string"}],
            "warnings": [{"code": "string", "message": "string"}],
        },
    }


async def _run_quality_review_subagent(ctx: "HarnessContext", packet: dict[str, Any]):
    handler = ctx.run_subagent_handler
    if not callable(handler):
        raise RuntimeError("subagent runner is not configured")
    ctx.hydrate_run_output_anchor()
    prompt = _render_quality_review_prompt(packet)
    request = SubagentRequest(
        task_id=f"quality-review-{uuid.uuid4().hex[:12]}",
        spec=SubagentTaskSpec(
            description="Quality review",
            prompt=prompt,
            subagent_type="QualityReview",
        ),
        auto_finalize_terminal=False,
    )
    packet["subagent_task_id"] = request.task_id
    setattr(ctx, "quality_review_packet", dict(packet))
    await _emit_subagent_card_queued(ctx, request)
    try:
        result = await handler(request, ctx)
    finally:
        if hasattr(ctx, "quality_review_packet"):
            delattr(ctx, "quality_review_packet")
    if not hasattr(result, "status"):
        raise RuntimeError("quality review subagent returned an invalid result")
    with harness_sync_session_scope() as session:
        update_run_payload(
            session,
            critique_run_id=str(packet["review_id"]),
            values={"subagent_task_id": request.task_id},
        )
    return request, result


def _render_quality_review_prompt(packet: dict[str, Any]) -> str:
    response_language = str(packet.get("response_language") or "zh").strip() or "zh"
    return (
        "Review the frozen artifact packet below. You must not modify files.\n"
        "First inspect the artifact source. If useful, call capture_artifact_evidence for desktop and mobile, "
        "then call analyze_image only when a real screenshot/image ref is available. Pass the screenshot_ref exactly as "
        "capture_artifact_evidence returned it; do not add project/, workspace/, or any other prefix. If screenshot evidence is unavailable, "
        "continue from source, layout, CSS, manifest, accessibility semantics, and copy.\n"
        f"Use response_language={response_language!r} for every user-visible prose value: must_fix, repair_instruction, "
        "designer_notes, role summaries, dimension notes, evidence notes, and warning messages. Keep JSON field names in English. "
        "For each role's dimensions array, use only rubric.fixed_dimensions keys in dimension.name. Do not invent, rename, "
        "translate, or vary dimension.name values; put the localized explanation in dimension.note instead.\n"
        "Return exactly one JSON object. Do not wrap it in Markdown fences.\n\n"
        f"{json.dumps(packet, ensure_ascii=False, indent=2)}"
    )


async def _apply_review(
    ctx: "HarnessContext",
    *,
    cfg: Any,
    packet: dict[str, Any],
    review: QualityReviewOutput,
    manifest: dict[str, Any],
) -> PublishGuardFailure | None:
    scores = {role: float(_role_review(review, role).score) for role in REQUIRED_SCORING_ROLES}
    composite = round(compute_composite(scores), 2)
    must_fix = _dedupe_text([*_system_must_fix(ctx, packet), *_merged_must_fix(review)])
    round_number = int(packet.get("round") or 1)
    findings = tuple(CritiqueFinding(role=_finding_role(item), text=item) for item in must_fix)
    warnings = tuple(CritiqueWarning(code=item.code, message=item.message) for item in review.warnings)
    snapshot_dir = snapshot_round(
        ctx,
        critique_run_id=str(packet["review_id"]),
        round_number=round_number,
        artifact_work_root=str(packet["artifact"]["artifact_work_root"]),
        active_entry=str(packet["artifact"]["active_entry"]),
        manifest=manifest,
        composite=composite,
        must_fix_count=len(must_fix),
        findings=findings,
        warnings=warnings,
    )
    snapshot_relpath = snapshot_dir.relative_to(Path(ctx.conversation_dir).resolve()).as_posix()
    payload = _review_payload(
        packet=packet,
        review=review,
        scores=scores,
        composite=composite,
        must_fix=must_fix,
        snapshot_relpath=snapshot_relpath,
        cfg=cfg,
    )
    with harness_sync_session_scope() as session:
        insert_round(
            session,
            critique_run_id=str(packet["review_id"]),
            round_number=round_number,
            active_entry=str(packet["artifact"]["active_entry"]),
            snapshot_relpath=snapshot_relpath,
            composite=composite,
            must_fix_count=len(must_fix),
            findings=[{"role": item.role, "text": item.text} for item in findings],
            warnings=[{"code": item.code, "message": item.message} for item in warnings],
        )
        update_run_payload(session, critique_run_id=str(packet["review_id"]), values=payload)
        stored_rounds = list_rounds(session, str(packet["review_id"]))
        decision = decide_round(composite=composite, must_fix_count=len(must_fix), cfg=cfg)
        if decision == "ship":
            finalize_run(
                session,
                critique_run_id=str(packet["review_id"]),
                status="shipped",
                best_round=round_number,
                score=composite,
                selected_snapshot_relpath=snapshot_relpath,
                warnings=[{"code": item.code, "message": item.message} for item in warnings],
            )
            payload["status"] = "shipped"
            payload["selected_round"] = round_number
            payload["selected_score"] = composite
            update_run_payload(session, critique_run_id=str(packet["review_id"]), values=payload)
            event_type = "critique.shipped"
            failure = None
        elif round_number >= cfg.max_rounds:
            selected = select_fallback_round(stored_rounds, cfg.fallback_policy)
            if selected is None:
                finalize_run(
                    session,
                    critique_run_id=str(packet["review_id"]),
                    status="failed",
                    best_round=None,
                    score=None,
                    selected_snapshot_relpath=None,
                    reason="no_valid_critique_round",
                    warnings=[{"code": item.code, "message": item.message} for item in warnings],
                )
                payload["status"] = "failed"
                event_type = "critique.failed"
                failure = PublishGuardFailure(
                    reason_code="critique_not_authorized",
                    message="Design Jury did not authorize publication.",
                    metadata=_repair_metadata(payload),
                )
            else:
                finalize_run(
                    session,
                    critique_run_id=str(packet["review_id"]),
                    status="below_threshold",
                    best_round=selected.round_number,
                    score=selected.composite,
                    selected_snapshot_relpath=selected.snapshot_relpath,
                    reason="below_threshold",
                    warnings=[{"code": item.code, "message": item.message} for item in warnings],
                )
                payload["status"] = "below_threshold"
                payload["selected_round"] = selected.round_number
                payload["selected_score"] = selected.composite
                update_run_payload(session, critique_run_id=str(packet["review_id"]), values=payload)
                event_type = "critique.below_threshold"
                failure = None
        else:
            payload["status"] = "running"
            update_run_payload(session, critique_run_id=str(packet["review_id"]), values=payload)
            event_type = "critique.round_completed"
            failure = PublishGuardFailure(
                reason_code="critique_not_authorized",
                message="Design Jury found blocking quality issues. Repair the must-fix items, then publish again.",
                metadata=_repair_metadata(payload),
            )
    await _emit_critique_event(ctx, event_type, payload)
    return failure


def _parse_review_output(text: str, *, packet: dict[str, Any], cfg: Any) -> QualityReviewOutput:
    raw = _extract_json(text)
    review = QualityReviewOutput.model_validate(raw)
    if review.review_id != str(packet["review_id"]):
        raise ValueError("review_id mismatch")
    if review.artifact_entry != str(packet["artifact"]["active_entry"]):
        raise ValueError("artifact_entry mismatch")
    for role in REQUIRED_SCORING_ROLES:
        role_review = _role_review(review, role)
        if role_review.score < 0 or role_review.score > cfg.score_scale:
            raise ValueError(f"{role} score out of range")
        if not role_review.dimensions:
            raise ValueError(f"{role} dimensions are required")
        for dimension in role_review.dimensions:
            if dimension.role != role:
                raise ValueError(f"{role} dimension role mismatch")
            if dimension.name not in QUALITY_REVIEW_DIMENSION_KEYS:
                raise ValueError(f"{role} dimension name is not in fixed rubric: {dimension.name}")
            if dimension.score < 0 or dimension.score > cfg.score_scale:
                raise ValueError(f"{role} dimension score out of range")
    return review


def _extract_json(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON object not found")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("QualityReview output must be a JSON object")
    return parsed


async def _finalize_not_critiqueable(ctx: "HarnessContext", cfg: Any, *, manifest: dict[str, Any] | None, artifact_work_root: str) -> None:
    with harness_sync_session_scope() as session:
        run = get_run_for_harness_run(session, ctx.run_id)
        if run is None:
            run = create_run(
                session,
                critique_run_id=f"critique-{uuid.uuid4().hex}",
                harness_run_id=ctx.run_id,
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                artifact_mode=ctx.artifact_mode,
                artifact_work_root=artifact_work_root,
                protocol_version=QUALITY_REVIEW_PROTOCOL_VERSION,
                max_rounds=cfg.max_rounds,
                score_scale=cfg.score_scale,
                score_threshold=cfg.score_threshold,
                fallback_policy=cfg.fallback_policy,
            )
        warning = {
            "code": "artifact_not_critiqueable",
            "message": "Current artifact is not eligible for Design Jury review; publishing is allowed.",
        }
        finalize_run(
            session,
            critique_run_id=run.critique_run_id,
            status="degraded",
            best_round=None,
            score=None,
            selected_snapshot_relpath=None,
            reason="artifact_not_critiqueable",
            warnings=[warning],
        )
        payload = {
            "critique_run_id": run.critique_run_id,
            "status": "degraded",
            "round": 0,
            "reason": "artifact_not_critiqueable",
            "scores": {},
            "dimensions": [],
            "findings": [],
            "warnings": [warning],
            "composite": None,
            "max_rounds": cfg.max_rounds,
            "score_scale": cfg.score_scale,
            "score_threshold": cfg.score_threshold,
            "publish_fallback": True,
            "eligibility": critique_eligibility_diagnostics(manifest, artifact_work_root=artifact_work_root),
        }
        update_run_payload(session, critique_run_id=run.critique_run_id, values=payload)
    await _emit_critique_event(ctx, "critique.degraded", payload)


async def _fail_open(
    ctx: "HarnessContext",
    cfg: Any,
    packet: dict[str, Any] | None,
    *,
    reason: str,
) -> None:
    critique_run_id = str((packet or {}).get("review_id") or "")
    warning = {
        "code": reason,
        "message": "Design Jury could not complete due to an internal review error; publishing is allowed.",
    }
    if critique_run_id:
        with harness_sync_session_scope() as session:
            run = get_run_for_harness_run(session, ctx.run_id)
            if run is not None and run.status == "running":
                finalize_run(
                    session,
                    critique_run_id=run.critique_run_id,
                    status="degraded",
                    best_round=None,
                    score=None,
                    selected_snapshot_relpath=None,
                    reason=reason,
                    warnings=[warning],
                )
    payload = {
        "critique_run_id": critique_run_id,
        "status": "degraded",
        "round": int((packet or {}).get("round") or 0),
        "reason": reason,
        "scores": {},
        "dimensions": [],
        "findings": [],
        "warnings": [warning],
        "composite": None,
        "max_rounds": cfg.max_rounds,
        "score_scale": cfg.score_scale,
        "score_threshold": cfg.score_threshold,
        "publish_fallback": True,
        "subagent_task_id": str((packet or {}).get("subagent_task_id") or ""),
    }
    await _emit_critique_event(ctx, "critique.degraded", payload)
    return None


def _quality_review_display_summary(review: "QualityReviewOutput") -> str:
    """Human-readable one-paragraph summary for the timeline subagent card,
    derived from the structured review (never the raw JSON)."""
    note = str(getattr(review, "designer_notes", "") or "").strip()
    if not note:
        critic = getattr(review, "critic", None)
        note = str(getattr(critic, "summary", "") or "").strip()
    return note


async def _finalize_quality_review_subagent(
    ctx: "HarnessContext",
    *,
    request: SubagentRequest,
    result: Any,
    status: Literal["completed", "degraded"],
    reason_code: str | None,
    display_summary: str | None = None,
) -> None:
    if isinstance(result, SubagentResult):
        result_payload = dict(result.result) if isinstance(result.result, dict) else {"value": result.result}
        transcript_ref = result_payload.get("transcript_ref")
        summary = result.summary
        usage = result.usage
    else:
        result_payload = {"value": result}
        transcript_ref = None
        summary = "QualityReview did not return a valid subagent result."
        usage = None
    # The raw subagent summary is the structured review JSON (used for scoring/gating).
    # For the timeline card we surface a human-readable note instead so it never renders
    # as a wall of JSON. Falls back to the raw summary if no clean summary is available.
    clean_summary = str(display_summary or "").strip()
    if clean_summary:
        summary = clean_summary
    finalized = SubagentResult(
        task_id=str(getattr(result, "task_id", "") or request.task_id),
        status=status,
        summary=summary,
        result=result_payload,
        usage=usage,
        reason_code=reason_code,
    )
    handler = ctx.run_subagent_handler
    owner = getattr(handler, "__self__", None)
    finalize = getattr(owner, "finalize_terminal_result", None)
    if callable(finalize):
        await finalize(
            parent_ctx=ctx,
            request=request,
            result=finalized,
            transcript_ref=str(transcript_ref) if transcript_ref else None,
        )


async def _emit_subagent_card_queued(ctx: "HarnessContext", request: SubagentRequest) -> None:
    payload = {
        "task_id": request.task_id,
        "label": request.label,
        "purpose": request.spec.purpose,
        "description": request.spec.description,
        "status": "queued",
        "subagent_type": request.subagent_type,
        "skill_id": ctx.skill_id,
        "parent_run_id": ctx.run_id,
        "task_spec": request.spec.to_dict(),
        **ctx.run_output_anchor_payload(),
    }
    draft = presentation_v2.event_draft(
        presentation_v2.subagent_card(
            conversation_id=ctx.conversation_id,
            run_id=ctx.run_id,
            payload=payload,
            status="queued",
        ),
        artifact_id=request.task_id,
        idempotency_key=f"run:{ctx.run_id}:subagent:{request.task_id}:created",
    )
    if ctx.runtime_gateway is not None:
        await ctx.emit_workflow_event(
            draft.event_type,
            draft.payload,
            block_id=draft.block_id,
            artifact_id=request.task_id,
            idempotency_key=draft.idempotency_key,
        )
    else:
        await publish_presentation_event_async(
            ctx.user_id,
            ctx.conversation_id,
            run_id=ctx.run_id,
            draft=draft,
        )


async def _emit_critique_event(ctx: "HarnessContext", event_type: str, payload: dict[str, Any]) -> None:
    identity = payload.get("round") or payload.get("reason") or payload.get("status")
    if ctx.runtime_gateway is not None:
        await ctx.emit_workflow_event(
            event_type,
            payload,
            artifact_id=str(payload.get("critique_run_id") or ""),
            idempotency_key=f"run:{ctx.run_id}:critique:{event_type}:{identity}",
        )
    else:
        sink_from_context(ctx).emit(
            event_type,
            data=payload,
            artifact_id=str(payload.get("critique_run_id") or ""),
            idempotency_key=f"run:{ctx.run_id}:critique:{event_type}:{identity}",
        )


def _review_payload(
    *,
    packet: dict[str, Any],
    review: QualityReviewOutput,
    scores: dict[str, float],
    composite: float,
    must_fix: list[str],
    snapshot_relpath: str,
    cfg: Any,
) -> dict[str, Any]:
    dimensions = []
    for role in REQUIRED_SCORING_ROLES:
        dimensions.extend(item.model_dump() for item in _role_review(review, role).dimensions)
    return {
        "critique_run_id": str(packet["review_id"]),
        "status": "running",
        "round": int(packet.get("round") or 1),
        "scores": scores,
        "dimensions": dimensions,
        "findings": [{"role": _finding_role(item), "text": item} for item in must_fix],
        "warnings": [item.model_dump() for item in review.warnings],
        "evidence": [item.model_dump() for item in review.evidence],
        "designer_notes": review.designer_notes,
        "repair_instruction": review.repair_instruction,
        "must_fix": must_fix,
        "must_fix_count": len(must_fix),
        "composite": composite,
        "max_rounds": cfg.max_rounds,
        "score_scale": cfg.score_scale,
        "score_threshold": cfg.score_threshold,
        "selected_round": None,
        "selected_score": None,
        "snapshot_relpath": snapshot_relpath,
        "artifact_fingerprint": str(packet["artifact"]["fingerprint"]),
        "packet_hash": _hash_json(packet),
        "subagent_task_id": str(packet.get("subagent_task_id") or ""),
    }


def _started_payload(packet: dict[str, Any], cfg: Any) -> dict[str, Any]:
    return {
        "critique_run_id": str(packet["review_id"]),
        "status": "running",
        "round": int(packet.get("round") or 1),
        "scores": {},
        "dimensions": [],
        "findings": [],
        "warnings": [],
        "composite": None,
        "max_rounds": cfg.max_rounds,
        "score_scale": cfg.score_scale,
        "score_threshold": cfg.score_threshold,
    }


def _repair_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "critique": payload,
        "repair_instruction": payload.get("repair_instruction") or _repair_instruction_from_findings(payload),
        "must_fix": list(payload.get("must_fix") or []),
        "recovery_hint": {
            "instruction": payload.get("repair_instruction") or _repair_instruction_from_findings(payload),
            "preferred_tools": ["read_file", "edit_file", "exec_command", "register_artifact", "publish_output"],
        },
    }


def _repair_instruction_from_findings(payload: dict[str, Any]) -> str:
    items = [str(item.get("text") or "") for item in list(payload.get("findings") or []) if isinstance(item, dict)]
    return "Repair the Design Jury must-fix items, then register_artifact and publish_output again:\n" + "\n".join(
        f"- {item}" for item in items if item
    )


def _merged_must_fix(review: QualityReviewOutput) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in review.must_fix:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            merged.append(text)
    for role in REQUIRED_SCORING_ROLES:
        for item in _role_review(review, role).must_fix:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def _system_must_fix(ctx: "HarnessContext", packet: dict[str, Any]) -> list[str]:
    artifact = packet.get("artifact") if isinstance(packet.get("artifact"), dict) else {}
    compliance = artifact.get("design_system_compliance") if isinstance(artifact, dict) else None
    values: list[str] = []
    values.extend(_compliance_must_fix(compliance if isinstance(compliance, dict) else None))
    values.extend(_evidence_compliance_must_fix(ctx, review_id=str(packet.get("review_id") or "")))
    return _dedupe_text(values)


def _compliance_must_fix(compliance: dict[str, Any] | None) -> list[str]:
    if not isinstance(compliance, dict):
        return []
    values: list[str] = []
    for item in list(compliance.get("findings") or []):
        if not isinstance(item, dict) or str(item.get("severity") or "") != "P0":
            continue
        message = str(item.get("message") or "").strip()
        fix = str(item.get("fix") or "").strip()
        if message and fix:
            values.append(f"{message} Fix: {fix}")
        elif message:
            values.append(message)
    return _dedupe_text(values)


def _evidence_compliance_must_fix(ctx: "HarnessContext", *, review_id: str) -> list[str]:
    safe_review_id = "".join(ch for ch in review_id if ch.isalnum() or ch in {"-", "_"})[:96] or "review"
    evidence_path = Path(ctx.conversation_dir).resolve() / "critique" / safe_review_id / "evidence" / "evidence.jsonl"
    if not evidence_path.is_file():
        return []
    values: list[str] = []
    try:
        lines = evidence_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        compliance = item.get("design_system_compliance")
        values.extend(_compliance_must_fix(compliance if isinstance(compliance, dict) else None))
    return _dedupe_text(values)


def _design_system_compliance_packet(ctx: "HarnessContext", *, manifest_entry: str) -> dict[str, Any] | None:
    if not is_home_open_design_html_run(ctx):
        return None
    if Path(manifest_entry).suffix.lower() not in {".html", ".htm"}:
        return None
    try:
        entry = normalize_project_relative(manifest_entry)
    except ValueError:
        return None
    project_dir = Path(ctx.project_dir).resolve()
    path = (project_dir / entry).resolve()
    try:
        path.relative_to(project_dir)
    except ValueError:
        return None
    if not path.is_file():
        return None
    runtime_contract = _runtime_contract_payload(ctx)
    active_ctx = compliance_context_from_runtime_contract(runtime_contract if isinstance(runtime_contract, dict) else None)
    result = lint_design_system_compliance(
        path.read_text(encoding="utf-8"),
        active_design_system_context=active_ctx,
    )
    return result.to_payload()


def _runtime_contract_payload(ctx: "HarnessContext") -> dict[str, Any] | None:
    payload = read_runtime_state_payload(ctx.user_id, ctx.conversation_id) or {}
    runtime_state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), dict) else {}
    runtime_contract = runtime_state.get("runtime_contract") if isinstance(runtime_state, dict) else None
    if not isinstance(runtime_contract, dict):
        snapshot = payload.get("runtime_snapshot_json") if isinstance(payload.get("runtime_snapshot_json"), dict) else {}
        runtime_contract = snapshot.get("runtime_contract") if isinstance(snapshot, dict) else None
    return dict(runtime_contract) if isinstance(runtime_contract, dict) else None


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _finding_role(text: str) -> str:
    lowered = str(text).lower()
    if "access" in lowered or "contrast" in lowered or "aria" in lowered:
        return "a11y"
    if "copy" in lowered or "文案" in lowered:
        return "copy"
    if "brand" in lowered or "品牌" in lowered:
        return "brand"
    return "critic"


def _role_review(review: QualityReviewOutput, role: str) -> QualityReviewRole:
    if role == "copy":
        return review.copy_review
    return getattr(review, role)


def _assistant_text(result_payload: Any) -> str:
    if isinstance(result_payload, dict):
        return str(result_payload.get("assistant_text") or result_payload.get("summary") or "")
    return str(result_payload or "")


def _artifact_fingerprint(ctx: "HarnessContext", *, artifact_work_root: str) -> str:
    root = (Path(ctx.project_dir) / artifact_work_root).resolve()
    project_dir = Path(ctx.project_dir).resolve()
    root.relative_to(project_dir)
    if not root.is_dir():
        raise ValueError("artifact work root does not exist")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(project_dir).as_posix()
        if "/critique/" in rel or rel.endswith(".map"):
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _hash_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
