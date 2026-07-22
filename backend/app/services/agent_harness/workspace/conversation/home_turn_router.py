from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import settings
from app.core.default_models import get_default_multimodal_model
from app.services.multimodal_service import resolve_multimodal_provider

logger = logging.getLogger(__name__)


HOME_TURN_ROUTE_LABELS = [
    "informational_turn",
    "artifact_creation",
    "artifact_revision",
    "workflow_continuation",
]

PLAN_FIRST_ARTIFACT_MODES = {"web", "document", "spreadsheet", "slides"}
DESIGN_SYSTEM_ARTIFACT_MODES = {"web", "document", "slides"}
DISCOVERY_INTERACTION_KINDS = {
    "quick_brief",
    "visual_direction_picker",
    "design_system_picker",
}


@dataclass(frozen=True)
class HomeTurnRoute:
    route_kind: str
    source: str
    confidence: float
    requires_plan_gate: bool
    requires_skill_selection: bool
    requires_design_system_selection: bool
    activity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Classifier = Callable[..., Awaitable[dict[str, Any]]]


def _artifact_mode(conversation: dict[str, Any]) -> str:
    return str(conversation.get("artifact_mode") or "web").strip().lower() or "web"


def _runtime_profile(conversation: dict[str, Any]) -> str:
    return str(conversation.get("runtime_profile") or "home").strip().lower() or "home"


def _is_plan_first_mode(conversation: dict[str, Any]) -> bool:
    if _runtime_profile(conversation) == "canvas":
        return False
    return _artifact_mode(conversation) in PLAN_FIRST_ARTIFACT_MODES


def _artifact_route(
    *,
    route_kind: str,
    source: str,
    confidence: float,
    conversation: dict[str, Any],
) -> HomeTurnRoute:
    requires_plan_gate = _is_plan_first_mode(conversation)
    return HomeTurnRoute(
        route_kind=route_kind,
        source=source,
        confidence=confidence,
        requires_plan_gate=requires_plan_gate,
        requires_skill_selection=requires_plan_gate and not bool(conversation.get("skill_id")),
        requires_design_system_selection=(
            requires_plan_gate
            and _artifact_mode(conversation) in DESIGN_SYSTEM_ARTIFACT_MODES
            and not bool(conversation.get("design_system_id"))
        ),
        activity="planning_outline" if requires_plan_gate else "executing",
    )


def informational_route(*, source: str = "deterministic_context", confidence: float = 1.0) -> HomeTurnRoute:
    return HomeTurnRoute(
        route_kind="informational_turn",
        source=source,
        confidence=confidence,
        requires_plan_gate=False,
        requires_skill_selection=False,
        requires_design_system_selection=False,
        activity="answering",
    )


def ui_action_route(*, activity: str = "executing") -> HomeTurnRoute:
    return HomeTurnRoute(
        route_kind="workflow_continuation",
        source="ui_action",
        confidence=1.0,
        requires_plan_gate=False,
        requires_skill_selection=False,
        requires_design_system_selection=False,
        activity=activity,
    )


def workflow_context_route(*, activity: str = "executing") -> HomeTurnRoute:
    return HomeTurnRoute(
        route_kind="workflow_continuation",
        source="deterministic_context",
        confidence=1.0,
        requires_plan_gate=False,
        requires_skill_selection=False,
        requires_design_system_selection=False,
        activity=activity,
    )


def canvas_bypass_route() -> HomeTurnRoute:
    return HomeTurnRoute(
        route_kind="workflow_continuation",
        source="canvas_bypass",
        confidence=1.0,
        requires_plan_gate=False,
        requires_skill_selection=False,
        requires_design_system_selection=False,
        activity="executing",
    )


def normalize_turn_route(raw: Any, *, conversation: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if isinstance(raw, HomeTurnRoute):
        return raw.to_dict()
    if not isinstance(raw, dict):
        return None
    route_kind = str(raw.get("route_kind") or "").strip()
    if route_kind not in HOME_TURN_ROUTE_LABELS:
        return None
    source = str(raw.get("source") or "deterministic_context").strip() or "deterministic_context"
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    conv = conversation or {}
    requires_plan_gate = bool(raw.get("requires_plan_gate"))
    if route_kind in {"artifact_creation", "artifact_revision"} and "requires_plan_gate" not in raw:
        requires_plan_gate = _is_plan_first_mode(conv)
    activity = str(raw.get("activity") or "").strip()
    if not activity:
        activity = "planning_outline" if requires_plan_gate else "answering" if route_kind == "informational_turn" else "executing"
    return {
        "route_kind": route_kind,
        "source": source,
        "confidence": max(0.0, min(1.0, confidence)),
        "requires_plan_gate": requires_plan_gate,
        "requires_skill_selection": bool(raw.get("requires_skill_selection")),
        "requires_design_system_selection": bool(raw.get("requires_design_system_selection")),
        "activity": activity,
    }


def route_from_ui_action(*, action_type: str | None = None) -> dict[str, Any]:
    action = str(action_type or "").strip().lower()
    if action in {"revise_plan", "plan_revision_requested"}:
        return ui_action_route(activity="planning_outline").to_dict()
    return ui_action_route(activity="executing").to_dict()


def _has_outline(conversation: dict[str, Any]) -> bool:
    if isinstance(conversation.get("plan_state"), dict):
        return True
    outline_runtime = conversation.get("outline_runtime")
    if isinstance(outline_runtime, dict) and isinstance(outline_runtime.get("current_outline"), dict):
        return True
    return False


def _should_default_classifier_failure_to_artifact(conversation: dict[str, Any]) -> bool:
    if not _is_plan_first_mode(conversation):
        return False
    return not bool(conversation.get("skill_id") or conversation.get("resolved_skill_id"))


def _classifier_failure_route(
    *,
    conversation: dict[str, Any],
    source: str,
) -> HomeTurnRoute:
    if _should_default_classifier_failure_to_artifact(conversation):
        route_kind = "artifact_revision" if _has_outline(conversation) else "artifact_creation"
        return _artifact_route(
            route_kind=route_kind,
            source=source,
            confidence=0.0,
            conversation=conversation,
        )
    return informational_route(source=source, confidence=0.0)


def route_after_interaction_submission(
    *,
    conversation: dict[str, Any],
    pending_interaction: dict[str, Any] | None,
) -> dict[str, Any]:
    """Route the run that resumes after the user submits an `/respond` answer.

    `/respond` only ever carries answers to pending interactions (discovery
    questionnaires, ask_user prompts) — it is **not** the plan-approval
    endpoint. Plan approval/revision go through `/plan/start` and
    `/plan/revise`. So discovery answers for plan-first artifact modes
    must continue into the plan-outline phase instead of jumping straight
    to executing.
    """
    if _runtime_profile(conversation) == "canvas":
        return canvas_bypass_route().to_dict()
    kind = str((pending_interaction or {}).get("kind") or "").strip().lower()
    phase = str(conversation.get("phase") or conversation.get("run_state") or "").strip().lower()
    if kind == "ask_user" and phase in {"planning", "revising_plan"}:
        if not _has_outline(conversation) and _is_plan_first_mode(conversation):
            return _artifact_route(
                route_kind="artifact_creation",
                source="interaction_submitted",
                confidence=1.0,
                conversation=conversation,
            ).to_dict()
        return ui_action_route(activity="planning_outline").to_dict()
    if (
        not _has_outline(conversation)
        and kind in DISCOVERY_INTERACTION_KINDS
        and _is_plan_first_mode(conversation)
    ):
        return _artifact_route(
            route_kind="artifact_creation",
            source="interaction_submitted",
            confidence=1.0,
            conversation=conversation,
        ).to_dict()
    return ui_action_route(activity="executing").to_dict()


async def route_home_text_turn(
    *,
    conversation: dict[str, Any],
    content: str,
    attachments: list[dict] | None = None,
    classifier: Classifier | None = None,
    user_id: int | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    model_name: str | None = None,
    provider_code: str | None = None,
    preflight_model_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    runtime_profile = str(conversation.get("runtime_profile") or "home").strip().lower()
    if runtime_profile == "canvas":
        return canvas_bypass_route().to_dict()

    pending_interaction = conversation.get("user_interaction")
    phase = str(conversation.get("phase") or "").strip().lower()
    runtime_status = str(conversation.get("runtime_status") or "").strip().lower()
    if isinstance(pending_interaction, dict) or runtime_status == "waiting_input" or phase in {"planning_ready", "awaiting_plan_review", "revising_plan"}:
        return workflow_context_route(activity="executing").to_dict()

    classifier_fn = classifier
    if classifier_fn is None:
        selected_model_name = model_name or get_default_multimodal_model()
        selected_provider_code = resolve_multimodal_provider(selected_model_name, provider_code)
        from app.services.agent_harness.prompt_runtime import classify_side_payload

        classifier_fn = classify_side_payload
    else:
        selected_model_name = model_name or get_default_multimodal_model()
        selected_provider_code = provider_code

    payload = {
        "task": "Route a home chat user message.",
        "user_message": str(content or ""),
        "artifact_mode": _artifact_mode(conversation),
        "has_active_plan": isinstance(conversation.get("plan_state"), dict),
        "has_skill": bool(conversation.get("skill_id") or conversation.get("resolved_skill_id")),
        "has_attachments": bool(attachments),
        "label_descriptions": {
            "informational_turn": (
                "The user wants an answer, explanation, lookup, search, analysis, "
                "or a one-shot generation such as a single image or a short video — "
                "anything that can be produced or returned in a single tool call "
                "without authoring a multi-section durable artifact."
            ),
            "artifact_creation": (
                "The user wants to author a multi-section durable artifact such as "
                "a website, document, spreadsheet, or slides — something that "
                "benefits from an outline / plan before generation. "
                "Single image or single video generation does NOT belong here; "
                "classify those as informational_turn."
            ),
            "artifact_revision": (
                "The user wants to modify an existing multi-section durable artifact "
                "(website, document, spreadsheet, or slides) or continue work on one. "
                "Re-generating or tweaking a single image or video is NOT a revision "
                "in this sense; classify those as informational_turn."
            ),
            "workflow_continuation": "The user is responding to an existing workflow prompt or continuing an already pending workflow.",
        },
    }
    classifier_timeout_seconds = float(settings.CLASSIFIER_TIMEOUT_SECONDS)
    try:
        result = await asyncio.wait_for(
            classifier_fn(
                label_space=HOME_TURN_ROUTE_LABELS,
                payload=payload,
                model_name=selected_model_name,
                provider_code=selected_provider_code,
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_id,
            ),
            timeout=classifier_timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "home turn classifier exceeded %.1fs; defaulting to informational route "
            "(conversation_id=%s, run_id=%s)",
            classifier_timeout_seconds,
            conversation_id,
            run_id,
        )
        return _classifier_failure_route(
            conversation=conversation,
            source="classifier_timeout_default",
        ).to_dict()
    except Exception:
        logger.debug("home turn classifier failed; defaulting from structured conversation state", exc_info=True)
        return _classifier_failure_route(
            conversation=conversation,
            source="classifier_failure_default",
        ).to_dict()

    model_call = result.get("_preflight_model_call") if isinstance(result, dict) else None
    if preflight_model_calls is not None and isinstance(model_call, dict):
        preflight_model_calls.append(model_call)

    label = str(result.get("label") or "").strip()
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if label not in HOME_TURN_ROUTE_LABELS:
        return informational_route(source="classifier", confidence=confidence).to_dict()
    if label == "informational_turn":
        return informational_route(source="classifier", confidence=confidence).to_dict()
    if label == "workflow_continuation":
        return HomeTurnRoute(
            route_kind="workflow_continuation",
            source="classifier",
            confidence=confidence,
            requires_plan_gate=False,
            requires_skill_selection=False,
            requires_design_system_selection=False,
            activity="executing",
        ).to_dict()
    return _artifact_route(
        route_kind=label,
        source="classifier",
        confidence=confidence,
        conversation=conversation,
    ).to_dict()
