"""Service orchestration for sending Harness conversation messages."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.harness import SendHarnessMessageRequest
from app.services.agent_harness.capabilities.skills.runtime_profiles import CANVAS_DEFAULT_SKILL_ID
from app.services.license_service import LicenseService

logger = logging.getLogger(__name__)

PLAN_FIRST_REQUIRED_SKILL_ARTIFACT_MODES = {"web", "document", "spreadsheet", "slides"}
REQUIRED_SKILL_ROUTE_SOURCES = {
    "classifier",
    "classifier_failure_default",
    "classifier_timeout_default",
    "classifier_unavailable_default",
    "deterministic_context",
}


def _safe_artifact_file_stem(value: str) -> str:
    stem = str(value or "").strip()
    if stem and all(ch.isalnum() or ch in ("-", "_") for ch in stem):
        return stem
    return sha256(stem.encode("utf-8")).hexdigest()


def _is_generation_artifact_available(conversation_dir: Path, artifact_ref: str) -> bool:
    normalized = str(artifact_ref or "").strip()
    if not normalized.startswith("artifact_ref:"):
        return False
    artifact_id = normalized.removeprefix("artifact_ref:")
    if not artifact_id or "/" in artifact_id or "\\" in artifact_id:
        return False
    artifact_path = conversation_dir / ".meta" / "generation_artifacts" / f"{_safe_artifact_file_stem(artifact_id)}.json"
    return artifact_path.exists()


def should_auto_resolve_main_skill(
    *,
    conversation: dict[str, Any],
    effective_skill_selection_mode: str,
    explicit_request_skill_id: bool,
    turn_route: dict[str, Any],
) -> bool:
    return (
        not conversation.get("skill_id")
        and str(effective_skill_selection_mode or "").strip().lower() == "auto"
        and not explicit_request_skill_id
        and bool(turn_route.get("requires_skill_selection"))
    )


@dataclass(frozen=True)
class HarnessSendMessageDependencies:
    get_request_language: Callable[[Request], str]
    validate_harness_skill_id: Callable[[Any], str | None]
    selection_source: Callable[..., str]
    rederive_harness_phase: Callable[[dict[str, Any]], str]
    clear_internal_hidden_skill_activation_state: Callable[..., None]
    validate_artifact_mode: Callable[[Any], str]
    validate_design_system_id: Callable[[Any], str | None]
    phase_diagnostic_payload: Callable[..., dict[str, Any]]
    require_canvas_project_access: Callable[..., Awaitable[Any]]
    build_live_streaming_response: Callable[..., Any]
    latched_internal_hidden_skill_ids: Callable[..., tuple[bool, list[str]]]
    persist_internal_hidden_skill_activation: Callable[..., None]

async def send_harness_message(
    conversation_id: str,
    data: SendHarnessMessageRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    deps: HarnessSendMessageDependencies,
    after_sequence: int | None = None,
):
    """Send a user message and stream the harness agent response via SSE."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
        update_conversation as update_conv,
    )
    from app.services.agent_harness.agent_run.control.active_run_guard import has_active_agent_run
    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    runtime_profile = str(conv.get("runtime_profile") or "home").strip().lower() or "home"
    if runtime_profile != "canvas":
        await LicenseService(db).ensure_capability("home_agent")
    lang = deps.get_request_language(request)
    if has_active_agent_run(conversation_id):
        raise HTTPException(status_code=409, detail="Conversation already has an active run")
    previous_skill_id = str(conv.get("skill_id") or "").strip() or None
    existing_messages_count: int | None = None

    def _conversation_has_persisted_messages() -> bool:
        nonlocal existing_messages_count
        if existing_messages_count is None:
            from app.services.agent_harness.workspace.session_v2.service import message_count as v2_message_count

            projected_count = v2_message_count(user.id, conversation_id)
            if projected_count is not None:
                existing_messages_count = projected_count
                return existing_messages_count > 0
            from app.services.agent_harness.workspace.conversation.conversation_service import load_messages

            existing_messages_count = len(load_messages(user.id, conversation_id))
        return existing_messages_count > 0

    def _clear_stale_plan_state_for_initial_turn() -> None:
        plan_state = conv.get("plan_state")
        if not plan_state:
            return
        if _conversation_has_persisted_messages():
            return
        runtime_status = str(conv.get("runtime_status") or "").strip().lower()
        run_state = str(conv.get("run_state") or "").strip().lower()
        if runtime_status not in {"", "idle"} or run_state not in {"", "idle"}:
            return
        outline_runtime = conv.get("outline_runtime") if isinstance(conv.get("outline_runtime"), dict) else {}
        current_outline = outline_runtime.get("current_outline") if isinstance(outline_runtime, dict) else None
        if isinstance(current_outline, dict) and current_outline:
            return
        next_phase = deps.rederive_harness_phase({
            **conv,
            "plan_state": None,
        })
        update_conv(
            user.id,
            conversation_id,
            plan_state=None,
            phase=next_phase,
        )
        conv["plan_state"] = None
        conv["phase"] = next_phase

    _clear_stale_plan_state_for_initial_turn()

    def _artifact_mode_for_skill(skill_id: str | None) -> str | None:
        normalized = str(skill_id or "").strip()
        if not normalized:
            return None
        try:
            from app.services.agent_harness.catalog import get_skill_summary_sync

            skill = get_skill_summary_sync(normalized)
        except Exception:
            logger.debug("Failed to resolve artifact mode for skill %s", normalized, exc_info=True)
            return None
        artifact_mode = str(getattr(skill, "artifact_mode", "") or "").strip().lower() if skill is not None else ""
        return artifact_mode or None

    if "skill_id" in getattr(data, "model_fields_set", set()):
        requested_skill_id = deps.validate_harness_skill_id(data.skill_id)
        if runtime_profile == "canvas" and requested_skill_id is None:
            next_skill_id = deps.validate_harness_skill_id(conv.get("skill_id")) or CANVAS_DEFAULT_SKILL_ID
        else:
            next_skill_id = requested_skill_id
        next_skill_selection_mode = data.skill_selection_mode or conv.get("skill_selection_mode") or ("manual" if next_skill_id else "auto")
        if runtime_profile == "canvas" and requested_skill_id:
            next_skill_selection_mode = "manual"
        next_skill_source = deps.selection_source(
            next_skill_selection_mode,
            next_skill_id,
            manual_source="user_selected",
            auto_source="ai_resolved",
        )
        next_phase = deps.rederive_harness_phase({
            **conv,
            "skill_id": next_skill_id,
            "resolved_skill_id": next_skill_id,
            "skill_selection_mode": next_skill_selection_mode,
            "skill_resolution_source": next_skill_source,
        })
        if (
            conv.get("skill_id") != next_skill_id
            or conv.get("skill_selection_mode") != next_skill_selection_mode
            or conv.get("skill_resolution_source") != next_skill_source
            or conv.get("last_skill_decision_reason") != data.skill_decision_reason
            or conv.get("last_skill_decision_confidence") != data.skill_decision_confidence
            or conv.get("phase") != next_phase
        ):
            update_conv(
                user.id,
                conversation_id,
                skill_id=next_skill_id,
                resolved_skill_id=next_skill_id,
                skill_resolution_source=next_skill_source,
                skill_selection_mode=next_skill_selection_mode,
                phase=next_phase,
                last_skill_decision_reason=data.skill_decision_reason,
                last_skill_decision_confidence=data.skill_decision_confidence,
            )
            conv["skill_id"] = next_skill_id
            conv["resolved_skill_id"] = next_skill_id
            conv["skill_resolution_source"] = next_skill_source
            conv["skill_selection_mode"] = next_skill_selection_mode
            conv["phase"] = next_phase
            conv["last_skill_decision_reason"] = data.skill_decision_reason
            conv["last_skill_decision_confidence"] = data.skill_decision_confidence
        if next_skill_id is None:
            deps.clear_internal_hidden_skill_activation_state(
                user_id=user.id,
                conversation_id=conversation_id,
                conversation=conv,
            )
        if next_skill_selection_mode == "auto" and next_skill_id:
            from app.services.agent_harness.workspace.conversation.conversation_service import (
                build_auto_selection_announcement_message,
            )

            announcement_previous_skill_id = previous_skill_id
            if announcement_previous_skill_id == next_skill_id and not _conversation_has_persisted_messages():
                announcement_previous_skill_id = None

            pending_message = build_auto_selection_announcement_message(
                previous_skill_id=announcement_previous_skill_id,
                next_skill_id=next_skill_id,
                language=lang,
            )
            if pending_message:
                conv["_pending_auto_selection_announcement_message"] = pending_message
            previous_skill_id = next_skill_id

    canvas_skill_artifact_mode: str | None = None
    if runtime_profile == "canvas":
        canvas_skill_artifact_mode = _artifact_mode_for_skill(conv.get("skill_id") or conv.get("resolved_skill_id"))

    if "skill_selection_mode" in getattr(data, "model_fields_set", set()) and "skill_id" not in getattr(data, "model_fields_set", set()):
        next_skill_selection_mode = data.skill_selection_mode or "auto"
        resetting_to_auto = (
            runtime_profile != "canvas"
            and next_skill_selection_mode == "auto"
            and str(conv.get("skill_selection_mode") or "").strip().lower() != "auto"
        )
        next_skill_id = None if resetting_to_auto else conv.get("skill_id")
        next_resolved_skill_id = None if resetting_to_auto else conv.get("resolved_skill_id")
        next_skill_source = deps.selection_source(
            next_skill_selection_mode,
            next_skill_id,
            manual_source="user_selected",
            auto_source="ai_resolved",
        )
        if (
            conv.get("skill_selection_mode") != next_skill_selection_mode
            or conv.get("skill_resolution_source") != next_skill_source
            or conv.get("skill_id") != next_skill_id
            or conv.get("resolved_skill_id") != next_resolved_skill_id
        ):
            update_conv(
                user.id,
                conversation_id,
                skill_id=next_skill_id,
                resolved_skill_id=next_resolved_skill_id,
                skill_selection_mode=next_skill_selection_mode,
                skill_resolution_source=next_skill_source,
            )
            conv["skill_id"] = next_skill_id
            conv["resolved_skill_id"] = next_resolved_skill_id
            conv["skill_selection_mode"] = next_skill_selection_mode
            conv["skill_resolution_source"] = next_skill_source
        if resetting_to_auto:
            deps.clear_internal_hidden_skill_activation_state(
                user_id=user.id,
                conversation_id=conversation_id,
                conversation=conv,
            )

    if runtime_profile == "canvas":
        def _existing_canvas_skill_id(raw_skill_id: Any) -> str | None:
            try:
                return deps.validate_harness_skill_id(raw_skill_id)
            except HTTPException:
                return None

        existing_canvas_skill_id = (
            _existing_canvas_skill_id(conv.get("skill_id"))
            or _existing_canvas_skill_id(conv.get("resolved_skill_id"))
        )
        canvas_skill_id = existing_canvas_skill_id or CANVAS_DEFAULT_SKILL_ID
        canvas_skill_selection_mode = str(
            conv.get("skill_selection_mode") if existing_canvas_skill_id else "auto"
        ).strip().lower() or ("manual" if existing_canvas_skill_id else "auto")
        canvas_skill_source = deps.selection_source(
            canvas_skill_selection_mode,
            canvas_skill_id,
            manual_source="user_selected",
            auto_source="ai_resolved",
        )
        next_phase = deps.rederive_harness_phase({
            **conv,
            "skill_id": canvas_skill_id,
            "resolved_skill_id": canvas_skill_id,
            "skill_selection_mode": canvas_skill_selection_mode,
            "skill_resolution_source": canvas_skill_source,
        })
        if (
            conv.get("skill_id") != canvas_skill_id
            or conv.get("resolved_skill_id") != canvas_skill_id
            or conv.get("skill_selection_mode") != canvas_skill_selection_mode
            or conv.get("skill_resolution_source") != canvas_skill_source
            or conv.get("phase") != next_phase
        ):
            update_conv(
                user.id,
                conversation_id,
                skill_id=canvas_skill_id,
                resolved_skill_id=canvas_skill_id,
                skill_selection_mode=canvas_skill_selection_mode,
                skill_resolution_source=canvas_skill_source,
                phase=next_phase,
            )
            conv["skill_id"] = canvas_skill_id
            conv["resolved_skill_id"] = canvas_skill_id
            conv["skill_selection_mode"] = canvas_skill_selection_mode
            conv["skill_resolution_source"] = canvas_skill_source
            conv["phase"] = next_phase

    if "artifact_mode" in getattr(data, "model_fields_set", set()):
        next_artifact_mode = deps.validate_artifact_mode(data.artifact_mode)
        if runtime_profile == "canvas" and canvas_skill_artifact_mode:
            next_artifact_mode = canvas_skill_artifact_mode
        if conv.get("artifact_mode") != next_artifact_mode:
            next_phase = deps.rederive_harness_phase({
                **conv,
                "artifact_mode": next_artifact_mode,
            })
            update_conv(user.id, conversation_id, artifact_mode=next_artifact_mode, phase=next_phase)
            conv["artifact_mode"] = next_artifact_mode
            conv["phase"] = next_phase
    elif runtime_profile == "canvas" and canvas_skill_artifact_mode and conv.get("artifact_mode") != canvas_skill_artifact_mode:
        next_phase = deps.rederive_harness_phase({
            **conv,
            "artifact_mode": canvas_skill_artifact_mode,
        })
        update_conv(user.id, conversation_id, artifact_mode=canvas_skill_artifact_mode, phase=next_phase)
        conv["artifact_mode"] = canvas_skill_artifact_mode
        conv["phase"] = next_phase

    if "design_system_id" in getattr(data, "model_fields_set", set()):
        next_design_system_id = deps.validate_design_system_id(data.design_system_id)
        if conv.get("design_system_id") != next_design_system_id:
            update_conv(
                user.id,
                conversation_id,
                design_system_id=next_design_system_id,
            )
            conv["design_system_id"] = next_design_system_id

    # Merge per-message model preferences into conversation metadata
    if data.model_preferences:
        update_conv(user.id, conversation_id, model_preferences=data.model_preferences)
        conv["model_preferences"] = data.model_preferences

    request_fields = getattr(data, "model_fields_set", set())
    effective_skill_selection_mode = str(
        data.skill_selection_mode
        or conv.get("skill_selection_mode")
        or ("manual" if conv.get("skill_id") else "auto")
    ).strip().lower()
    effective_artifact_mode = str(conv.get("artifact_mode") or data.artifact_mode or "web")
    explicit_request_skill_id = (
        "skill_id" in request_fields
        and deps.validate_harness_skill_id(data.skill_id) is not None
    )
    home_turn_router_model_calls: list[dict[str, Any]] = []

    def _selected_multimodal_model() -> str | None:
        preferences = data.model_preferences or conv.get("model_preferences")
        if not isinstance(preferences, dict):
            return None
        return str(preferences.get("multimodal_model") or "").strip() or None

    def _selected_multimodal_provider() -> str | None:
        preferences = data.model_preferences or conv.get("model_preferences")
        if not isinstance(preferences, dict):
            return None
        return str(preferences.get("multimodal_provider") or "").strip() or None

    from app.services.agent_harness.workspace.conversation.home_turn_router import (
        canvas_bypass_route,
        route_from_ui_action,
        route_home_text_turn,
    )

    input_kind = str(getattr(data, "input_kind", "user_text_message") or "user_text_message").strip()
    if runtime_profile == "canvas":
        turn_route = canvas_bypass_route().to_dict()
    elif input_kind == "user_ui_action":
        turn_route = route_from_ui_action(action_type=getattr(data, "action_type", None))
    else:
        turn_route = await route_home_text_turn(
            conversation=conv,
            content=data.content,
            attachments=data.attachments,
            user_id=user.id,
            conversation_id=conversation_id,
            run_id=str(conv.get("run_id") or ""),
            model_name=_selected_multimodal_model(),
            provider_code=_selected_multimodal_provider(),
            preflight_model_calls=home_turn_router_model_calls,
        )
    if conv.get("turn_route") != turn_route or conv.get("activity") != turn_route.get("activity"):
        update_conv(
            user.id,
            conversation_id,
            turn_route=turn_route,
            activity=turn_route.get("activity"),
        )
        conv["turn_route"] = turn_route
        conv["activity"] = turn_route.get("activity")

    should_auto_resolve_skill = should_auto_resolve_main_skill(
        conversation=conv,
        effective_skill_selection_mode=effective_skill_selection_mode,
        explicit_request_skill_id=explicit_request_skill_id,
        turn_route=turn_route,
    )
    is_initial_auto_selection = (
        should_auto_resolve_skill
        and not bool(conv.get("skill_id") or conv.get("resolved_skill_id"))
    )
    requires_defaultable_plan_skill = (
        should_auto_resolve_skill
        and str(turn_route.get("source") or "").strip() in REQUIRED_SKILL_ROUTE_SOURCES
        and str(turn_route.get("activity") or "").strip() == "planning_outline"
        and bool(turn_route.get("requires_plan_gate"))
        and effective_artifact_mode in PLAN_FIRST_REQUIRED_SKILL_ARTIFACT_MODES
    )

    def _default_required_plan_skill_id() -> str | None:
        from app.services.agent_harness.capabilities.skills.policy_registry import (
            default_skill_id_for_artifact_mode,
        )
        from app.services.agent_harness.catalog import get_skill_summary_sync, list_skill_summaries_sync

        default_skill_id = default_skill_id_for_artifact_mode(effective_artifact_mode)
        if not default_skill_id:
            return None
        skill = get_skill_summary_sync(default_skill_id)
        if skill is None or str(skill.artifact_mode or "").strip().lower() != effective_artifact_mode:
            return None
        selectable_ids = {
            str(candidate.id)
            for candidate in list_skill_summaries_sync()
            if str(candidate.artifact_mode or "").strip().lower() == effective_artifact_mode
            and candidate.capabilities.get("phase_enabled") is not False
            and candidate.capabilities.get("selection_enabled") is not False
        }
        if default_skill_id not in selectable_ids:
            return None
        return default_skill_id

    def _apply_resolved_skill_state(
        *,
        resolved_skill_id: str,
        source: str,
        reason: str | None,
        confidence: float | None,
    ) -> str:
        next_phase = deps.rederive_harness_phase({
            **conv,
            "skill_id": resolved_skill_id,
            "resolved_skill_id": resolved_skill_id,
            "skill_resolution_source": source,
            "skill_selection_mode": "auto",
            "last_skill_decision_reason": reason,
            "last_skill_decision_confidence": confidence,
        })
        update_conv(
            user.id,
            conversation_id,
            skill_id=resolved_skill_id,
            resolved_skill_id=resolved_skill_id,
            skill_resolution_source=source,
            skill_selection_mode="auto",
            last_skill_decision_reason=reason,
            last_skill_decision_confidence=confidence,
            phase=next_phase,
        )
        conv["skill_id"] = resolved_skill_id
        conv["resolved_skill_id"] = resolved_skill_id
        conv["skill_resolution_source"] = source
        conv["skill_selection_mode"] = "auto"
        conv["last_skill_decision_reason"] = reason
        conv["last_skill_decision_confidence"] = confidence
        conv["phase"] = next_phase
        return next_phase

    def _publish_skill_selection_resolved_event(
        *,
        resolved_skill_id: str,
        source: str,
        reason: str | None,
        confidence: float | None,
        phase: str | None,
    ) -> None:
        try:
            from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event

            publish_user_event(
                user.id,
                conversation_id,
                run_id=str(conv.get("run_id") or "preflight"),
                event_type="selection_resolved",
                data={
                    "skill_id": resolved_skill_id,
                    "resolved_skill_id": resolved_skill_id,
                    "skill_selection_mode": "auto",
                    "skill_resolution_source": source,
                    "artifact_mode": effective_artifact_mode,
                    "last_skill_decision_reason": reason,
                    "last_skill_decision_confidence": confidence,
                    "phase": phase,
                },
            )
        except Exception:
            logger.debug("Failed to publish skill selection event", exc_info=True)

    async def _record_preflight_model_calls(preflight_model_calls) -> None:
        from app.services.agent_harness.workspace.conversation.turns.preflight_billing import (
            record_turn_preflight_model_calls,
        )
        from app.services.agent_harness.workspace.conversation.turns.turn_preparation import (
            build_turn_idempotency_key,
        )

        # Build the dedup key from the *early* inputs available at preflight
        # time. The final enqueue idempotency key contains more fields but
        # this subset is stable across client retries of the same logical
        # turn, which is all we need to prevent duplicate preflight charges.
        preflight_idempotency_key = build_turn_idempotency_key(
            "preflight_message",
            conversation_id,
            data.content,
            data.attachments,
            data.skill_id,
            effective_artifact_mode,
        )
        parent_usage_log_id = await record_turn_preflight_model_calls(
            user_id=user.id,
            conversation=conv,
            artifact_mode=effective_artifact_mode,
            run_id=str(conv.get("run_id") or "preflight"),
            preflight_model_calls=list(preflight_model_calls or []),
            turn_idempotency_key=preflight_idempotency_key,
        )
        if parent_usage_log_id is not None:
            update_conv(user.id, conversation_id, parent_usage_log_id=parent_usage_log_id)
            conv["parent_usage_log_id"] = parent_usage_log_id

    async def _resolve_internal_hidden_skills(selected_skill_id: str) -> list[Any]:
        from app.services.agent_harness.authoring.planning.decision_resolver import resolve_selection

        if runtime_profile == "canvas":
            return []
        try:
            latched, _latched_ids = deps.latched_internal_hidden_skill_ids(
                user_id=user.id,
                conversation_id=conversation_id,
                conversation=conv,
                selected_skill_id=selected_skill_id,
            )
        except Exception:
            latched = False
        if latched:
            return []
        helper_result = await resolve_selection(
            artifact_mode=effective_artifact_mode,
            prompt=data.content,
            attachments=data.attachments,
            current_skill_id=selected_skill_id,
            resolve_skill=False,
            model_preferences=data.model_preferences or conv.get("model_preferences") or {},
            user_id=user.id,
            conversation_id=conversation_id,
            run_id=str(conv.get("run_id") or "preflight"),
        )
        internal_skill_ids = list(getattr(helper_result, "internal_skill_ids", None) or [])
        if internal_skill_ids:
            deps.persist_internal_hidden_skill_activation(
                user_id=user.id,
                conversation_id=conversation_id,
                conversation=conv,
                selected_skill_id=selected_skill_id,
                internal_skill_ids=internal_skill_ids,
                language=lang,
            )
        return list(getattr(helper_result, "preflight_model_calls", None) or [])

    selection_preflight_model_calls: list[Any] = []
    selected_skill_for_helper = str(conv.get("skill_id") or conv.get("resolved_skill_id") or "").strip() or None
    if should_auto_resolve_skill:
        from app.services.agent_harness.authoring.planning.decision_resolver import resolve_selection

        selection_result = await resolve_selection(
            artifact_mode=effective_artifact_mode,
            prompt=data.content,
            attachments=data.attachments,
            current_skill_id=conv.get("skill_id"),
            resolve_skill=True,
            model_preferences=data.model_preferences or conv.get("model_preferences") or {},
            user_id=user.id,
            conversation_id=conversation_id,
            run_id=str(conv.get("run_id") or "preflight"),
        )
        selection_preflight_model_calls = list(getattr(selection_result, "preflight_model_calls", None) or [])
        skill_decision = getattr(selection_result, "skill", None)
        selected_skill_id = str(getattr(skill_decision, "id", "") or "").strip() or None
        should_replace_current = bool(getattr(skill_decision, "should_replace_current", False))
        if selected_skill_id and (not conv.get("skill_id") or should_replace_current):
            selected_phase = _apply_resolved_skill_state(
                resolved_skill_id=selected_skill_id,
                source="ai_resolved",
                reason=getattr(skill_decision, "reasoning_summary", None),
                confidence=getattr(skill_decision, "confidence", None),
            )
            _publish_skill_selection_resolved_event(
                resolved_skill_id=selected_skill_id,
                source="ai_resolved",
                reason=getattr(skill_decision, "reasoning_summary", None),
                confidence=getattr(skill_decision, "confidence", None),
                phase=selected_phase,
            )
            try:
                from app.services.agent_harness.workspace.conversation.conversation_service import (
                    build_auto_selection_announcement_message,
                )

                pending_message = build_auto_selection_announcement_message(
                    previous_skill_id=previous_skill_id,
                    next_skill_id=selected_skill_id,
                    language=lang,
                )
                if pending_message:
                    conv["_pending_auto_selection_announcement_message"] = pending_message
            except Exception:
                logger.debug("Failed to build auto-selection announcement", exc_info=True)
            try:
                deps.persist_internal_hidden_skill_activation(
                    user_id=user.id,
                    conversation_id=conversation_id,
                    conversation=conv,
                    selected_skill_id=selected_skill_id,
                    internal_skill_ids=list(getattr(selection_result, "internal_skill_ids", None) or []),
                    language=lang,
                )
            except Exception:
                logger.debug("Failed to persist internal hidden skill activation", exc_info=True)
            selected_skill_for_helper = selected_skill_id
        elif requires_defaultable_plan_skill:
            default_skill_id = _default_required_plan_skill_id()
            if default_skill_id:
                selected_phase = _apply_resolved_skill_state(
                    resolved_skill_id=default_skill_id,
                    source="deterministic_default",
                    reason="Default skill required for plan-first artifact mode.",
                    confidence=1.0,
                )
                _publish_skill_selection_resolved_event(
                    resolved_skill_id=default_skill_id,
                    source="deterministic_default",
                    reason="Default skill required for plan-first artifact mode.",
                    confidence=1.0,
                    phase=selected_phase,
                )
                selected_skill_for_helper = default_skill_id

    preflight_failure: BaseException | None = None
    if selected_skill_for_helper:
        try:
            selection_preflight_model_calls.extend(await _resolve_internal_hidden_skills(selected_skill_for_helper))
        except Exception as exc:
            preflight_failure = exc

    if runtime_profile != "canvas":
        await _record_preflight_model_calls([*home_turn_router_model_calls, *selection_preflight_model_calls])

    if conv.get("web_search_enabled") != data.web_search_enabled:
        update_conv(user.id, conversation_id, web_search_enabled=data.web_search_enabled)
        conv["web_search_enabled"] = data.web_search_enabled
    if conv.get("language") != lang:
        update_conv(user.id, conversation_id, language=lang)
        conv["language"] = lang

    derived_phase = deps.rederive_harness_phase(conv)
    if conv.get("phase") != derived_phase:
        update_conv(user.id, conversation_id, phase=derived_phase)
        conv["phase"] = derived_phase

    try:
        from app.services.agent_harness.runtime.eventing.persistence import append_trace

        append_trace(
            user.id,
            conversation_id,
            trace_type="send_message_phase_diagnostic",
            phase=str(conv.get("phase")) if conv.get("phase") else None,
            run_status=str(conv.get("runtime_status")) if conv.get("runtime_status") else None,
            summary="send_message phase diagnostic",
            payload=deps.phase_diagnostic_payload(
                conv,
                source="send_message.before_start_run",
                derived_phase=derived_phase,
                request_fields=getattr(data, "model_fields_set", set()),
                extra={
                    "effective_artifact_mode": effective_artifact_mode,
                    "effective_skill_selection_mode": effective_skill_selection_mode,
                    "is_initial_auto_selection": is_initial_auto_selection,
                    "should_auto_resolve_skill": should_auto_resolve_skill,
                    "turn_route": turn_route,
                    "input_kind": input_kind,
                    "existing_messages_count": existing_messages_count,
                },
            ),
        )
    except Exception:
        logger.debug("Failed to append send_message phase diagnostic trace", exc_info=True)

    attachments = data.attachments
    from app.services.agent_harness.references import InvalidMessageReferenceError, resolve_message_references

    has_structured_references = isinstance(data.references, list) and len(data.references) > 0
    message_references: list[dict[str, Any]] = []
    if runtime_profile != "canvas":
        try:
            message_references = resolve_message_references(
                data.references,
                attachments=attachments,
            )
        except InvalidMessageReferenceError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    base_file_versions = [
        {
            "file_id": item.file_id,
            "version_id": item.version_id or "current",
            "name": item.name or item.file_id,
        }
        for item in (data.base_file_versions or [])
    ]
    hidden_user_context = None
    if data.base_file_versions:
        version_lines = [
            (
                f"- {item.name or item.file_id}: file_id={item.file_id}, "
                f"version_id={item.version_id or 'current'}"
            )
            for item in data.base_file_versions
        ]
        hidden_user_context = (
            "Base file versions selected by the user. To edit them, call "
            "workspace_file(action='prepare_edit') with the listed file_id/version_id, modify the returned "
            "output_path, validate it, then publish with workspace_file(action='publish_edit'):\n"
            + "\n".join(version_lines)
        )
    if runtime_profile == "canvas":
        project_id = conv.get("project_id")
        if project_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Canvas harness conversation is missing project_id",
            )
        project = await deps.require_canvas_project_access(db, user_id=user.id, project_id=int(project_id))
        from app.services.agent_harness.canvas import load_canvas_items, parse_canvas_references
        from app.services.canvas_media_rehost_service import CanvasMediaRehostService

        media_rehost = CanvasMediaRehostService(db)
        attachments, references = await _rehost_canvas_message_media(
            attachments,
            data.references,
            media_rehost=media_rehost,
            project_id=int(project_id),
            user_id=user.id,
        )

        canvas_items = await load_canvas_items(db, project=project, user_id=user.id)
        from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir

        conversation_dir = get_conversation_dir(
            user.id,
            conversation_id,
            runtime_profile=runtime_profile,
            project_id=int(project_id),
        )
        try:
            message_references = resolve_message_references(
                references,
                attachments=attachments,
                canvas_items=canvas_items,
                project_id=int(project_id),
                content=data.content,
                is_artifact_reference_available=lambda artifact_ref: _is_generation_artifact_available(
                    conversation_dir,
                    artifact_ref,
                ),
            )
        except InvalidMessageReferenceError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if has_structured_references:
            parsed_refs = None
        else:
            parsed_refs = parse_canvas_references(
                data.content,
                canvas_items,
                language=lang,
            )
        if parsed_refs is None:
            canvas_hidden_context = ""
        else:
            canvas_prompt_contract = (
                "Canvas runtime rules:\n"
                "- The user may reference canvas media with @[name](canvas:itemId).\n"
                "- The user may reference a local marked region with #[label](canvas-mark:markId:image:itemId:x:rx:y:ry).\n"
                "- If the referenced media was generated earlier in this conversation, pass its artifact_ref to downstream tools instead of copying a generated URL.\n"
                "- For user uploads, external media, or existing local assets, pass the referenced URL or path required by the target tool.\n"
                "- When generating video from referenced media, follow generate_video.input exactly: use input.frames.first_image_url for frame-driven generation, or input.references.image_urls for reference-image generation; reference video and reference audio are not supported in this version.\n"
                "- When a mark is referenced, treat it as a local edit target on the referenced source image.\n"
                "- Image/video generation results in this conversation will be inserted back into the canvas automatically.\n"
            )
            plain_text_hint = parsed_refs.cleaned_content.strip()
            canvas_context_parts = [canvas_prompt_contract]
            if plain_text_hint and plain_text_hint != str(data.content or "").strip():
                canvas_context_parts.append(f"Plain-text user intent after stripping canvas references:\n{plain_text_hint}")
            if parsed_refs.prompt_context:
                canvas_context_parts.append(parsed_refs.prompt_context)
            canvas_hidden_context = "\n\n".join(part for part in canvas_context_parts if part)
        if canvas_hidden_context:
            hidden_user_context = (
                f"{hidden_user_context}\n\n{canvas_hidden_context}"
                if hidden_user_context
                else canvas_hidden_context
            )
    web_search_enabled = data.web_search_enabled
    user_message_metadata: dict[str, object] = {}
    if base_file_versions:
        user_message_metadata["base_file_versions"] = base_file_versions
    if message_references:
        user_message_metadata["references"] = message_references
        user_message_metadata["reference_diagnostics"] = _reference_diagnostics(message_references)
    active_user_skill_id = str(
        data.skill_id
        or conv.get("skill_id")
        or conv.get("resolved_skill_id")
        or "",
    ).strip()
    if active_user_skill_id:
        user_message_metadata["skill_id"] = active_user_skill_id
    if hidden_user_context:
        user_message_metadata["hidden_user_context"] = {
            "custom_lanes": [{"type": "context", "text": hidden_user_context}]
        }

    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_message_run
    from app.services.agent_harness.agent_coordination.run_wakeup_bus import wake_agent_run_worker
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.workspace.conversation.turns.message_turn import prepare_message_run_payload
    from app.services.agent_harness.workspace.conversation.turns.turn_preparation import build_turn_idempotency_key

    user_message_payload = {
        "id": uuid.uuid4().hex[:8],
        "role": "user",
        "content": data.content,
        "attachments": attachments or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if user_message_metadata:
        user_message_payload["metadata"] = user_message_metadata
    user_message_event_payload = {
        "id": user_message_payload["id"],
        "role": "user",
        "content": data.content,
        "attachments": attachments or [],
        "created_at": user_message_payload["created_at"],
    }
    if user_message_metadata:
        user_message_event_payload["metadata"] = user_message_metadata
    if base_file_versions:
        user_message_event_payload["base_file_versions"] = base_file_versions
    if preflight_failure is not None:
        error_summary = str(preflight_failure) or preflight_failure.__class__.__name__
        run_id = str(conv.get("run_id") or f"preflight-{conversation_id}")
        update_conv(
            user.id,
            conversation_id,
            runtime_status="failed",
            run_state="failed",
            turn_status="failed",
            last_error_summary=error_summary,
        )
        conv["runtime_status"] = "failed"
        conv["run_state"] = "failed"
        conv["turn_status"] = "failed"
        conv["last_error_summary"] = error_summary
        try:
            from app.services.agent_harness.runtime.eventing.event_log import append_event
            from app.services.agent_harness.runtime.eventing.turn_protocol import (
                TURN_COMPLETED,
                build_turn_completed_payload,
                build_turn_error,
            )

            runtime_snapshot = {
                "runtime_status": "failed",
                "run_state": "failed",
                "turn_status": "failed",
                "last_error_summary": error_summary,
                "failure": {"error_type": "PreflightFailed", "summary": error_summary},
            }
            append_event(
                user.id,
                conversation_id,
                run_id=run_id,
                event_type="user_message",
                data=user_message_event_payload,
                lane="user",
                idempotency_key=f"run:{run_id}:preflight-user-message",
            )
            append_event(
                user.id,
                conversation_id,
                run_id=run_id,
                event_type="message_error",
                data={
                    "message": error_summary,
                    "failure": {
                        "error_type": "PreflightFailed",
                        "summary": error_summary,
                        "user_visible": True,
                    },
                },
                lane="user",
                idempotency_key=f"run:{run_id}:preflight-message-error",
            )
            append_event(
                user.id,
                conversation_id,
                run_id=run_id,
                event_type=TURN_COMPLETED,
                data=build_turn_completed_payload(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    status="failed",
                    runtime_snapshot=runtime_snapshot,
                    error=build_turn_error("PreflightFailed", error_summary),
                ),
                lane="user",
                idempotency_key=f"run:{run_id}:turn-completed",
            )
        except Exception:
            logger.debug("Failed to append preflight failure event", exc_info=True)
        return deps.build_live_streaming_response(
            user.id,
            conversation_id,
            after_sequence=after_sequence,
            run_id=run_id,
            request_id=None,
        )

    try:
        run_request = await enqueue_message_run(
            user_id=user.id,
            conversation_id=conversation_id,
            payload=prepare_message_run_payload(
                content=data.content,
                attachments=attachments or [],
                base_file_versions=base_file_versions,
                hidden_user_context=hidden_user_context,
                user_message_metadata=user_message_metadata,
                user_message_event=user_message_event_payload,
                language=lang,
                web_search_enabled=web_search_enabled,
                model_preferences=data.model_preferences or conv.get("model_preferences") or {},
                effective_artifact_mode=effective_artifact_mode,
                turn_route=turn_route,
                skill_selection={
                    "requested_skill_id": data.skill_id,
                    "mode": effective_skill_selection_mode,
                    "should_auto_resolve_skill": should_auto_resolve_skill,
                    "requires_defaultable_plan_skill": requires_defaultable_plan_skill,
                },
                canvas={
                    "project_id": conv.get("project_id"),
                    "references": message_references or [],
                },
            ),
            idempotency_key=build_turn_idempotency_key(
                "message",
                conversation_id,
                data.content,
                attachments or [],
                base_file_versions,
                message_references or [],
                user_message_metadata,
            ),
            parent_usage_log_id=(
                None
                if runtime_profile == "canvas"
                else conv.get("parent_usage_log_id") if isinstance(conv.get("parent_usage_log_id"), int) else None
            ),
            parent_billing_conversation=conv if runtime_profile == "canvas" else None,
            wake_worker=False,
        )
    except AgentRunAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail="Conversation already has an active run") from exc

    await wake_agent_run_worker()

    return deps.build_live_streaming_response(
        user.id,
        conversation_id,
        after_sequence=after_sequence,
        run_id=run_request.run_id,
        request_id=run_request.id,
    )


def _reference_diagnostics(references: list[dict[str, Any]]) -> dict[str, Any]:
    ids: list[str] = []
    kinds: dict[str, int] = {}
    for reference in references:
        if not isinstance(reference, dict):
            continue
        reference_id = str(reference.get("id") or "").strip()
        if reference_id:
            ids.append(reference_id)
        kind = str(reference.get("kind") or "unknown").strip() or "unknown"
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"count": len(ids), "ids": ids, "kinds": kinds}


async def _rehost_canvas_message_media(
    attachments: Any,
    references: Any,
    *,
    media_rehost: Any,
    project_id: int,
    user_id: int,
) -> tuple[Any, Any]:
    if not isinstance(attachments, list):
        return attachments, references

    changed = False
    next_attachments: list[Any] = []
    copied_by_url: dict[str, str] = {}
    for attachment in attachments:
        if not isinstance(attachment, dict):
            next_attachments.append(attachment)
            continue

        original_url = attachment.get("url") or attachment.get("path")
        normalized_url = await media_rehost.rehost_url(
            original_url,
            target_project_id=project_id,
            user_id=user_id,
            copied_by_url=copied_by_url,
        )
        if not normalized_url or normalized_url == attachment.get("url"):
            next_attachments.append(attachment)
            continue

        copied_by_url[str(original_url or "")] = normalized_url
        next_attachment = dict(attachment)
        next_attachment["url"] = normalized_url
        reference = next_attachment.get("reference")
        if isinstance(reference, dict):
            next_reference = dict(reference)
            source = next_reference.get("source")
            if isinstance(source, dict) and source.get("type") == "home_asset":
                next_reference["source"] = {**source, "url": normalized_url}
                next_reference["id"] = f"home-asset:{normalized_url}"
                next_reference["tool_reference"] = normalized_url
            next_attachment["reference"] = next_reference
        next_attachments.append(next_attachment)
        changed = True

    next_references = _replace_canvas_message_reference_urls(references, copied_by_url)
    return next_attachments if changed else attachments, next_references


def _replace_canvas_message_reference_urls(references: Any, replacements: dict[str, str]) -> Any:
    if not replacements or not isinstance(references, list):
        return references

    changed = False
    next_references: list[Any] = []
    for reference in references:
        if not isinstance(reference, dict):
            next_references.append(reference)
            continue

        next_reference = dict(reference)
        reference_changed = False
        source = next_reference.get("source")
        if isinstance(source, dict):
            source_url = source.get("url")
            replacement = replacements.get(str(source_url or ""))
            if replacement:
                next_source = dict(source)
                next_source["url"] = replacement
                next_reference["source"] = next_source
                next_reference["tool_reference"] = replacement
                reference_changed = True
                if next_reference.get("kind") == "home_asset":
                    next_reference["id"] = f"home-asset:{replacement}"

        tool_reference = next_reference.get("tool_reference")
        replacement = replacements.get(str(tool_reference or ""))
        if replacement:
            next_reference["tool_reference"] = replacement
            reference_changed = True

        next_references.append(next_reference)
        changed = changed or reference_changed

    return next_references if changed else references

