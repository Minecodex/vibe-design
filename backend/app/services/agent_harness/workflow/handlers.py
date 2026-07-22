from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import inspect
import json
from pathlib import Path
import time
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.services.agent_harness.authoring.planning.discovery_runtime import (
    build_design_system_interaction,
    build_quick_brief_interaction,
    conversation_has_reference_attachments,
    normalize_interaction_answers,
    resolve_design_system_id,
    resolve_artifact_family,
    should_prompt_design_system_picker,
)
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.skills.policy_registry import default_skill_id_for_artifact_mode
from app.services.agent_harness.capabilities.skill_protocols.registry import resolve_protocol_for_context
from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
from app.services.agent_harness.capabilities.tools import create_harness_registry, tool_max_result_size_chars
from app.services.agent_harness.core.context import reset_current_context, set_current_context
from app.services.agent_harness.core.engine_helpers.engine_utils import resolve_harness_multimodal_model
from app.services.agent_harness.runtime.execution_support.harness_model_provider import create_harness_model_provider
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context
from app.services.agent_harness.runtime.execution_support.billing_controller import record_model_usage_billing
from app.services.agent_harness.runtime.execution_support.interaction_gate import InteractionGate
from app.services.agent_harness.runtime.execution_support.tool_result_projection import build_model_tool_content
from app.services.agent_harness.runtime.execution_support.turn_runner import TurnRunner
from app.services.agent_harness.runtime.artifacts.manifest import normalize_project_relative, read_artifact_manifest
from app.services.agent_harness.runtime.critique.lifecycle import (
    critique_runtime_payload,
    terminate_critique_run,
)
from app.services.agent_harness.runtime.open_design.artifact_adapter import (
    capture_artifact_block,
    has_artifact_open_tag,
)
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    TURN_COMPLETED,
    build_turn_completed_payload,
    build_turn_error,
)
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta, utc_now, write_json
from app.services.agent_harness.runtime.system_write_lease import system_write_lease
from app.services.agent_harness.runtime.model_context import prompt_cache_debug
from app.services.agent_harness.workspace.conversation.home_turn_router import route_after_interaction_submission
from app.services.agent_harness.workspace.conversation.turns.preflight_billing import (
    record_turn_preflight_model_calls,
)
from app.services.agent_harness.workspace.session_v2.service import normalize_message_id
from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
    get_conversation_async,
    get_conversation_dir,
    update_conversation_async,
)
from app.services.agent_harness.prompt_runtime import Phase, PromptMode, PromptRuntime, TurnSpec

from .contracts import BillingSpec, BlobSpec, EventSpec, MessageSpec, StepError, StepResult, StepSpec
from .activity_runner import get_workflow_activity_runner
from .gateway import AgentRuntimeGateway
from .interaction_projection import interaction_payload, interaction_submission_message_spec
from .plan_projection import (
    apply_execution_progress_projection,
    apply_plan_approval_projection,
    apply_planning_draft_projection,
    start_plan_execution_projection,
)
from .presentation_events import event_spec_from_presentation_draft
from .records import WorkflowStepRecord
from .context_session import (
    ContextProjector,
    ContextSessionManager,
    apply_context_session_to_context,
    validate_context_session_integrity,
)
from .repositories import (
    count_consecutive_tool_validation_failures_async,
    get_latest_step_checkpoint_async,
    get_run_runtime_snapshot_async,
    is_cancel_requested,
)
from .diagnostics import log_tool_failure_breaker_terminalized, log_tool_failure_loop_detected, log_workflow_phase_timing
from .ecommerce_generation_context import (
    ECOMMERCE_INTERACTION_KINDS,
    ecommerce_generation_context_message_spec,
    ecommerce_text,
    record_ecommerce_submission_in_contract,
    resolve_ecommerce_taxonomy_prompts,
)
from .runtime_preparation import (
    create_workflow_context,
    prepare_active_skill_runtime_context,
)
from .tool_batch_service import execute_segment, plan_next_segment
from .tool_execution import execute_tool_invocation
from .tool_execution import tool_presentation_message_key
from .tool_gating import (
    CONTROL_TOOL_FAILURE_BREAKER_TOOLS,
    build_tool_card_event,
    normalize_presentation_scope,
    presentation_scope_for_interaction_response,
    is_control_tool_breaker_failure,
    normalized_card_tool_name,
)
from .status import (
    RUN_KIND_REVISE_PLAN,
    RUN_KIND_RESUME_INTERACTION,
    RUN_KIND_START_PLAN,
    STEP_APPLY_USER_INPUT,
    STEP_DISCOVERY_SCHEMA,
    STEP_PREPARE_CONTEXT_SESSION,
    STEP_RENDER_CONTEXT,
    STEP_MODEL_TURN,
    STEP_EXECUTE_TOOL,
    STEP_FAIL_OR_CANCEL,
    STEP_FINALIZE,
    STEP_PERSIST_TOOL_RESULT,
    STEP_PREPARE_SKILL,
    STEP_STATUS_CANCELLED,
    STEP_STATUS_FAILED,
    STEP_STATUS_SUCCEEDED,
    STEP_STATUS_WAITING_INPUT,
    STEP_PLAN_LIFECYCLE,
    STEP_WAIT_USER_INPUT,
)


SYSTEM_PUBLISH_OUTPUT_STEP_KEY_TEMPLATE = "run:{run_id}:system-publish-output:execute"
ARTIFACT_MANIFEST_GATE_STEP_KEY_TEMPLATE = "run:{run_id}:pre-final-artifact-manifest:{turn}"


def _presentation_scope_from_step(step: WorkflowStepRecord) -> dict[str, str | None]:
    return normalize_presentation_scope(step.input.get("presentation_scope"))


def _presentation_scope_input(step: WorkflowStepRecord) -> dict[str, dict[str, str | None]]:
    scope = _presentation_scope_from_step(step)
    return {"presentation_scope": scope} if scope else {}


def _presentation_scope_for_tool_outcome(
    step: WorkflowStepRecord,
    *,
    turn: int,
    call_id: str,
    outcome: dict[str, Any],
) -> dict[str, str | None]:
    scope = normalize_presentation_scope(outcome.get("presentation_scope")) or _presentation_scope_from_step(step)
    if not call_id:
        return scope
    if scope.get("message_key"):
        return scope
    return {
        "message_key": tool_presentation_message_key(
            run_id=step.run_id,
            turn=turn,
            tool_call_id=call_id,
        ),
        "parent_block_key": scope.get("parent_block_key"),
    }


def _turn_completed_event(
    step: WorkflowStepRecord,
    *,
    status: str,
    runtime_snapshot: dict[str, Any],
    error: dict[str, Any] | None = None,
) -> EventSpec:
    return EventSpec(
        event_type=TURN_COMPLETED,
        payload=build_turn_completed_payload(
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            status=status,
            runtime_snapshot=runtime_snapshot,
            error=error,
        ),
        idempotency_key=f"run:{step.run_id}:step:{step.step_id}:turn-completed:{status}",
    )

StepHandler = Callable[[WorkflowStepRecord, AgentRuntimeGateway], Awaitable[StepResult]]
DESIGN_SYSTEM_DISCOVERY_ARTIFACT_FAMILIES = {"web", "document", "slides"}
DISCOVERY_ARTIFACT_FAMILIES = {"web", "document", "slides", "spreadsheet"}
MODEL_STREAM_DELTA_FLUSH_INTERVAL_SECONDS = 0.20
MODEL_STREAM_DELTA_FLUSH_CHARS = 64


class ContextSessionUnavailable(RuntimeError):
    def __init__(self, error_type: str, summary: str) -> None:
        super().__init__(summary)
        self.error_type = error_type
        self.summary = summary


async def _load_context_session(step: WorkflowStepRecord) -> dict[str, Any]:
    snapshot = await get_run_runtime_snapshot_async(step.run_id)
    session = snapshot.get("context_session") if isinstance(snapshot, dict) else None
    if not isinstance(session, dict) or not session.get("fingerprint"):
        raise ContextSessionUnavailable(
            "ContextSessionMissing",
            "execution run is missing context_session; old execution recovery is not supported",
        )
    ok, diagnostics = validate_context_session_integrity(session)
    if not ok:
        raise ContextSessionUnavailable(
            "ContextSessionFingerprintMismatch",
            "execution context_session fingerprint mismatch; old or mutated execution state is not reusable",
        )
    return session


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _phase_elapsed(started_ms: float) -> float:
    return max(_now_ms() - started_ms, 0.0)


async def _record_discovery_model_billing(
    *,
    step: WorkflowStepRecord,
    conversation: dict[str, Any],
    artifact_family: str,
    model_calls: list[dict[str, Any]],
    idempotency_suffix: str | None = None,
) -> None:
    if not model_calls:
        return
    base_key = str(step.idempotency_key or step.step_id or "").strip()
    turn_idempotency_key = f"{base_key}:{idempotency_suffix}" if base_key and idempotency_suffix else base_key or None
    await record_turn_preflight_model_calls(
        user_id=step.user_id,
        conversation=conversation,
        artifact_mode=artifact_family,
        run_id=step.run_id,
        preflight_model_calls=model_calls,
        turn_idempotency_key=turn_idempotency_key,
    )


def _artifact_manifest_needs_publish(manifest: dict[str, Any] | None) -> bool:
    if not isinstance(manifest, dict) or not str(manifest.get("entry") or "").strip():
        return False
    publication = manifest.get("publication") if isinstance(manifest.get("publication"), dict) else {}
    return str(publication.get("status") or "").strip().lower() != "published"


def _artifact_manifest_is_published(manifest: dict[str, Any] | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    publication = manifest.get("publication") if isinstance(manifest.get("publication"), dict) else {}
    return str(publication.get("status") or "").strip().lower() == "published"


def _published_artifact_path(manifest: dict[str, Any] | None) -> str:
    if not isinstance(manifest, dict):
        return ""
    publication = manifest.get("publication") if isinstance(manifest.get("publication"), dict) else {}
    payload = publication.get("payload") if isinstance(publication.get("payload"), dict) else {}
    for key in ("current_version_path", "path"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(manifest.get("entry") or "").strip()


def _normalize_project_entry_candidate(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    normalized = normalized.split("#", 1)[0].split("?", 1)[0].strip().strip("/")
    if not normalized or normalized.startswith((".", "/")) or "://" in normalized:
        return ""
    if normalized.startswith(("references/", "skill/", "published/", ".meta/", ".agent/")):
        return ""
    if normalized.startswith("project/"):
        normalized = normalized[len("project/"):]
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return ""
    suffix = Path(parts[-1]).suffix.lower()
    if suffix not in {".html", ".htm", ".pptx", ".pdf", ".docx", ".md", ".xlsx", ".xlsm", ".csv", ".svg"}:
        return ""
    return "/".join(parts)


def _artifact_kind_for_entry(entry: str, *, artifact_type: str, artifact_mode: str) -> str:
    suffix = Path(entry).suffix.lower()
    normalized_artifact_type = str(artifact_type or "").strip().lower()
    normalized_artifact_mode = str(artifact_mode or "").strip().lower()
    if normalized_artifact_type in {"html", "web"} or normalized_artifact_mode == "web":
        return "html" if suffix in {".html", ".htm"} else "file"
    if normalized_artifact_type in {"ppt", "deck", "slides"}:
        return "deck"
    if normalized_artifact_type in {"excel", "spreadsheet", "sheet"}:
        return "spreadsheet"
    if normalized_artifact_type in {"word", "document", "doc"}:
        return "document"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".pptx":
        return "deck"
    if suffix in {".xlsx", ".xlsm", ".csv"}:
        return "spreadsheet"
    if suffix in {".docx", ".pdf", ".md"}:
        return "document"
    if suffix == ".svg":
        return "svg"
    return "file"


def _render_context_idempotency_key(
    run_id: str,
    *,
    turn: int,
    transient_messages: list[dict[str, Any]] | None = None,
) -> str:
    """Idempotency key for a render_context step.

    When the step carries transient_messages (a recovery / critique / nudge
    instruction), the key includes a digest of that payload so two divergent paths
    that target the same turn cannot dedupe each other and silently drop one path's
    corrective instruction. The digest is deterministic, so retrying the same step
    keeps the same key (idempotent recovery preserved). No-transient steps keep the
    bare key unchanged.
    """
    base = f"run:{run_id}:step:{STEP_RENDER_CONTEXT}:{turn}"
    if not transient_messages:
        return base
    digest = hashlib.sha256(
        json.dumps(transient_messages, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    return f"{base}:t-{digest}"


def _finalize_step_idempotency_key(run_id: str, *, turn: int, reason: str) -> str:
    reason_key = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in str(reason or "model_turn_completed").strip().lower()
    ).strip("-")
    return f"run:{run_id}:step:{STEP_FINALIZE}:{turn}:{reason_key or 'model_turn_completed'}"


def _current_user_message_from_payload(payload: dict[str, Any], *, run_id: str) -> dict[str, Any] | None:
    content = str(payload.get("content") or payload.get("instruction") or "")
    event_payload = payload.get("user_message_event") if isinstance(payload.get("user_message_event"), dict) else {}
    message_metadata = (
        dict(payload.get("message_metadata") or {})
        if isinstance(payload.get("message_metadata"), dict)
        else {}
    )
    attachments = (
        list(event_payload.get("attachments") or [])
        if isinstance(event_payload.get("attachments"), list)
        else list(payload.get("attachments") or [])
    )
    if not content and not attachments and not message_metadata:
        return None
    message_id = str(event_payload.get("id") or "").strip() or f"run:{run_id}:user-message"
    created_at = str(event_payload.get("created_at") or "").strip() or utc_now()
    return {
        "role": "user",
        "content": content,
        "attachments": attachments,
        "created_at": created_at,
        "metadata": {
            **message_metadata,
            "idempotency_key": message_id,
        },
    }


def _runtime_contract_from_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    runtime_state = conversation.get("runtime_state") if isinstance(conversation.get("runtime_state"), dict) else {}
    runtime_snapshot = (
        conversation.get("runtime_snapshot")
        if isinstance(conversation.get("runtime_snapshot"), dict)
        else conversation.get("runtime_snapshot_json")
        if isinstance(conversation.get("runtime_snapshot_json"), dict)
        else {}
    )
    for source in (runtime_state, runtime_snapshot, conversation):
        if not isinstance(source, dict):
            continue
        runtime_contract = source.get("runtime_contract")
        if isinstance(runtime_contract, dict):
            return dict(runtime_contract)
    return {}


def _record_ask_user_submission_in_contract(
    runtime_contract: dict[str, Any],
    *,
    request_id: str,
    pending_interaction: dict[str, Any] | None,
    payload: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    pending = pending_interaction if isinstance(pending_interaction, dict) else {}
    schema = pending.get("schema") if isinstance(pending.get("schema"), dict) else {}
    questions = schema.get("questions") if isinstance(schema.get("questions"), list) else []
    question_ids = [
        str(question.get("id") or "").strip()
        for question in questions
        if isinstance(question, dict) and str(question.get("id") or "").strip()
    ]
    record = {
        "request_id": request_id or None,
        "kind": "ask_user",
        "title": str(schema.get("title") or pending.get("question") or "").strip() or None,
        "question_ids": question_ids,
        "answers": dict(answers or {}),
        "answer": str(payload.get("answer") or ""),
        "display_label": payload.get("display_label"),
        "submitted_at": utc_now(),
    }
    record = {key: value for key, value in record.items() if value not in (None, "", [])}
    updated_contract = dict(runtime_contract or {})
    submissions = [
        dict(item)
        for item in updated_contract.get("ask_user_submissions", [])
        if isinstance(item, dict)
    ]
    if request_id:
        submissions = [
            item for item in submissions if str(item.get("request_id") or "").strip() != request_id
        ]
    submissions.append(record)
    updated_contract["ask_user_submissions"] = submissions[-25:]
    existing_answer_map = updated_contract.get("ask_user_answer_map")
    answer_map = {
        str(key): dict(value)
        for key, value in (existing_answer_map.items() if isinstance(existing_answer_map, dict) else [])
        if isinstance(value, dict)
    }
    if request_id:
        answer_map[request_id] = record
        updated_contract["ask_user_answer_map"] = answer_map
    return updated_contract


def _message_spec_from_persist_message(message: dict[str, Any]) -> MessageSpec:
    metadata = dict(message.get("metadata") or {})
    return MessageSpec(
        role=str(message.get("role") or "system"),
        content=str(message.get("content") or ""),
        blocks=list(message.get("blocks") or []) if isinstance(message.get("blocks"), list) else None,
        tool_calls=list(message.get("tool_calls") or []) if isinstance(message.get("tool_calls"), list) else None,
        attachments=list(message.get("attachments") or []) if isinstance(message.get("attachments"), list) else None,
        created_at=str(message.get("created_at") or "") or None,
        idempotency_key=str(metadata.get("idempotency_key") or ""),
        metadata={
            key: value
            for key, value in metadata.items()
            if key != "idempotency_key"
        },
    )


def _is_external_user_render_step(step_input: dict[str, Any], current_user_message: dict[str, Any] | None) -> bool:
    if isinstance(current_user_message, dict):
        return True
    kind = str(step_input.get("kind") or "").strip()
    return kind in {RUN_KIND_RESUME_INTERACTION, RUN_KIND_START_PLAN, RUN_KIND_REVISE_PLAN}


def _persist_prompt_cache_debug_usage_trace(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    step_id: str,
    turn: int,
    model: str,
    model_provider: str | None,
    prompt_cache_key: str | None,
    usage: dict[str, Any] | None,
    elapsed_ms: int,
    render_trace_file: str | None,
) -> None:
    prompt_cache_debug.ensure_harness_meta = ensure_harness_meta
    prompt_cache_debug.persist_prompt_cache_debug_usage_trace(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        step_id=step_id,
        turn=turn,
        model=model,
        model_provider=model_provider,
        prompt_cache_key=prompt_cache_key,
        usage=usage,
        elapsed_ms=elapsed_ms,
        render_trace_file=render_trace_file,
    )


class _HtmlBodySignalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_html = False
        self.has_body = False
        self._in_body = False
        self._in_script = False
        self.has_body_text = False
        self.has_body_runtime = False
        self.has_body_media = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "html":
            self.has_html = True
        if normalized == "body":
            self.has_body = True
            self._in_body = True
            return
        if not self._in_body:
            return
        if normalized == "script":
            self._in_script = True
            if any(name.lower() == "src" and str(value or "").strip() for name, value in attrs):
                self.has_body_runtime = True
        elif normalized in {"canvas", "embed", "iframe", "img", "object", "picture", "svg", "video"}:
            self.has_body_media = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "script":
            self._in_script = False
        elif normalized == "body":
            self._in_body = False

    def handle_data(self, data: str) -> None:
        if not self._in_body or not str(data or "").strip():
            return
        if self._in_script:
            self.has_body_runtime = True
        else:
            self.has_body_text = True


def _html_entry_has_deliverable_body(entry_path: Path) -> bool:
    try:
        html = entry_path.read_text(encoding="utf-8", errors="ignore")[:131072]
    except OSError:
        return False
    parser = _HtmlBodySignalParser()
    try:
        parser.feed(html)
    except Exception:
        return False
    return parser.has_html and parser.has_body and (
        parser.has_body_text or parser.has_body_runtime or parser.has_body_media
    )


def _project_artifact_candidate_is_publishable(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
    entry: str,
    kind: str,
) -> bool:
    try:
        normalized = normalize_project_relative(entry)
    except ValueError:
        return False
    project_dir = get_conversation_dir(
        user_id,
        conversation_id,
        runtime_profile=conversation.get("runtime_profile"),
        project_id=conversation.get("project_id"),
    ) / "project"
    entry_path = (project_dir / normalized).resolve()
    try:
        entry_path.relative_to(project_dir.resolve())
    except ValueError:
        return False
    try:
        if not entry_path.is_file() or entry_path.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if str(kind or "").strip().lower() == "html" or entry_path.suffix.lower() in {".html", ".htm"}:
        return _html_entry_has_deliverable_body(entry_path)
    return True


def _artifact_manifest_gate_payload(
    conversation: dict[str, Any],
    payload: dict[str, Any],
    *,
    user_id: int,
    conversation_id: str,
) -> dict[str, Any] | None:
    artifact_mode = str(payload.get("artifact_mode") or conversation.get("artifact_mode") or "").strip().lower()
    if artifact_mode in {"", "image", "video", "audio"}:
        return None

    candidates: list[str] = []

    def add_candidate(value: Any) -> None:
        entry = _normalize_project_entry_candidate(value)
        if entry and entry not in candidates:
            candidates.append(entry)

    runtime_state = conversation.get("runtime_state") if isinstance(conversation.get("runtime_state"), dict) else {}
    workspace_session = runtime_state.get("workspace_runtime_session") if isinstance(runtime_state.get("workspace_runtime_session"), dict) else {}
    add_candidate(workspace_session.get("active_entry"))

    plan_state = conversation.get("plan_state") if isinstance(conversation.get("plan_state"), dict) else {}
    user_plan = plan_state.get("user_plan") if isinstance(plan_state.get("user_plan"), dict) else {}
    add_candidate(user_plan.get("file_path") or user_plan.get("filePath"))
    for key in ("items", "outline"):
        for item in list(user_plan.get(key) or []):
            if isinstance(item, dict):
                add_candidate(item.get("artifact_ref") or item.get("artifactRef") or item.get("file_path") or item.get("filePath"))
    outline_state = plan_state.get("outline_state") if isinstance(plan_state.get("outline_state"), dict) else {}
    for item in list(outline_state.get("items") or []):
        if isinstance(item, dict):
            add_candidate(item.get("artifact_ref") or item.get("artifactRef") or item.get("file_path") or item.get("filePath"))

    if not candidates:
        return None
    artifact_type = str(
        user_plan.get("artifact_type")
        or user_plan.get("artifactType")
        or outline_state.get("artifact_type")
        or outline_state.get("artifactType")
        or artifact_mode
    ).strip().lower()
    entry = ""
    kind = ""
    for candidate in candidates:
        candidate_kind = _artifact_kind_for_entry(candidate, artifact_type=artifact_type, artifact_mode=artifact_mode)
        if _project_artifact_candidate_is_publishable(
            user_id=user_id,
            conversation_id=conversation_id,
            conversation=conversation,
            entry=candidate,
            kind=candidate_kind,
        ):
            entry = candidate
            kind = candidate_kind
            break
    if not entry:
        return None
    language = str(payload.get("language") or conversation.get("language") or "zh")
    if language.lower().startswith("zh"):
        message = (
            "系统提醒：最终回复前发现已有可交付文件，但尚未登记 artifact_manifest，版本发布无法继续。"
            f"请只调用工具完成交付登记和发布：先调用 register_artifact(entry=\"{entry}\", kind=\"{kind}\")，"
            "再调用 publish_output。不要输出最终回复；如果 entry 不是用户最终要打开的主文件，请改用正确的 project/ 内主入口。"
        )
    else:
        message = (
            "System reminder: a deliverable file exists, but artifact_manifest is not registered, so version publishing cannot continue. "
            f"Only call tools now: first register_artifact(entry=\"{entry}\", kind=\"{kind}\"), then call publish_output. "
            "Do not send the final answer; if that entry is not the user-facing primary file, use the correct project/ entry instead."
        )
    return {"kind": "artifact_manifest", "entry": entry, "artifact_kind": kind, "message": message}


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _final_summary_outline_items(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    runtime_state = _first_dict(conversation.get("runtime_state"), conversation.get("runtime_snapshot"))
    plan_state = _first_dict(
        conversation.get("user_plan"),
        conversation.get("plan_state"),
        runtime_state.get("user_plan"),
        runtime_state.get("plan_state"),
    )
    raw_items = (
        plan_state.get("items")
        or plan_state.get("outline")
        or _first_dict(runtime_state.get("outline_state")).get("items")
        or []
    )
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw_items[:12]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "title": str(item.get("title") or "").strip(),
                "summary": str(item.get("summary") or item.get("description") or "").strip(),
                "artifact_ref": str(item.get("artifact_ref") or "").strip(),
            }
        )
    return [item for item in items if item["title"] or item["summary"] or item["artifact_ref"]]


def _final_summary_critique_payload(
    conversation: dict[str, Any],
    *,
    runtime_critique: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    runtime_state = _first_dict(conversation.get("runtime_state"), conversation.get("runtime_snapshot"))
    critique = runtime_critique if isinstance(runtime_critique, dict) else runtime_state.get("critique")
    if not isinstance(critique, dict):
        return None
    dimensions = critique.get("dimensions") if isinstance(critique.get("dimensions"), list) else []
    warnings = critique.get("warnings") if isinstance(critique.get("warnings"), list) else []
    return {
        "status": critique.get("status"),
        "round": critique.get("round"),
        "composite": critique.get("composite"),
        "selected_round": critique.get("selected_round"),
        "selected_score": critique.get("selected_score"),
        "must_fix_count": critique.get("must_fix_count"),
        "scores": critique.get("scores") if isinstance(critique.get("scores"), dict) else {},
        "dimensions": [
            {
                "role": item.get("role"),
                "name": item.get("name"),
                "score": item.get("score"),
                "note": item.get("note"),
            }
            for item in dimensions[:6]
            if isinstance(item, dict)
        ],
        "warnings": [
            {
                "code": item.get("code"),
                "message": item.get("message"),
            }
            for item in warnings[:4]
            if isinstance(item, dict)
        ],
    }


def _final_summary_publication_payload(manifest: dict[str, Any] | None) -> dict[str, Any]:
    publication = _first_dict((manifest or {}).get("publication"))
    payload = _first_dict(publication.get("payload"))
    lint = _first_dict(payload.get("open_design_lint"))
    return {
        "status": publication.get("status"),
        "published_at": publication.get("published_at"),
        "file_id": payload.get("file_id"),
        "path": payload.get("current_version_path") or payload.get("path") or _published_artifact_path(manifest),
        "version_id": payload.get("current_version_id"),
        "open_design_lint": {
            "p0_count": lint.get("p0_count"),
            "p1_count": lint.get("p1_count"),
            "p2_count": lint.get("p2_count"),
        }
        if lint
        else None,
    }


def _final_summary_side_payload(
    *,
    title: str,
    artifact_path: str,
    manifest: dict[str, Any] | None,
    conversation: dict[str, Any],
    runtime_critique: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = {
        "title": title,
        "entry": str((manifest or {}).get("entry") or "").strip(),
        "kind": (manifest or {}).get("kind"),
        "renderer": (manifest or {}).get("renderer"),
        "artifact_path": artifact_path,
    }
    return {
        "title": title,
        "artifact_path": artifact_path,
        "artifact": artifact,
        "publication": _final_summary_publication_payload(manifest),
        "outline_items": _final_summary_outline_items(conversation),
        "critique": _final_summary_critique_payload(conversation, runtime_critique=runtime_critique),
    }


def _conversation_multimodal_provider(conversation: dict[str, Any] | None) -> str | None:
    prefs = conversation.get("model_preferences") if isinstance(conversation, dict) else None
    if not isinstance(prefs, dict):
        return None
    provider = str(prefs.get("multimodal_provider") or "").strip()
    return provider or None


async def _persist_critique_ui_state(step: WorkflowStepRecord, payload: dict[str, Any]) -> None:
    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {}
    runtime_state = (
        dict(conversation.get("runtime_state") or {})
        if isinstance(conversation.get("runtime_state"), dict)
        else {}
    )
    runtime_state["critique"] = dict(payload or {})
    await update_conversation_async(
        step.user_id,
        step.conversation_id,
        runtime_state=runtime_state,
    )


async def _has_critique_context(step: WorkflowStepRecord) -> bool:
    return await asyncio.to_thread(critique_runtime_payload, harness_run_id=step.run_id) is not None


def _runtime_context_requires_skill(conversation: dict[str, Any]) -> bool:
    if str(conversation.get("runtime_profile") or "home").strip().lower() == "canvas":
        return True
    artifact_mode = str(conversation.get("artifact_mode") or "").strip().lower()
    if artifact_mode not in DISCOVERY_ARTIFACT_FAMILIES:
        return False
    turn_route = conversation.get("turn_route") if isinstance(conversation.get("turn_route"), dict) else {}
    route_kind = str(turn_route.get("route_kind") or "").strip()
    if route_kind in {"artifact_creation", "artifact_revision", "workflow_continuation"}:
        return True
    if route_kind == "informational_turn":
        return False
    phase = str(conversation.get("phase") or conversation.get("run_state") or "").strip().lower()
    return phase in {"planning", "planning_ready", "awaiting_plan_review", "revising_plan", "executing"}


async def _backfill_default_skill_if_required(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
    skill: Any | None,
    requested_skill_id: str | None = None,
) -> tuple[dict[str, Any], Any | None]:
    if skill is not None or not _runtime_context_requires_skill(conversation):
        return conversation, skill
    requested_skill_id = str(requested_skill_id or "").strip() or None
    if requested_skill_id and str(conversation.get("runtime_profile") or "").strip().lower() == "canvas":
        requested_skill = get_skill(requested_skill_id)
        if requested_skill is not None:
            updates = {
                "skill_id": requested_skill_id,
                "resolved_skill_id": requested_skill_id,
                "skill_selection_mode": "manual",
                "skill_resolution_source": "user_selected",
            }
            requested_artifact_mode = str(getattr(requested_skill, "artifact_mode", "") or "").strip().lower()
            if requested_artifact_mode:
                updates["artifact_mode"] = requested_artifact_mode
            await update_conversation_async(user_id, conversation_id, **updates)
            return {**conversation, **updates}, requested_skill
    artifact_mode = str(conversation.get("artifact_mode") or "").strip().lower()
    default_skill_id = default_skill_id_for_artifact_mode(artifact_mode)
    if not default_skill_id:
        return conversation, skill
    default_skill = get_skill(default_skill_id)
    if default_skill is None:
        return conversation, skill
    updates = {
        "skill_id": default_skill_id,
        "resolved_skill_id": default_skill_id,
        "skill_selection_mode": "auto",
        "skill_resolution_source": "deterministic_default",
        "last_skill_decision_reason": "Default skill required for plan-first artifact mode.",
        "last_skill_decision_confidence": 1.0,
    }
    await update_conversation_async(user_id, conversation_id, **updates)
    return {**conversation, **updates}, default_skill


async def _run_coro_on_loop(coro, loop: asyncio.AbstractEventLoop):
    if asyncio.get_running_loop() is loop:
        return await coro
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return await asyncio.wrap_future(future)


class _SchedulerLoopGatewayProxy:
    def __init__(self, gateway: AgentRuntimeGateway, loop: asyncio.AbstractEventLoop) -> None:
        self._gateway = gateway
        self._loop = loop

    def __getattr__(self, name: str):
        value = getattr(self._gateway, name)
        if not inspect.iscoroutinefunction(value):
            return value

        async def _wrapped(*args, **kwargs):
            return await _run_coro_on_loop(value(*args, **kwargs), self._loop)

        return _wrapped


async def _await_activity(step: WorkflowStepRecord, future, *, poll_seconds: float = 2.0):
    wrapped = asyncio.wrap_future(future)
    try:
        while True:
            done, _pending = await asyncio.wait({wrapped}, timeout=poll_seconds)
            if done:
                return await wrapped
            if await asyncio.to_thread(is_cancel_requested, step.run_id):
                raise asyncio.CancelledError("workflow activity cancelled")
    except asyncio.CancelledError:
        if not wrapped.done():
            future.cancel()
            wrapped.cancel()
        raise


_TOOL_BILLING_LABEL_BY_CATEGORY = {
    "multimodal": "billing.labels.multimodal_call",
    "image_analysis": "billing.labels.image_analysis",
    "image_generation": "billing.labels.image_generate",
    "video_generation": "billing.labels.video_generate",
    "context_compression": "billing.labels.multimodal_call",
}

_DIRECT_MODEL_BILLING_DETAIL_KINDS = {
    "analyze_image",
    "subagent_llm",
    "subagent_llm_final",
}


def _should_record_tool_billing_breakdown_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    detail = item.get("detail")
    if not isinstance(detail, dict):
        return True
    detail_kind = str(detail.get("kind") or "").strip()
    return detail_kind not in _DIRECT_MODEL_BILLING_DETAIL_KINDS


def _user_message_event_specs(payload: dict[str, Any], *, run_id: str) -> list[EventSpec]:
    user_message_event = payload.get("user_message_event")
    if not isinstance(user_message_event, dict) or not user_message_event:
        return []
    event_payload = dict(user_message_event)
    message_metadata = payload.get("message_metadata") if isinstance(payload.get("message_metadata"), dict) else {}
    if message_metadata:
        event_payload["metadata"] = {
            **dict(event_payload.get("metadata") if isinstance(event_payload.get("metadata"), dict) else {}),
            **dict(message_metadata),
        }
    return [
        EventSpec(
            event_type="user_message",
            payload=event_payload,
            idempotency_key=f"run:{run_id}:user-message",
        )
    ]


async def _prepare_skill(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    kind = str(step.input.get("kind") or "message")
    conversation = await get_conversation_async(step.user_id, step.conversation_id)
    if not conversation:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError("ConversationNotFound", f"conversation {step.conversation_id} not found"),
        )

    events = _user_message_event_specs(payload, run_id=step.run_id)

    skill_id = str(conversation.get("skill_id") or conversation.get("resolved_skill_id") or "").strip()
    skill = get_skill(skill_id) if skill_id else None
    skill_selection = payload.get("skill_selection") if isinstance(payload.get("skill_selection"), dict) else {}
    requested_skill_id = str(skill_selection.get("requested_skill_id") or "").strip() or None
    conversation, skill = await _backfill_default_skill_if_required(
        user_id=step.user_id,
        conversation_id=step.conversation_id,
        conversation=conversation,
        skill=skill,
        requested_skill_id=requested_skill_id,
    )
    skill_id = str(conversation.get("skill_id") or conversation.get("resolved_skill_id") or "").strip()
    artifact_family = resolve_artifact_family(conversation=conversation, skill=skill)
    phase = str(conversation.get("phase") or conversation.get("run_state") or "").strip().lower()
    if phase == "executing":
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"runtime_status": "running", "run_state": "preparing", "turn_status": "running"},
            events=events,
            next_steps=[
                StepSpec(
                    step_type=STEP_PREPARE_CONTEXT_SESSION,
                    input={"kind": kind, "payload": payload, "turn": 0},
                    idempotency_key=f"run:{step.run_id}:step:{STEP_PREPARE_CONTEXT_SESSION}:0",
                    max_attempts=2,
                ),
            ],
            activity_summary={"activity_type": "prepare_skill", "routed": "prepare_context_session"},
        )
    if kind != "message" or skill is None or artifact_family not in DISCOVERY_ARTIFACT_FAMILIES:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            events=events,
            error=StepError(
                "ContextSessionSkillRequired",
                "agent workflow requires a selected supported skill; legacy planning context rendering has been removed",
            ),
        )

    async def _prepare() -> dict[str, Any]:
        ctx = create_workflow_context(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            language=str(payload.get("language") or conversation.get("language") or "zh"),
            conversation=conversation,
        )
        ctx.ensure_dirs()
        prepared = prepare_active_skill_runtime_context(ctx=ctx, skill=skill)
        return {
            "runtime_root": str(prepared.get("runtime_root") or ""),
            "artifact_family": artifact_family,
            "runtime_contract": {"active_skill_context": prepared.get("active_skill_context")},
            "staged_skill": prepared.get("staged_skill"),
        }

    prepared = await _await_activity(step, get_workflow_activity_runner().submit(_prepare()))
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:prepare_skill:{step.attempts}",
        activity_type="prepare_skill",
        status="succeeded",
        attempt=step.attempts,
        diagnostics={"artifact_family": artifact_family},
    )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "runtime_status": "running",
            "run_state": "preparing",
            "turn_status": "running",
            "activity": "preparing",
            "prepared_skill_runtime": prepared,
            "runtime_contract": prepared.get("runtime_contract"),
        },
        events=events,
        next_steps=[
            StepSpec(
                step_type=STEP_DISCOVERY_SCHEMA,
                input={"kind": kind, "payload": payload, "artifact_family": artifact_family},
                idempotency_key=f"run:{step.run_id}:step:{STEP_DISCOVERY_SCHEMA}:0",
                max_attempts=3,
            )
        ],
        activity_summary={"activity_type": "prepare_skill", "routed": "discovery_schema"},
    )


async def _discovery_schema(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    conversation = await get_conversation_async(step.user_id, step.conversation_id)
    if not conversation:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError("ConversationNotFound", f"conversation {step.conversation_id} not found"),
        )
    skill_id = str(conversation.get("skill_id") or conversation.get("resolved_skill_id") or "").strip()
    skill = get_skill(skill_id) if skill_id else None
    if skill is None:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError(
                "ContextSessionSkillRequired",
                "agent workflow requires a selected skill; legacy planning context rendering has been removed",
            ),
        )
    language = str(payload.get("language") or conversation.get("language") or "zh")
    artifact_family = str(step.input.get("artifact_family") or resolve_artifact_family(conversation=conversation, skill=skill))
    started_at = utc_now()
    discovery_model_calls: list[dict[str, Any]] = []
    schema_retry_diagnostics: list[dict[str, Any]] = []

    async def _record_quick_brief_model_call(model_name: str, usage: dict[str, Any] | None, elapsed_ms: int) -> None:
        discovery_model_calls.append(
            {
                "kind": "quick_brief_schema",
                "model_name": model_name,
                "usage": usage,
                "elapsed_ms": elapsed_ms,
            }
        )

    async def _build_interaction() -> dict:
        has_reference_attachments = conversation_has_reference_attachments(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
        )
        return await build_quick_brief_interaction(
            conversation_id=step.conversation_id,
            language=language,
            artifact_family=artifact_family,
            conversation=conversation,
            skill=skill,
            has_reference_attachments=has_reference_attachments,
            user_id=step.user_id,
            run_id=step.run_id,
            on_model_call=_record_quick_brief_model_call,
            retry_diagnostics=schema_retry_diagnostics,
        )

    pending_interaction = await _await_activity(step, get_workflow_activity_runner().submit(_build_interaction()))
    await _record_discovery_model_billing(
        step=step,
        conversation=conversation,
        artifact_family=artifact_family,
        model_calls=discovery_model_calls,
    )
    fields = list(((pending_interaction.get("schema") or {}).get("fields") or []))
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:discovery_schema:{step.attempts}",
        activity_type="discovery_schema",
        status="succeeded",
        attempt=step.attempts,
        diagnostics={
            "artifact_family": artifact_family,
            "field_count": len(fields),
            "schema_retry_count": len(schema_retry_diagnostics),
            "schema_retries": schema_retry_diagnostics,
        },
    )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "phase": "discovery",
            "runtime_status": "waiting_input",
            "run_state": "briefing",
            "turn_status": "waiting_input",
            "activity": "waiting_input",
            "user_interaction": pending_interaction,
            "run_id": step.run_id,
            "discovery_status": "waiting_input",
            "discovery_started_at": started_at,
            "discovery_schema": fields,
        },
        next_steps=[
            StepSpec(
                step_type=STEP_WAIT_USER_INPUT,
                input={
                    "interaction": pending_interaction,
                    "artifact_family": artifact_family,
                    "started_at": started_at,
                },
                idempotency_key=f"run:{step.run_id}:step:{STEP_WAIT_USER_INPUT}:quick-brief",
            )
        ],
        activity_summary={"activity_type": "discovery_schema", "field_count": len(fields)},
    )


async def _wait_user_input(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    pending_interaction = interaction_payload(dict(step.input.get("interaction") or {}))
    fields = list(((pending_interaction.get("schema") or {}).get("fields") or []))
    started_at = step.input.get("started_at")
    interaction_kind = str(pending_interaction.get("kind") or "interaction").strip() or "interaction"
    request_id = str(pending_interaction.get("request_id") or interaction_kind).strip() or interaction_kind
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:wait_user_input:{step.attempts}",
        activity_type="wait_user_input",
        status="waiting_input",
        attempt=step.attempts,
        diagnostics={
            "interaction_kind": pending_interaction.get("kind"),
            "field_count": len(fields),
        },
    )
    runtime_patch = {
        "phase": "discovery",
        "runtime_status": "waiting_input",
        "run_state": "briefing",
        "turn_status": "waiting_input",
        "activity": "waiting_input",
        "user_interaction": pending_interaction,
        "run_id": step.run_id,
        "discovery_status": "waiting_input",
        "discovery_started_at": started_at,
        "discovery_schema": fields,
    }
    return StepResult(
        status=STEP_STATUS_WAITING_INPUT,
        runtime_patch=runtime_patch,
        events=[
            EventSpec(
                event_type="discovery_started",
                payload={
                    "discovery_status": "waiting_input",
                    "discovery_started_at": started_at,
                    "discovery_schema": fields,
                },
                idempotency_key=f"run:{step.run_id}:discovery-started:{request_id}",
            ),
            event_spec_from_presentation_draft(
                presentation_v2.event_draft(
                    presentation_v2.interaction_form(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        interaction=pending_interaction,
                    ),
                    idempotency_key=f"run:{step.run_id}:interaction-requested:{request_id}",
                )
            ),
            _turn_completed_event(step, status="waiting_input", runtime_snapshot=runtime_patch),
        ],
        activity_summary={"activity_type": "wait_user_input", "field_count": len(fields)},
    )


async def _prepare_context_session(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    turn = int(step.input.get("turn") or 0)
    conversation = await get_conversation_async(step.user_id, step.conversation_id)
    if not conversation:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError("ConversationNotFound", f"conversation {step.conversation_id} not found"),
        )

    async def _prepare() -> dict[str, Any]:
        return ContextSessionManager().build(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            payload=payload,
            conversation=conversation,
        )

    activity_started = _now_ms()
    context_session = await _await_activity(step, get_workflow_activity_runner().submit(_prepare()))
    activity_elapsed_ms = _phase_elapsed(activity_started)
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:prepare_context_session:{step.attempts}",
        activity_type="prepare_context_session",
        status="succeeded",
        attempt=step.attempts,
        elapsed_ms=activity_elapsed_ms,
        diagnostics={
            "fingerprint": context_session.get("fingerprint"),
            "static_context_hash": context_session.get("static_context_hash"),
            "tool_schema_count": len(context_session.get("tool_schemas") or []),
        },
    )
    runtime_patch = {
        "runtime_status": "running",
        "run_state": "rendering_context",
        "turn_status": "running",
        "activity": "rendering_context",
        "context_session": context_session,
    }
    for key in ("runtime_contract", "workspace_runtime_session", "prepared_workspace"):
        if isinstance(context_session.get(key), dict):
            runtime_patch[key] = context_session[key]
    events = [
        EventSpec(
            event_type="context_session_prepared",
            payload={
                "version": context_session.get("version"),
                "fingerprint": context_session.get("fingerprint"),
                "static_context_hash": context_session.get("static_context_hash"),
                "model": context_session.get("model"),
                "skill_id": context_session.get("skill_id"),
                "artifact_mode": context_session.get("artifact_mode"),
                "tool_schema_count": len(context_session.get("tool_schemas") or []),
            },
            lane="internal",
            idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:context-session-prepared",
        )
    ]
    if isinstance(context_session.get("critique"), dict):
        await _persist_critique_ui_state(step, context_session["critique"])
        events.append(
            EventSpec(
                event_type="critique.started",
                payload=context_session["critique"],
                lane="user",
                idempotency_key=f"run:{step.run_id}:critique:started",
            )
        )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch=runtime_patch,
        events=events,
        next_steps=[
            StepSpec(
                step_type=STEP_RENDER_CONTEXT,
                input={
                    "payload": payload,
                    "turn": turn,
                    **_presentation_scope_input(step),
                    **({"kind": str(step.input.get("kind") or "")} if str(step.input.get("kind") or "").strip() else {}),
                },
                idempotency_key=f"run:{step.run_id}:step:{STEP_RENDER_CONTEXT}:{turn}",
                max_attempts=2,
            )
        ],
        activity_summary={"activity_type": "prepare_context_session"},
    )


async def _render_context(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    turn = int(step.input.get("turn") or 0)
    transient_messages = list(step.input.get("transient_messages") or [])
    try:
        context_session = await _load_context_session(step)
    except ContextSessionUnavailable as exc:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError(exc.error_type, exc.summary),
        )
    previous_checkpoint = await get_latest_step_checkpoint_async(
        run_id=step.run_id,
        step_type=STEP_RENDER_CONTEXT,
        status=STEP_STATUS_SUCCEEDED,
    )
    if isinstance(previous_checkpoint.get("render_context"), dict):
        previous_checkpoint = dict(previous_checkpoint["render_context"])

    async def _render() -> dict[str, Any]:
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        provider = create_harness_model_provider(
            api_key=await resolve_user_apimart_key_for_context(step.user_id),
            multimodal_provider=_conversation_multimodal_provider(conversation)
        )
        current_user_message = _current_user_message_from_payload(payload, run_id=step.run_id) if turn == 0 else None
        return ContextProjector().render(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            render_step_id=step.step_id,
            turn=turn,
            attempt=step.attempts,
            context_session=context_session,
            conversation=conversation,
            previous_checkpoint=previous_checkpoint,
            current_user_message=current_user_message,
            include_runtime_time=_is_external_user_render_step(step.input, current_user_message),
            transient_messages=transient_messages,
            llm_compact_adapter=provider,
        )

    activity_started = _now_ms()
    rendered = await _await_activity(step, get_workflow_activity_runner().submit(_render()))
    activity_elapsed_ms = _phase_elapsed(activity_started)
    checkpoint = rendered.get("checkpoint") if isinstance(rendered.get("checkpoint"), dict) else {}
    if step.claim_token and checkpoint:
        await gateway.update_step_checkpoint(
            claim_token=step.claim_token,
            patch=checkpoint,
        )
    diagnostics = rendered.get("diagnostics") if isinstance(rendered.get("diagnostics"), dict) else {}
    persist_messages = [
        _message_spec_from_persist_message(message)
        for message in list(rendered.get("persist_messages") or [])
        if isinstance(message, dict)
    ]
    rendered_runtime_patch = rendered.get("runtime_patch") if isinstance(rendered.get("runtime_patch"), dict) else {}
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:render_context:{step.attempts}",
        activity_type="render_context",
        status="succeeded",
        attempt=step.attempts,
        elapsed_ms=activity_elapsed_ms,
        diagnostics=diagnostics,
    )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "runtime_status": "running",
            "run_state": "model_turn",
            "turn_status": "running",
            "activity": "model_turn",
            **rendered_runtime_patch,
            "render_context": {
                "turn": turn,
                "message_seq_end": checkpoint.get("message_seq_end"),
                "event_seq_end": checkpoint.get("event_seq_end"),
                "dynamic_context_digest": checkpoint.get("dynamic_context_digest"),
            },
        },
        events=[
            EventSpec(
                event_type="render_context_completed",
                payload={
                    "version": checkpoint.get("version"),
                    "message_seq_end": checkpoint.get("message_seq_end"),
                    "event_seq_end": checkpoint.get("event_seq_end"),
                    "dynamic_context_digest": checkpoint.get("dynamic_context_digest"),
                    "history_source": checkpoint.get("history_source"),
                    "message_count": diagnostics.get("message_count"),
                    "tool_schema_count": diagnostics.get("tool_schema_count"),
                    "static_context_hash": diagnostics.get("static_context_hash"),
                },
                lane="internal",
                idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:render-context-completed",
            )
        ],
        messages=persist_messages,
        next_steps=[
            StepSpec(
                step_type=STEP_MODEL_TURN,
                input={
                    "payload": payload,
                    "turn": turn,
                    "turn_context": rendered.get("turn_context"),
                    **_presentation_scope_input(step),
                },
                idempotency_key=f"run:{step.run_id}:step:{STEP_MODEL_TURN}:{turn}",
                max_attempts=2,
            )
        ],
        activity_summary={"activity_type": "render_context", **diagnostics},
    )


async def _apply_user_input(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
    pending = (
        conversation.get("runtime_state", {}).get("user_interaction")
        if isinstance(conversation.get("runtime_state"), dict)
        else conversation.get("user_interaction")
    )
    normalized_answers = normalize_interaction_answers(
        raw_answers=payload.get("answers") if isinstance(payload.get("answers"), dict) else None,
        answer=str(payload.get("answer") or ""),
        display_label=payload.get("display_label"),
        pending_interaction=pending if isinstance(pending, dict) else None,
    )
    request_id = str((pending or {}).get("request_id") or "").strip() if isinstance(pending, dict) else ""
    pending_kind = str((pending or {}).get("kind") or "").strip() if isinstance(pending, dict) else ""
    raw_resume_turn = (
        (pending or {}).get("resume_turn")
        if isinstance(pending, dict)
        else None
    ) or payload.get("turn") or 0
    try:
        resume_turn = int(raw_resume_turn)
    except (TypeError, ValueError):
        resume_turn = 0
    submission_answers = normalized_answers
    extra_submission_messages: list[MessageSpec] = []
    runtime_contract = _runtime_contract_from_conversation(conversation)
    runtime_contract_changed = False
    design_system_id_patch: str | None = None
    if pending_kind == "quick_brief":
        runtime_contract["discovery_brief"] = {
            "request_id": request_id or None,
            "answers": normalized_answers,
            "answer": str(payload.get("answer") or ""),
            "display_label": payload.get("display_label"),
            "submitted_at": utc_now(),
        }
        runtime_contract_changed = True
    elif pending_kind == "design_system_picker":
        discovery_brief_state = (
            runtime_contract.get("discovery_brief")
            if isinstance(runtime_contract.get("discovery_brief"), dict)
            else {}
        )
        discovery_brief = (
            discovery_brief_state.get("answers")
            if isinstance(discovery_brief_state.get("answers"), dict)
            else {}
        )
        has_reference_attachments = conversation_has_reference_attachments(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
        )
        design_system_id_patch = resolve_design_system_id(
            conversation=conversation,
            discovery_brief=discovery_brief,
            direction_answers=normalized_answers,
            has_reference_attachments=has_reference_attachments,
        )
        runtime_contract["design_system_id"] = design_system_id_patch
        runtime_contract_changed = True
    elif pending_kind == "ask_user":
        runtime_contract = _record_ask_user_submission_in_contract(
            runtime_contract,
            request_id=request_id,
            pending_interaction=pending if isinstance(pending, dict) else None,
            payload=payload,
            answers=normalized_answers,
        )
        runtime_contract_changed = True
    elif pending_kind in ECOMMERCE_INTERACTION_KINDS:
        ecommerce_answers = {
            **normalized_answers,
            **(
                {"action": payload.get("action")}
                if "action" not in normalized_answers and payload.get("action") is not None
                else {}
            ),
        }
        if ecommerce_text(ecommerce_answers.get("action")).lower() == "confirm":
            ecommerce_answers = await resolve_ecommerce_taxonomy_prompts(ecommerce_answers)
        submission_answers = ecommerce_answers
        runtime_contract = record_ecommerce_submission_in_contract(
            runtime_contract,
            request_id=request_id,
            pending_interaction=pending if isinstance(pending, dict) else None,
            payload=payload,
            answers=ecommerce_answers,
        )
        generation_context_message = ecommerce_generation_context_message_spec(
            run_id=step.run_id,
            step_id=step.step_id,
            request_id=request_id,
            answers=ecommerce_answers,
        )
        if generation_context_message is not None:
            extra_submission_messages.append(generation_context_message)
        runtime_contract_changed = True
    submission_message = interaction_submission_message_spec(
        run_id=step.run_id,
        step_id=step.step_id,
        pending_interaction=pending if isinstance(pending, dict) else None,
        payload=payload,
        answers=submission_answers,
    )
    submission_messages = [submission_message] if submission_message is not None else []
    submission_messages.extend(extra_submission_messages)
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:apply_user_input:{step.attempts}",
        activity_type="apply_user_input",
        status="succeeded",
        attempt=step.attempts,
        diagnostics={"pending_kind": pending_kind or None, "has_request_id": bool(request_id)},
    )
    turn_route = route_after_interaction_submission(
        conversation=conversation,
        pending_interaction=pending if isinstance(pending, dict) else None,
    )
    should_create_plan = bool(turn_route.get("requires_plan_gate"))
    route_activity = str(turn_route.get("activity") or "").strip()
    conversation_phase = str(conversation.get("phase") or conversation.get("run_state") or "").strip().lower()
    resumes_planning_context = (
        pending_kind == "ask_user"
        and route_activity == "planning_outline"
        and conversation_phase in {"planning", "revising_plan"}
    )
    next_phase = (
        "planning"
        if should_create_plan
        else conversation_phase
        if resumes_planning_context
        else "executing"
    )
    next_activity = "planning_outline" if should_create_plan or resumes_planning_context else "executing"
    artifact_family = str(conversation.get("artifact_mode") or "").strip().lower()
    if (
        pending_kind == "quick_brief"
        and should_create_plan
        and artifact_family in DESIGN_SYSTEM_DISCOVERY_ARTIFACT_FAMILIES
        and should_prompt_design_system_picker(
            conversation=conversation,
            discovery_brief=normalized_answers,
            has_reference_attachments=conversation_has_reference_attachments(
                user_id=step.user_id,
                conversation_id=step.conversation_id,
            ),
        )
    ):
        skill_id = str(conversation.get("skill_id") or conversation.get("resolved_skill_id") or "").strip()
        skill = get_skill(skill_id) if skill_id else None
        design_system_model_calls: list[dict[str, Any]] = []

        async def _record_design_system_model_call(model_name: str, usage: dict[str, Any] | None, elapsed_ms: int) -> None:
            design_system_model_calls.append(
                {
                    "kind": "design_system_selection",
                    "model_name": model_name,
                    "usage": usage,
                    "elapsed_ms": elapsed_ms,
                }
            )

        pending_design_system = await build_design_system_interaction(
            conversation_id=step.conversation_id,
            language=str(payload.get("language") or conversation.get("language") or "zh"),
            artifact_family=artifact_family,
            conversation=conversation,
            discovery_brief=normalized_answers,
            skill=skill,
            current_design_system_id=None,
            user_id=step.user_id,
            run_id=step.run_id,
            on_model_call=_record_design_system_model_call,
        )
        await _record_discovery_model_billing(
            step=step,
            conversation=conversation,
            artifact_family=artifact_family,
            model_calls=design_system_model_calls,
            idempotency_suffix="design_system",
        )
        fields = list(((pending_design_system.get("schema") or {}).get("fields") or []))
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={
                "phase": "discovery",
                "runtime_status": "waiting_input",
                "run_state": "briefing",
                "turn_status": "waiting_input",
                "activity": "waiting_input",
                "user_interaction": pending_design_system,
                "runtime_contract": runtime_contract,
                "discovery_status": "waiting_input",
                "discovery_schema": fields,
            },
            messages=submission_messages,
            next_steps=[
                StepSpec(
                    step_type=STEP_WAIT_USER_INPUT,
                    input={
                        "interaction": pending_design_system,
                        "artifact_family": artifact_family,
                        "started_at": utc_now(),
                    },
                    idempotency_key=f"run:{step.run_id}:step:{STEP_WAIT_USER_INPUT}:design-system",
                )
            ],
            activity_summary={"activity_type": "apply_user_input", "routed": "design_system_picker"},
        )
    runtime_patch = {
        "phase": next_phase,
        "runtime_status": "running",
        "run_state": next_phase,
        "turn_status": "running",
        "activity": next_activity,
        "user_interaction": None,
    }
    if design_system_id_patch is not None:
        runtime_patch["design_system_id"] = design_system_id_patch
    if runtime_contract_changed:
        runtime_patch["runtime_contract"] = runtime_contract
    next_step_type = STEP_PLAN_LIFECYCLE if should_create_plan else STEP_PREPARE_CONTEXT_SESSION
    next_step_suffix = "after-discovery" if should_create_plan else "0"
    if pending_kind in {"ask_user", *ECOMMERCE_INTERACTION_KINDS}:
        next_step_suffix = f"after-interaction:{request_id or step.step_id}"
    next_step_input = {"payload": payload, "turn": resume_turn}
    if pending_kind in {"ask_user", *ECOMMERCE_INTERACTION_KINDS} and request_id:
        next_step_input["presentation_scope"] = presentation_scope_for_interaction_response(
            conversation_id=step.conversation_id,
            request_id=request_id,
            turn=resume_turn,
        )
    current_kind = str(step.input.get("kind") or "").strip()
    if current_kind:
        next_step_input["kind"] = current_kind
    extra_events: list[EventSpec] = []
    if pending_kind == "design_system_picker" and design_system_id_patch:
        extra_events.append(
            EventSpec(
                event_type="design_system_selected",
                payload={
                    "design_system_id": design_system_id_patch,
                    "source": "user_selected",
                    "phase": next_phase,
                },
                lane="user",
                idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:design-system-selected",
            )
        )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch=runtime_patch,
        events=extra_events,
        messages=submission_messages,
        next_steps=[
            StepSpec(
                step_type=next_step_type,
                input=next_step_input,
                idempotency_key=f"run:{step.run_id}:step:{next_step_type}:{next_step_suffix}",
                max_attempts=2,
            )
        ],
        activity_summary={"activity_type": "apply_user_input"},
    )


# Cap how many times a single user turn may bounce through the artifact-capture
# repair loop. Without it, a model that keeps emitting un-capturable output would
# loop forever (re-render context -> model turn -> capture fails -> repeat),
# leaving the run wedged at "Artifact capture failed; repair required.".
MAX_ARTIFACT_REPAIR_ATTEMPTS = 3
EMPTY_MODEL_RESPONSE_SUMMARY = (
    "Model turn returned no assistant text and no tool calls; stopping the run to avoid an empty retry loop."
)
PLANNING_TOOL_REQUIRED_SUMMARY = (
    "Planning turn produced assistant text without a lifecycle tool call; "
    "planning must use ask_user, update_planning_draft, or request_plan_approval."
)
EXECUTION_PROGRESS_REQUIRED_SUMMARY = (
    "Execution turn produced no tool calls or progress update while the approved plan still has unfinished steps."
)
PLANNING_PHASES = {"planning", "revising_plan"}
EXECUTION_PHASES = {"executing", "finalizing"}
PLANNING_LIFECYCLE_RECOVERY_KEY = "_planning_lifecycle_recovery_attempts"
MAX_PLANNING_LIFECYCLE_RECOVERY_ATTEMPTS = 1
EXECUTION_NO_PROGRESS_RECOVERY_KEY = "_execution_no_progress_recovery_attempts"
MAX_EXECUTION_NO_PROGRESS_RECOVERY_ATTEMPTS = 2


def _normalize_workflow_phase(conversation: dict[str, Any] | None, payload: dict[str, Any] | None) -> str:
    for source in (conversation, payload):
        if not isinstance(source, dict):
            continue
        phase = str(source.get("phase") or "").strip().lower()
        if phase:
            return phase
    return "executing"


def _execution_plan_has_unfinished_steps(conversation: dict[str, Any] | None) -> bool:
    plan_state = (conversation or {}).get("plan_state") if isinstance(conversation, dict) else None
    if not isinstance(plan_state, dict):
        return False
    if str(plan_state.get("status") or "").strip().lower() != "in_progress":
        return False
    execution_state = plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else {}
    steps = execution_state.get("steps") or plan_state.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return False
    return any(
        isinstance(step, dict)
        and str(step.get("status") or "").strip().lower() != "completed"
        for step in steps
    )


def _execution_no_progress_recovery_message(language: str | None) -> str:
    if str(language or "").strip().lower().startswith("zh"):
        return (
            "系统提醒：用户已经批准并开始执行当前计划，但 plan_state 仍为 in_progress，"
            "且 execution_state.steps 中还有未完成步骤。不要等待用户再次批准，也不要直接输出最终回复。"
            "请立即继续执行下一项具体工作并按需调用工具；如果任务确实已经完成，必须先调用 "
            "update_execution_progress，把剩余步骤标记为 completed，并将计划状态同步为 completed。"
        )
    return (
        "System reminder: the user has already approved and started the current plan, "
        "but plan_state is still in_progress and execution_state.steps still has unfinished steps. "
        "Do not wait for another approval and do not send a final answer directly. "
        "Continue the next concrete execution step now using tools as needed; if the task is genuinely complete, "
        "first call update_execution_progress to mark the remaining steps completed and synchronize the plan status to completed."
    )


def _planning_lifecycle_recovery_message(language: str | None) -> str:
    if str(language or "").strip().lower().startswith("zh"):
        return (
            "系统提醒：当前仍处于规划阶段。上一轮只输出了普通说明文本，但规划阶段必须通过生命周期工具"
            "同步状态。请不要重复普通说明；如果还需要用户补充或选择，调用 ask_user；如果正在整理草稿，"
            "调用 update_planning_draft 并提供 draft_outline；如果计划已经完整且可执行，调用 "
            "request_plan_approval。"
        )
    return (
        "System reminder: the run is still in planning. The previous turn produced plain assistant text only, "
        "but planning must synchronize state through a lifecycle tool. Do not repeat prose only; call ask_user "
        "if user input is still needed, update_planning_draft with draft_outline if the plan is still being "
        "drafted, or request_plan_approval if the plan is complete and executable."
    )


def _execution_no_progress_gate_result(
    step: WorkflowStepRecord,
    *,
    phase: str,
    conversation: dict[str, Any] | None,
    payload: dict[str, Any],
    turn: int,
    events: list[EventSpec],
) -> StepResult | None:
    normalized_phase = str(phase or "").strip().lower()
    if normalized_phase not in EXECUTION_PHASES:
        return None
    if not _execution_plan_has_unfinished_steps(conversation):
        return None
    # If the deliverable is already published, a tool-less turn is the legitimate
    # close-out (final summary), not a stall — even if the plan was never synced to
    # completed. Failing it here would mark a successful, published run as failed.
    if _artifact_manifest_is_published(read_artifact_manifest(step.user_id, step.conversation_id)):
        return None
    try:
        recovery_attempts = int(payload.get(EXECUTION_NO_PROGRESS_RECOVERY_KEY) or 0)
    except (TypeError, ValueError):
        recovery_attempts = 0
    if recovery_attempts >= MAX_EXECUTION_NO_PROGRESS_RECOVERY_ATTEMPTS:
        runtime_patch = {
            "phase": normalized_phase,
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "failure": {
                "error_type": "ExecutionPlanProgressRequired",
                "summary": EXECUTION_PROGRESS_REQUIRED_SUMMARY,
                "failure_source": "model_turn",
            },
        }
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch=runtime_patch,
            events=[
                *events,
                _turn_completed_event(
                    step,
                    status="failed",
                    runtime_snapshot=runtime_patch,
                    error=build_turn_error("ExecutionPlanProgressRequired", EXECUTION_PROGRESS_REQUIRED_SUMMARY),
                ),
            ],
            error=StepError("ExecutionPlanProgressRequired", EXECUTION_PROGRESS_REQUIRED_SUMMARY),
            activity_summary={
                "activity_type": "model_turn",
                "tool_call_count": 0,
                "execution_no_progress_blocked": True,
                "phase": normalized_phase,
            },
        )

    next_turn = turn + 1
    language = str((conversation or {}).get("language") or payload.get("language") or "zh")
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "phase": normalized_phase,
            "runtime_status": "running",
            "run_state": "rendering_context",
            "turn_status": "running",
            "activity": "execution_progress_required",
        },
        events=events,
        next_steps=[
            StepSpec(
                step_type=STEP_RENDER_CONTEXT,
                input={
                    "payload": {
                        **payload,
                        EXECUTION_NO_PROGRESS_RECOVERY_KEY: recovery_attempts + 1,
                    },
                    "turn": next_turn,
                    "transient_messages": [
                        {
                            "role": "user",
                            "content": _execution_no_progress_recovery_message(language),
                        }
                    ],
                    **_presentation_scope_input(step),
                },
                idempotency_key=(
                    f"run:{step.run_id}:step:{STEP_RENDER_CONTEXT}:{next_turn}:"
                    f"execution-no-progress:{recovery_attempts + 1}"
                ),
                max_attempts=2,
            )
        ],
        activity_summary={
            "activity_type": "model_turn",
            "tool_call_count": 0,
            "execution_no_progress_recovery": True,
            "recovery_attempt": recovery_attempts + 1,
            "phase": normalized_phase,
        },
    )


def _plain_text_lifecycle_violation_result(
    step: WorkflowStepRecord,
    *,
    phase: str,
    conversation: dict[str, Any] | None,
    payload: dict[str, Any],
    turn: int,
    events: list[EventSpec],
) -> StepResult | None:
    normalized_phase = str(phase or "").strip().lower()
    if normalized_phase in PLANNING_PHASES:
        try:
            recovery_attempts = int(payload.get(PLANNING_LIFECYCLE_RECOVERY_KEY) or 0)
        except (TypeError, ValueError):
            recovery_attempts = 0
        if recovery_attempts < MAX_PLANNING_LIFECYCLE_RECOVERY_ATTEMPTS:
            next_turn = turn + 1
            language = str((conversation or {}).get("language") or payload.get("language") or "zh")
            transient_messages = [{"role": "user", "content": _planning_lifecycle_recovery_message(language)}]
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch={
                    "phase": normalized_phase,
                    "runtime_status": "running",
                    "run_state": normalized_phase,
                    "turn_status": "running",
                    "activity": "planning_lifecycle_required",
                },
                events=events,
                next_steps=[
                    StepSpec(
                        step_type=STEP_RENDER_CONTEXT,
                        input={
                            "payload": {
                                **payload,
                                PLANNING_LIFECYCLE_RECOVERY_KEY: recovery_attempts + 1,
                            },
                            "turn": next_turn,
                            "transient_messages": transient_messages,
                            **_presentation_scope_input(step),
                        },
                        idempotency_key=_render_context_idempotency_key(
                            step.run_id,
                            turn=next_turn,
                            transient_messages=transient_messages,
                        ),
                        max_attempts=2,
                    )
                ],
                activity_summary={
                    "activity_type": "model_turn",
                    "tool_call_count": 0,
                    "plain_text_lifecycle_recovery": True,
                    "recovery_attempt": recovery_attempts + 1,
                    "phase": normalized_phase,
                },
            )
        runtime_patch = {
            "phase": normalized_phase,
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "failure": {
                "error_type": "PlanningLifecycleToolRequired",
                "summary": PLANNING_TOOL_REQUIRED_SUMMARY,
                "failure_source": "model_turn",
            },
        }
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch=runtime_patch,
            events=[
                *events,
                _turn_completed_event(
                    step,
                    status="failed",
                    runtime_snapshot=runtime_patch,
                    error=build_turn_error("PlanningLifecycleToolRequired", PLANNING_TOOL_REQUIRED_SUMMARY),
                ),
            ],
            error=StepError("PlanningLifecycleToolRequired", PLANNING_TOOL_REQUIRED_SUMMARY),
            activity_summary={
                "activity_type": "model_turn",
                "tool_call_count": 0,
                "plain_text_lifecycle_violation": True,
                "phase": normalized_phase,
            },
        )
    return None


async def _model_turn(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    turn = int(step.input.get("turn") or 0)
    artifact_repair_attempts = int(payload.get("_artifact_repair_attempts") or 0)
    transient_messages = list(step.input.get("transient_messages") or [])
    prepared_turn_context = step.input.get("turn_context") if isinstance(step.input.get("turn_context"), dict) else None
    is_final_summary_turn = bool(step.input.get("final_summary"))
    message_id = normalize_message_id(f"run:{step.run_id}:message:assistant:{turn}")
    block_id = f"run:{step.run_id}:model:{turn}:assistant-text"
    stream_state = {"message_started": False, "delta_index": 0}
    stream_delta_buffer: list[str] = []
    stream_delta_buffer_chars = 0
    stream_delta_last_flush = time.monotonic()
    scheduler_loop = asyncio.get_running_loop()
    activity_gateway = _SchedulerLoopGatewayProxy(gateway, scheduler_loop)

    def _presentation_event(payload: dict[str, Any], *, idempotency_key: str, parent_block_key: str | None = None) -> EventSpec:
        return event_spec_from_presentation_draft(
            presentation_v2.event_draft(
                payload,
                block_id=block_id,
                parent_block_id=parent_block_key,
                idempotency_key=idempotency_key,
            )
        )

    def _assistant_text_end_event(text: str) -> EventSpec:
        return _presentation_event(
            presentation_v2.text_block_complete(
                conversation_id=step.conversation_id,
                run_id=step.run_id,
                block_key=block_id,
                message_key=message_id,
                text=text,
                ui_kind="text",
            ),
            idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-end:{step.attempts}",
        )

    async def _resume_completed_model_turn() -> StepResult | None:
        checkpoint = step.checkpoint if isinstance(step.checkpoint, dict) else {}
        model_checkpoint = checkpoint.get("model_turn") if isinstance(checkpoint.get("model_turn"), dict) else {}
        stream_checkpoint = checkpoint.get("stream") if isinstance(checkpoint.get("stream"), dict) else {}
        if not model_checkpoint.get("completed"):
            return None
        stored_message_id = str(stream_checkpoint.get("message_id") or message_id).strip()
        message = await gateway.get_message(stored_message_id)
        if not isinstance(message, dict):
            return None
        message_metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        assistant_text = str(message_metadata.get("model_session_content") or message.get("content") or "")
        tool_calls = list(message.get("tool_calls") or [])
        events = [_assistant_text_end_event(assistant_text)] if assistant_text else []
        if tool_calls:
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch={"runtime_status": "running", "run_state": "waiting_tool", "turn_status": "running"},
                events=events,
                next_steps=[
                    StepSpec(
                        step_type=STEP_EXECUTE_TOOL,
                        input={
                            "payload": payload,
                            "turn": turn,
                            "tool_calls": tool_calls,
                            "segment_start_index": 0,
                            **_presentation_scope_input(step),
                        },
                        idempotency_key=f"run:{step.run_id}:turn:{turn}:tool-segment:0:execute",
                        max_attempts=2,
                    )
                ],
                activity_summary={"activity_type": "model_turn", "recovered_from_checkpoint": True},
            )
        if assistant_text.strip() and not is_final_summary_turn:
            conversation = await get_conversation_async(step.user_id, step.conversation_id) or {
                "id": step.conversation_id
            }
            plain_text_violation = _plain_text_lifecycle_violation_result(
                step,
                phase=_normalize_workflow_phase(conversation, payload),
                conversation=conversation,
                payload=payload,
                turn=turn,
                events=events,
            )
            if plain_text_violation is not None:
                return plain_text_violation
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"runtime_status": "running", "run_state": "finalizing", "turn_status": "running"},
            events=events,
            next_steps=[
                StepSpec(
                    step_type=STEP_FINALIZE,
                    input={"payload": payload, "turn": turn, "reason": "model_turn_completed"},
                    idempotency_key=_finalize_step_idempotency_key(
                        step.run_id,
                        turn=turn,
                        reason="model_turn_completed",
                    ),
                )
            ],
            activity_summary={"activity_type": "model_turn", "recovered_from_checkpoint": True},
        )

    if not bool(settings.HARNESS_CRITIQUE_ENABLED):
        recovered_result = await _resume_completed_model_turn()
        if recovered_result is not None:
            await gateway.record_activity(
                activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:model_turn:{step.attempts}:recovered",
                activity_type="model_turn",
                status="succeeded",
                attempt=step.attempts,
                diagnostics={"recovered_from_checkpoint": True},
            )
            return recovered_result

    if not isinstance(prepared_turn_context, dict):
        recovered_result = await _resume_completed_model_turn()
        if recovered_result is not None:
            await gateway.record_activity(
                activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:model_turn:{step.attempts}:recovered",
                activity_type="model_turn",
                status="succeeded",
                attempt=step.attempts,
                diagnostics={"recovered_from_checkpoint": True},
            )
            return recovered_result
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError("RenderContextMissing", "model_turn requires render_context output"),
        )
    try:
        context_session = await _load_context_session(step)
    except ContextSessionUnavailable as exc:
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=StepError(exc.error_type, exc.summary),
        )

    recovered_result = await _resume_completed_model_turn()
    if recovered_result is not None:
        await gateway.record_activity(
            activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:model_turn:{step.attempts}:recovered",
            activity_type="model_turn",
            status="succeeded",
            attempt=step.attempts,
            diagnostics={"recovered_from_checkpoint": True},
        )
        return recovered_result

    async def _ensure_stream_message_started() -> None:
        if stream_state["message_started"]:
            return
        await _run_coro_on_loop(
            gateway.append_message(
                MessageSpec(
                    role="assistant",
                    content="",
                    streaming=True,
                    idempotency_key=message_id,
                    metadata={
                        "message_kind": "agent_context",
                        "model_visible": True,
                        "ui_visible": False,
                        "run_id": step.run_id,
                        "workflow_step_id": step.step_id,
                    },
                )
            ),
            scheduler_loop,
        )
        await _run_coro_on_loop(
            gateway.append_event(
                _presentation_event(
                    presentation_v2.text_block_start(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        block_key=block_id,
                        message_key=message_id,
                    ),
                    idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-start:{step.attempts}",
                )
            ),
            scheduler_loop,
        )
        if step.attempts > 1:
            # A previous attempt may have streamed partial deltas under this stable
            # block id before failing. Reset the block text so the retry's deltas do not
            # append onto the stale partial text (the client preserves block text across
            # repeated block_start events).
            await _run_coro_on_loop(
                gateway.append_event(
                    _presentation_event(
                        presentation_v2.block_patch(
                            conversation_id=step.conversation_id,
                            run_id=step.run_id,
                            block_key=block_id,
                            message_key=message_id,
                            patch={"payload": {"text": ""}},
                        ),
                        idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-reset:{step.attempts}",
                    )
                ),
                scheduler_loop,
            )
        stream_state["message_started"] = True
        if step.claim_token:
            await _run_coro_on_loop(
                gateway.update_step_checkpoint(
                    claim_token=step.claim_token,
                    patch={
                        "stream": {
                            "message_started": True,
                            "message_id": message_id,
                            "block_id": block_id,
                            "attempt": step.attempts,
                            "delta_index": 0,
                        }
                    },
                ),
                scheduler_loop,
            )

    async def _flush_model_delta(*, force: bool = False) -> None:
        nonlocal stream_delta_buffer_chars, stream_delta_last_flush
        if not stream_delta_buffer:
            return
        elapsed = time.monotonic() - stream_delta_last_flush
        if (
            not force
            and stream_delta_buffer_chars < MODEL_STREAM_DELTA_FLUSH_CHARS
            and elapsed < MODEL_STREAM_DELTA_FLUSH_INTERVAL_SECONDS
        ):
            return
        await _ensure_stream_message_started()
        delta = "".join(stream_delta_buffer)
        stream_delta_buffer.clear()
        stream_delta_buffer_chars = 0
        stream_delta_last_flush = time.monotonic()
        stream_state["delta_index"] = int(stream_state["delta_index"]) + 1
        await _run_coro_on_loop(
            gateway.append_event(
                _presentation_event(
                    presentation_v2.block_delta(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        block_key=block_id,
                        message_key=message_id,
                        field="text",
                        delta=delta,
                    ),
                    idempotency_key=(
                        f"run:{step.run_id}:step:{step.step_id}:event:"
                        f"assistant-text-delta:{step.attempts}:{stream_state['delta_index']}"
                    ),
                )
            ),
            scheduler_loop,
        )
        if step.claim_token and int(stream_state["delta_index"]) % 10 == 0:
            await _run_coro_on_loop(
                gateway.update_step_checkpoint(
                    claim_token=step.claim_token,
                    patch={
                        "stream": {
                            "delta_index": int(stream_state["delta_index"]),
                            "last_event": "presentation.block.delta",
                        }
                    },
                ),
                scheduler_loop,
            )

    async def _on_model_chunk(chunk: dict[str, Any]) -> None:
        nonlocal stream_delta_buffer_chars, stream_delta_last_flush
        delta = str(chunk.get("content") or "")
        if not delta:
            return
        if not stream_delta_buffer:
            stream_delta_last_flush = time.monotonic()
        stream_delta_buffer.append(delta)
        stream_delta_buffer_chars += len(delta)
        await _flush_model_delta()

    async def _run_turn() -> dict:
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        model_provider = _conversation_multimodal_provider(conversation)
        provider = create_harness_model_provider(
            api_key=await resolve_user_apimart_key_for_context(step.user_id),
            multimodal_provider=model_provider
        )
        ctx = create_workflow_context(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            language=str(payload.get("language") or conversation.get("language") or "zh"),
            conversation=conversation,
        )
        ctx.runtime_gateway = activity_gateway
        apply_context_session_to_context(ctx, context_session)
        ctx.ensure_dirs()
        registry = create_harness_registry(web_search_enabled=bool(payload.get("web_search_enabled", True)))
        model = str(context_session.get("model") or resolve_harness_multimodal_model(conversation))
        ctx.multimodal_model = model
        token = set_current_context(ctx)
        try:
            ctx.run_subagent_handler = HarnessSubagentRunner(
                provider=provider,
                conversation=conversation,
                parent_context=ctx,
                parent_registry=registry,
                language=ctx.language,
            ).run
            turn_context = {
                "messages": list(prepared_turn_context.get("messages") or []),
                "system": str(prepared_turn_context.get("system") or ""),
                "tools": list(prepared_turn_context.get("tools") or []),
                "model": str(prepared_turn_context.get("model") or model),
                "language": str(prepared_turn_context.get("language") or ctx.language),
                "prompt_cache_key": str(prepared_turn_context.get("prompt_cache_key") or f"agent:{step.conversation_id}"),
            }
            result = await TurnRunner(provider).run(
                messages=turn_context["messages"],
                system=turn_context["system"],
                tools=turn_context["tools"],
                model=turn_context["model"],
                prompt_cache_key=turn_context["prompt_cache_key"],
                on_chunk=_on_model_chunk,
            )
            return {
                "assistant_text": result.assistant_text,
                "tool_calls": result.tool_calls,
                "finish_reason": result.finish_reason,
                "usage": result.usage,
                "elapsed_ms": result.elapsed_ms,
                "model": turn_context["model"],
                "model_provider": model_provider,
                "language": turn_context["language"],
                "prompt_cache_key": turn_context["prompt_cache_key"],
                "conversation": conversation,
            }
        finally:
            reset_current_context(token)

    result = await _await_activity(step, get_workflow_activity_runner().submit(_run_turn()))
    await _flush_model_delta(force=True)
    try:
        _persist_prompt_cache_debug_usage_trace(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            step_id=step.step_id,
            turn=turn,
            model=str(result.get("model") or ""),
            model_provider=str(result.get("model_provider") or "") or None,
            prompt_cache_key=str(result.get("prompt_cache_key") or "") or None,
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else None,
            elapsed_ms=int(result.get("elapsed_ms") or 0),
            render_trace_file=(
                str(prepared_turn_context.get("prompt_cache_debug_trace_file") or "")
                if isinstance(prepared_turn_context, dict)
                else ""
            )
            or None,
        )
    except Exception:
        pass
    # Reuse the conversation already loaded inside the turn instead of re-fetching the
    # (potentially large) runtime snapshot for billing.
    billing_conversation = (
        result.get("conversation")
        if isinstance(result.get("conversation"), dict)
        else None
    ) or {"id": step.conversation_id}
    billing_ctx = create_workflow_context(
        user_id=step.user_id,
        conversation_id=step.conversation_id,
        run_id=step.run_id,
        language=str(result.get("language") or payload.get("language") or billing_conversation.get("language") or "zh"),
        conversation=billing_conversation,
    )
    await record_model_usage_billing(
        user_id=step.user_id,
        ctx=billing_ctx,
        model_name=str(result.get("model") or ""),
        usage=result.get("usage") if isinstance(result.get("usage"), dict) else None,
        elapsed_ms=int(result.get("elapsed_ms") or 0),
        kind="agent_llm",
        category="multimodal",
        billing_key=f"run:{step.run_id}:step:{step.step_id}:billing:model",
    )
    assistant_text = str(result.get("assistant_text") or "")
    tool_calls = list(result.get("tool_calls") or [])
    if not assistant_text.strip() and not tool_calls:
        await gateway.record_activity(
            activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:model_turn:{step.attempts}",
            activity_type="model_turn",
            status="failed",
            attempt=step.attempts,
            elapsed_ms=float(result.get("elapsed_ms") or 0),
            diagnostics={
                "model": result.get("model"),
                "tool_call_count": 0,
                "assistant_text_length": 0,
                "artifact_captured": False,
                "empty_model_response": True,
                "finish_reason": result.get("finish_reason"),
            },
        )
        runtime_patch = {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "last_error_summary": EMPTY_MODEL_RESPONSE_SUMMARY,
            "failure": {
                "error_type": "EmptyModelResponse",
                "summary": EMPTY_MODEL_RESPONSE_SUMMARY,
                "failure_source": "model_turn",
            },
        }
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch=runtime_patch,
            events=[
                _turn_completed_event(
                    step,
                    status="failed",
                    runtime_snapshot=runtime_patch,
                    error=build_turn_error("EmptyModelResponse", EMPTY_MODEL_RESPONSE_SUMMARY),
                )
            ],
            error=StepError("EmptyModelResponse", EMPTY_MODEL_RESPONSE_SUMMARY),
            activity_summary={
                "activity_type": "model_turn",
                "tool_call_count": 0,
                "empty_model_response": True,
            },
        )
    artifact_capture = None
    if assistant_text and not tool_calls and has_artifact_open_tag(assistant_text):
        capture_conversation = (
            result.get("conversation")
            if isinstance(result.get("conversation"), dict)
            else None
        ) or {"id": step.conversation_id}
        ctx = create_workflow_context(
            user_id=step.user_id,
            conversation_id=step.conversation_id,
            run_id=step.run_id,
            language=str(result.get("language") or payload.get("language") or capture_conversation.get("language") or "zh"),
            conversation=capture_conversation,
        )
        ctx.runtime_gateway = activity_gateway
        apply_context_session_to_context(ctx, context_session)
        ctx.ensure_dirs()
        protocol = resolve_protocol_for_context(ctx)
        artifact_capture = await capture_artifact_block(ctx, assistant_text, protocol=protocol, return_errors=True)
        if artifact_capture is not None:
            assistant_text = artifact_capture.replacement_text
    if stream_state["message_started"]:
        await gateway.update_message(
            message_id=message_id,
            content="",
            tool_calls=tool_calls,
            streaming=False,
            metadata={
                "message_kind": "agent_context",
                "model_visible": True,
                "ui_visible": False,
                "run_id": step.run_id,
                "workflow_step_id": step.step_id,
                "text_block_id": block_id,
                "model_session_content": assistant_text,
                "finish_reason": result.get("finish_reason"),
            },
        )
    elif assistant_text or tool_calls:
        await gateway.append_message(
            MessageSpec(
                role="assistant",
                content="",
                tool_calls=tool_calls or None,
                streaming=False,
                idempotency_key=message_id,
                metadata={
                    "message_kind": "agent_context",
                    "model_visible": True,
                    "ui_visible": False,
                    "run_id": step.run_id,
                    "workflow_step_id": step.step_id,
                    "text_block_id": block_id,
                    "model_session_content": assistant_text,
                    "finish_reason": result.get("finish_reason"),
                },
            )
        )
    if step.claim_token:
        await gateway.update_step_checkpoint(
            claim_token=step.claim_token,
            patch={
                "model_turn": {
                    "completed": True,
                    "finish_reason": result.get("finish_reason"),
                    "assistant_text_length": len(str(result.get("assistant_text") or "")),
                    "tool_call_count": len(result.get("tool_calls") or []),
                },
                "stream": {
                    "message_started": bool(stream_state["message_started"]),
                    "message_id": message_id,
                    "block_id": block_id,
                    "delta_index": int(stream_state["delta_index"]),
                    "completed": bool(result.get("assistant_text")),
                },
            },
        )
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:model_turn:{step.attempts}",
        activity_type="model_turn",
        status="succeeded",
        attempt=step.attempts,
        elapsed_ms=float(result.get("elapsed_ms") or 0),
        diagnostics={
            "model": result.get("model"),
            "tool_call_count": len(result.get("tool_calls") or []),
            "assistant_text_length": len(str(result.get("assistant_text") or "")),
            "artifact_captured": bool(artifact_capture),
        },
    )
    messages: list[MessageSpec] = []
    events: list[EventSpec] = []
    if artifact_capture is not None and stream_state["message_started"]:
        events.append(
            _presentation_event(
                presentation_v2.block_patch(
                    conversation_id=step.conversation_id,
                    run_id=step.run_id,
                    block_key=block_id,
                    message_key=message_id,
                    patch={"payload": {"text": assistant_text}},
                ),
                idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-artifact-capture:{step.attempts}",
            )
        )
    if assistant_text and not stream_state["message_started"]:
        events.extend(
            [
                _presentation_event(
                    presentation_v2.text_block_start(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        block_key=block_id,
                        message_key=message_id,
                    ),
                    idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-start:{step.attempts}",
                ),
                _presentation_event(
                    presentation_v2.block_delta(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        block_key=block_id,
                        message_key=message_id,
                        field="text",
                        delta=assistant_text,
                    ),
                    idempotency_key=f"run:{step.run_id}:step:{step.step_id}:event:assistant-text-delta:{step.attempts}:final",
                ),
            ]
        )
    if assistant_text:
        events.append(_assistant_text_end_event(assistant_text))
    if tool_calls:
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={
                "runtime_status": "running",
                "run_state": "waiting_tool",
                "turn_status": "running",
            },
            events=events,
            messages=messages,
            next_steps=[
                StepSpec(
                    step_type=STEP_EXECUTE_TOOL,
                    input={
                        "payload": payload,
                        "turn": turn,
                        "tool_calls": tool_calls,
                        "segment_start_index": 0,
                        **_presentation_scope_input(step),
                    },
                    idempotency_key=f"run:{step.run_id}:turn:{turn}:tool-segment:0:execute",
                    max_attempts=2,
                )
            ],
            activity_summary={"activity_type": "model_turn", "tool_call_count": len(tool_calls)},
        )
    if (
        artifact_capture is not None
        and artifact_capture.error_text
        and artifact_repair_attempts < MAX_ARTIFACT_REPAIR_ATTEMPTS
    ):
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={
                "runtime_status": "running",
                "run_state": "rendering_context",
                "turn_status": "running",
            },
            events=events,
            messages=messages,
            next_steps=[
                StepSpec(
                    step_type=STEP_RENDER_CONTEXT,
                    input={
                        "payload": {**payload, "_artifact_repair_attempts": artifact_repair_attempts + 1},
                        "turn": turn + 1,
                        "transient_messages": [{"role": "user", "content": artifact_capture.error_text}],
                        **_presentation_scope_input(step),
                    },
                    idempotency_key=f"run:{step.run_id}:step:{STEP_RENDER_CONTEXT}:{turn + 1}:artifact-capture-error",
                    max_attempts=2,
                )
            ],
            activity_summary={"activity_type": "model_turn", "tool_call_count": 0, "artifact_capture_error": True},
        )
    if artifact_capture is None and not is_final_summary_turn:
        execution_no_progress = _execution_no_progress_gate_result(
            step,
            phase=_normalize_workflow_phase(billing_conversation, payload),
            conversation=billing_conversation,
            payload=payload,
            turn=turn,
            events=events,
        )
        if execution_no_progress is not None:
            return execution_no_progress
    if artifact_capture is None and not is_final_summary_turn:
        plain_text_violation = _plain_text_lifecycle_violation_result(
            step,
            phase=_normalize_workflow_phase(billing_conversation, payload),
            conversation=billing_conversation,
            payload=payload,
            turn=turn,
            events=events,
        )
        if plain_text_violation is not None:
            return plain_text_violation
    finalize_reason = "final_summary_completed" if is_final_summary_turn else "model_turn_completed"
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "runtime_status": "running",
            "run_state": "finalizing",
            "turn_status": "running",
        },
        events=events,
        messages=messages,
        next_steps=[
            StepSpec(
                step_type=STEP_FINALIZE,
                input={"payload": payload, "turn": turn, "reason": finalize_reason},
                idempotency_key=_finalize_step_idempotency_key(
                    step.run_id,
                    turn=turn,
                    reason=finalize_reason,
                ),
            )
        ],
        activity_summary={"activity_type": "model_turn", "tool_call_count": 0},
    )


async def _execute_tool(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    tool_calls = list(step.input.get("tool_calls") or [])
    segment_start_index = int(step.input.get("segment_start_index") or 0)
    turn = int(step.input.get("turn") or 0)
    scheduler_loop = asyncio.get_running_loop()
    activity_gateway = _SchedulerLoopGatewayProxy(gateway, scheduler_loop)

    checkpoint = step.checkpoint if isinstance(step.checkpoint, dict) else {}
    segment_checkpoint = checkpoint.get("tool_segment") if isinstance(checkpoint.get("tool_segment"), dict) else {}
    try:
        checkpoint_segment_start_index = int(segment_checkpoint.get("segment_start_index"))
    except (TypeError, ValueError):
        checkpoint_segment_start_index = -1
    recovered_outcomes = (
        list(segment_checkpoint.get("outcomes") or [])
        if segment_checkpoint.get("completed")
        and checkpoint_segment_start_index == segment_start_index
        else None
    )
    registry = create_harness_registry(web_search_enabled=bool(payload.get("web_search_enabled", True)))
    segment = plan_next_segment(registry=registry, tool_calls=tool_calls, start_index=segment_start_index)
    context_session: dict[str, Any] | None = None
    if recovered_outcomes is None:
        try:
            context_session = await _load_context_session(step)
        except ContextSessionUnavailable as exc:
            return StepResult(
                status=STEP_STATUS_FAILED,
                runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
                error=StepError(exc.error_type, exc.summary),
            )

    async def _run_segment() -> list[dict[str, Any]]:
        return await execute_segment(
            segment=segment,
            execute_one=lambda tool_call, absolute_tool_index: execute_tool_invocation(
                step=step,
                gateway=activity_gateway,
                activity_gateway=activity_gateway,
                scheduler_loop=scheduler_loop,
                payload=payload,
                turn=turn,
                tool_call=tool_call,
                absolute_tool_index=absolute_tool_index,
                context_session=context_session,
            ),
            max_concurrency=int(getattr(settings, "HARNESS_TOOL_BATCH_MAX_CONCURRENCY", 10) or 10),
        )

    activity_started = _now_ms()
    if recovered_outcomes is not None:
        outcomes = [dict(outcome) for outcome in recovered_outcomes]
        activity_elapsed_ms = 0.0
    else:
        outcomes = await _await_activity(step, get_workflow_activity_runner().submit(_run_segment()))
        activity_elapsed_ms = _phase_elapsed(activity_started)
    for outcome in outcomes:
        timings = outcome.get("timings") if isinstance(outcome.get("timings"), dict) else {}
        for phase, elapsed_ms in timings.items():
            log_workflow_phase_timing(
                phase=f"execute_tool.{phase.removesuffix('_ms')}",
                step_type=step.step_type,
                step_id=step.step_id,
                run_id=step.run_id,
                elapsed_ms=float(elapsed_ms or 0.0),
                metadata={
                    "tool_name": outcome.get("tool_name"),
                    "tool_index": outcome.get("tool_index"),
                    "status": outcome.get("status"),
                },
            )
    if step.claim_token and recovered_outcomes is None:
        await gateway.update_step_checkpoint(
            claim_token=step.claim_token,
            patch={
                "tool_segment": {
                    "completed": True,
                    "segment_start_index": segment.start_index,
                    "next_tool_index": segment.end_index,
                    "outcomes": outcomes,
                }
            },
        )
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:execute_tool:{step.attempts}",
        activity_type="execute_tool",
        status="failed" if any(bool(outcome.get("is_error")) for outcome in outcomes) else "succeeded",
        attempt=step.attempts,
        elapsed_ms=activity_elapsed_ms,
        diagnostics={
            "segment_start_index": segment.start_index,
            "next_tool_index": segment.end_index,
            "tool_count": len(outcomes),
            "concurrent": segment.is_concurrent,
        },
    )
    for outcome in outcomes:
        for billing_index, item in enumerate(list(outcome.get("billing_breakdown") or [])):
            if not _should_record_tool_billing_breakdown_item(item):
                continue
            detail = item.get("detail") if isinstance(item, dict) and isinstance(item.get("detail"), dict) else {}
            billing_category = str(item.get("category") or "agent_tool") if isinstance(item, dict) else "agent_tool"
            await gateway.record_billing(
                BillingSpec(
                    billing_key=(
                        f"run:{step.run_id}:step:{step.step_id}:billing:"
                        f"tool:{outcome.get('call_id') or outcome.get('tool_index')}:{billing_index}"
                    ),
                    model_name=str(detail.get("model_name") or detail.get("model") or outcome.get("tool_name") or "tool"),
                    model_label=str(detail.get("model_label") or detail.get("model_name") or outcome.get("tool_name") or "tool"),
                    task_type=billing_category,
                    amount_cents=int(float(item.get("amount") or 0)) if isinstance(item, dict) else 0,
                    parent_id=None,
                    params={"detail": detail, "tool_name": outcome.get("tool_name"), "tool_call_id": outcome.get("call_id")},
                    task_status="completed",
                    billing_label=_TOOL_BILLING_LABEL_BY_CATEGORY.get(billing_category, "billing.labels.multimodal_call"),
                    elapsed_ms=int(detail.get("elapsed_ms") or 0) if isinstance(detail, dict) else None,
                )
            )
    first_outcome = outcomes[0] if outcomes else {}
    first_call_id = str(first_outcome.get("call_id") or first_outcome.get("tool_index") or segment.start_index)
    next_step = StepSpec(
        step_type=STEP_PERSIST_TOOL_RESULT,
        input={
            "payload": payload,
            "turn": turn,
            "tool_calls": tool_calls,
            "segment_start_index": segment.start_index,
            "next_tool_index": segment.end_index,
            "outcomes": outcomes,
            "outcome_index": 0,
            **_presentation_scope_input(step),
        },
        idempotency_key=f"run:{step.run_id}:turn:{turn}:tool:{first_call_id}:persist-result",
    )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        next_steps=[next_step],
        activity_summary={
            "activity_type": "execute_tool",
            "segment_start_index": segment.start_index,
            "next_tool_index": segment.end_index,
            "tool_count": len(outcomes),
        },
    )


def _tool_card_result_payload(outcome: dict[str, Any], result_payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    raw_args = outcome.get("raw_args")
    if not isinstance(raw_args, dict):
        raw_args = result_payload.get("args")
    base = dict(raw_args or {}) if isinstance(raw_args, dict) else {}
    payload = {**base, **metadata}
    for key in ("query", "search_type"):
        if str(payload.get(key) or "").strip():
            continue
        value = base.get(key)
        if value not in (None, ""):
            payload[key] = value
    return payload


def _media_result_has_task_identity(metadata: dict[str, Any]) -> bool:
    for key in ("task_id", "artifact_ref", "result_url", "planned_result_url", "preview_url"):
        if str(metadata.get(key) or "").strip():
            return True
    return isinstance(metadata.get("canvas_item"), dict)


def _should_emit_media_generation_card(*, outcome: dict[str, Any], metadata: dict[str, Any]) -> bool:
    if metadata.get("emit_media_card") is False:
        return False
    failed = bool(outcome.get("is_error")) or str(outcome.get("status") or "").lower() == "failed"
    if not failed:
        return _media_result_has_task_identity(metadata)
    failure_kind = str(metadata.get("failure_kind") or "").strip()
    if failure_kind == "invalid_parameters":
        return False
    return _media_result_has_task_identity(metadata)


def _pending_interaction_from_tool_metadata(
    *,
    tool_name: str,
    call_id: str,
    tool_metadata: dict[str, Any],
    output: str,
) -> dict[str, Any] | None:
    if tool_name == "ask_user":
        return interaction_payload(InteractionGate.ask_user_pending(call_id, tool_metadata, output))
    if str(tool_metadata.get("type") or "").strip() != "interaction":
        return None
    source = tool_metadata.get("interaction")
    if not isinstance(source, dict):
        return None
    kind = str(source.get("kind") or "").strip()
    if not kind:
        return None
    request_id = str(source.get("request_id") or source.get("requestId") or call_id or "").strip()
    pending = dict(source)
    pending["request_id"] = request_id
    pending["tool_call_id"] = str(source.get("tool_call_id") or source.get("toolCallId") or request_id)
    return interaction_payload(pending)


async def _tool_failure_breaker_result(
    step: WorkflowStepRecord,
    *,
    tool_name: str,
    outcome: dict[str, Any],
) -> StepResult | None:
    normalized_tool = str(tool_name or "").strip()
    if normalized_tool not in CONTROL_TOOL_FAILURE_BREAKER_TOOLS or not is_control_tool_breaker_failure(outcome):
        return None
    threshold = max(int(getattr(settings, "HARNESS_WORKFLOW_TOOL_FAILURE_BREAKER_THRESHOLD", 3) or 3), 1)
    previous_failures = await count_consecutive_tool_validation_failures_async(
        run_id=step.run_id,
        before_step_pk=step.id,
        tool_name=normalized_tool,
    )
    failure_count = previous_failures + 1
    log_tool_failure_loop_detected(
        run_id=step.run_id,
        tool_name=normalized_tool,
        failure_count=failure_count,
        latest_step_id=step.step_id,
        error_type="tool_validation_loop",
        breaker_threshold=threshold,
    )
    if failure_count < threshold:
        return None
    log_tool_failure_breaker_terminalized(run_id=step.run_id, tool_name=normalized_tool, status="failed")
    summary = f"{normalized_tool} failed validation {failure_count} consecutive times"
    runtime_patch = {
        "runtime_status": "failed",
        "run_state": "failed",
        "turn_status": "failed",
        "failure": {"error_type": "tool_validation_loop", "summary": summary},
    }
    return StepResult(
        status=STEP_STATUS_FAILED,
        runtime_patch=runtime_patch,
        events=[
            _turn_completed_event(
                step,
                status="failed",
                runtime_snapshot=runtime_patch,
                error=build_turn_error("tool_validation_loop", summary),
            )
        ],
        activity_summary={
            "activity_type": "persist_tool_result",
            "status": "failed",
            "tool_name": normalized_tool,
            "failure_count": failure_count,
            "error_type": "tool_validation_loop",
        },
        error=StepError("tool_validation_loop", summary),
    )


def _is_duplicate_media_generation_reuse(
    *,
    tool_name: str,
    metadata: dict[str, Any],
) -> bool:
    return (
        normalized_card_tool_name(tool_name) in {"generate_image", "generate_video"}
        and metadata.get("duplicate_generation_blocked") is True
    )


async def _persist_tool_result(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    turn = int(step.input.get("turn") or 0)
    tool_calls = list(step.input.get("tool_calls") or [])
    segment_start_index = int(step.input.get("segment_start_index") or 0)
    next_tool_index = int(step.input.get("next_tool_index") or 0)
    outcomes = list(step.input.get("outcomes") or [])
    outcome_index = int(step.input.get("outcome_index") or 0)
    outcome = dict(outcomes[outcome_index] or {}) if 0 <= outcome_index < len(outcomes) else {}
    result_payload = dict(outcome.get("result_payload") or {})
    call_id = str(outcome.get("call_id") or result_payload.get("tool_call_id") or "")
    tool_name = str(outcome.get("tool_name") or result_payload.get("tool") or "")
    output = str(result_payload.get("output") or "")
    tool_metadata = result_payload.get("metadata") if isinstance(result_payload.get("metadata"), dict) else {}
    is_interaction_result = str(tool_metadata.get("type") or "").strip() == "interaction"
    presentation_scope = _presentation_scope_for_tool_outcome(
        step,
        turn=turn,
        call_id=call_id,
        outcome=outcome,
    )
    _card_tool = normalized_card_tool_name(tool_name)
    is_media_generation_tool = _card_tool in {"generate_image", "generate_video"}
    should_emit_media_card = (
        _should_emit_media_generation_card(outcome=outcome, metadata=tool_metadata)
        if is_media_generation_tool and not is_interaction_result
        else False
    )
    duplicate_media_generation_reuse = _is_duplicate_media_generation_reuse(
        tool_name=tool_name,
        metadata=tool_metadata,
    )
    blob = await gateway.write_blob(
        BlobSpec(
            content=output,
            tool_call_id=call_id or "tool",
            tool_name=tool_name or "tool",
        )
    )
    artifact_ref = str(tool_metadata.get("artifact_ref") or "").strip()
    if should_emit_media_card or duplicate_media_generation_reuse:
        model_payload = {
            "status": "failed" if outcome.get("is_error") else "completed",
            "artifact_ref": artifact_ref or None,
            "error": tool_metadata.get("error") or tool_metadata.get("error_message"),
            "blob_artifact": blob.get("artifact"),
        }
        model_payload = {key: value for key, value in model_payload.items() if value is not None and value != ""}
    else:
        review = result_payload.get("review") if isinstance(result_payload.get("review"), dict) else None
        model_payload = build_model_tool_content(
            tool_name=tool_name,
            output=output,
            review=review,
            outcome=outcome,
            blob_artifact=blob.get("artifact"),
            max_chars=tool_max_result_size_chars(tool_name),
        )
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:persist_tool_result:{step.attempts}",
        activity_type="persist_tool_result",
        status=str(outcome.get("status") or "succeeded"),
        attempt=step.attempts,
        output_ref=str((blob.get("artifact") or {}).get("ref") or ""),
        diagnostics={"tool_name": tool_name, "call_id": call_id, "promoted_blob": bool(blob.get("promoted"))},
    )
    runtime_patch = {"runtime_status": "running", "run_state": "rendering_context", "turn_status": "running"}
    events = [
        EventSpec(
            event_type="tool_result",
            payload={"tool": tool_name, "tool_call_id": call_id, "review": result_payload.get("review") or {}},
            lane="internal",
            tool_call_id=call_id,
            idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:result-event",
        )
    ]
    # Publish the user-facing media/web-search card for the tool result. For async
    # media (generate_image/video) the tool returns status=processing, which renders the
    # in-progress card; the generation-task poller later updates the same block to
    # completed. analyze_image / web_search are synchronous, so this is their final card.
    if should_emit_media_card:
        _card_status = str(tool_metadata.get("status") or ("failed" if outcome.get("is_error") else "completed"))
    else:
        _card_status = (
            "failed"
            if (outcome.get("is_error") or str(outcome.get("status") or "") == "failed")
            else "completed"
        )
    end_card_event = build_tool_card_event(
        conversation_id=step.conversation_id,
        run_id=step.run_id,
        step_id=step.step_id,
        phase="end",
        tool_name=tool_name,
        call_id=call_id,
        result_payload=_tool_card_result_payload(outcome, result_payload, tool_metadata),
        status=_card_status,
        message_key=presentation_scope.get("message_key"),
        parent_block_key=presentation_scope.get("parent_block_key"),
        order=int(outcome.get("presentation_order") or int(outcome.get("tool_index") or 0) + 1),
    )
    if end_card_event is not None and not is_interaction_result and (not is_media_generation_tool or should_emit_media_card):
        events.append(end_card_event)
    planning_draft = tool_metadata.get("planning_draft")
    if tool_name == "update_planning_draft" and isinstance(planning_draft, dict):
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        draft_patch, draft_events = apply_planning_draft_projection(
            run_id=step.run_id,
            step_id=step.step_id,
            conversation=conversation,
            planning_draft=planning_draft,
        )
        runtime_patch.update(draft_patch)
        events.extend(draft_events)
    plan_state = tool_metadata.get("plan_state")
    if tool_name == "request_plan_approval" and isinstance(plan_state, dict):
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        plan_patch, plan_events = apply_plan_approval_projection(
            run_id=step.run_id,
            step_id=step.step_id,
            conversation=conversation,
            plan_state=plan_state,
        )
        runtime_patch.update(plan_patch)
        events.extend(plan_events)
    if tool_name == "update_execution_progress" and isinstance(plan_state, dict):
        plan_patch, plan_events = apply_execution_progress_projection(
            run_id=step.run_id,
            step_id=step.step_id,
            plan_state=plan_state,
        )
        runtime_patch.update(plan_patch)
        events.extend(plan_events)
    breaker_result = await _tool_failure_breaker_result(step, tool_name=tool_name, outcome=outcome)
    if breaker_result is not None:
        breaker_result.events[:0] = events
        breaker_result.messages[:0] = [
            MessageSpec(
                role="tool",
                content=json.dumps(model_payload, ensure_ascii=False),
                idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:result-message",
                metadata={
                    "message_kind": "agent_context",
                    "ui_visible": False,
                    "run_id": step.run_id,
                    "workflow_step_id": step.step_id,
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "model_visible": not (should_emit_media_card or duplicate_media_generation_reuse),
                    **({"suppress_model_context": True} if duplicate_media_generation_reuse else {}),
                },
            )
        ]
        return breaker_result
    messages = [
        MessageSpec(
            role="tool",
            content=json.dumps(model_payload, ensure_ascii=False),
            idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:result-message",
            metadata={
                "message_kind": "agent_context",
                "ui_visible": False,
                "run_id": step.run_id,
                "workflow_step_id": step.step_id,
                "tool_call_id": call_id,
                "tool_name": tool_name,
                "model_visible": not (should_emit_media_card or duplicate_media_generation_reuse),
                **({"suppress_model_context": True} if duplicate_media_generation_reuse else {}),
            },
        )
    ]
    pending_interaction = (
        _pending_interaction_from_tool_metadata(
            tool_name=tool_name,
            call_id=call_id,
            tool_metadata=tool_metadata,
            output=output,
        )
        if not bool(outcome.get("is_error")) and str(outcome.get("status") or "") != "failed"
        else None
    )
    if pending_interaction is not None:
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        pending_interaction["resume_turn"] = turn + 1
        runtime_patch = {
            "phase": str(conversation.get("phase") or "executing"),
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "activity": "waiting_input",
            "user_interaction": pending_interaction,
        }
        events.append(
            event_spec_from_presentation_draft(
                presentation_v2.event_draft(
                    presentation_v2.interaction_form(
                        conversation_id=step.conversation_id,
                        run_id=step.run_id,
                        interaction=pending_interaction,
                    ),
                    idempotency_key=f"run:{step.run_id}:interaction-requested:{call_id or step.step_id}",
                )
            )
        )
        return StepResult(
            status=STEP_STATUS_WAITING_INPUT,
            runtime_patch=runtime_patch,
            messages=messages,
            events=[
                *events,
                _turn_completed_event(step, status="waiting_input", runtime_snapshot=runtime_patch),
            ],
            activity_summary={"activity_type": "persist_tool_result", **outcome, "awaiting_user": True},
        )
    if bool(tool_metadata.get("plan_gate_blocked")):
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        runtime_patch = {
            "phase": str(conversation.get("phase") or "planning_ready"),
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "activity": "waiting_input",
        }
        return StepResult(
            status=STEP_STATUS_WAITING_INPUT,
            runtime_patch=runtime_patch,
            messages=messages,
            events=[
                *events,
                _turn_completed_event(step, status="waiting_input", runtime_snapshot=runtime_patch),
            ],
            activity_summary={
                "activity_type": "persist_tool_result",
                **outcome,
                "awaiting_user": True,
                "plan_gate_blocked": True,
            },
        )
    if str(runtime_patch.get("runtime_status") or "").lower() == "waiting_input":
        return StepResult(
            status=STEP_STATUS_WAITING_INPUT,
            runtime_patch=runtime_patch,
            messages=messages,
            events=[
                *events,
                _turn_completed_event(step, status="waiting_input", runtime_snapshot=runtime_patch),
            ],
            activity_summary={"activity_type": "persist_tool_result", **outcome, "awaiting_user": True},
        )
    tool_succeeded = not bool(outcome.get("is_error")) and str(outcome.get("status") or "").lower() != "failed"
    reason_code = str(tool_metadata.get("reason_code") or "")
    if tool_name == "publish_output" and tool_succeeded:
        critique_publish_status = str(tool_metadata.get("critique_publish_status") or "").strip().lower()
        if critique_publish_status in {"degraded", "failed"}:
            # Fail-open publish: the Design Jury could not validate this version (e.g. an
            # internal review error), so it was published only as a fallback. Do NOT treat
            # it as a clean terminal ship — that would summarize and end the run on an
            # unvalidated artifact. Hand control back to the model so it can improve and
            # re-publish for a clean review, or wrap up on its own terms (a no-tool reply
            # then finalizes via the normal path). The stuck-run janitor + Fix-3 recovery
            # bound the worst case if the review keeps degrading.
            nudge = (
                "The Design Jury could not validate the published version due to an internal review error, "
                "so the current version was published only as a fallback. If the artifact still needs work, "
                "improve it and call publish_output again to obtain a clean review; otherwise give your final summary."
            )
            transient_messages = [{"role": "user", "content": nudge}]
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch={"runtime_status": "running", "run_state": "rendering_context", "turn_status": "running"},
                messages=messages,
                events=events,
                next_steps=[
                    StepSpec(
                        step_type=STEP_RENDER_CONTEXT,
                        input={
                            "payload": payload,
                            "turn": turn + 1,
                            "transient_messages": transient_messages,
                            **_presentation_scope_input(step),
                        },
                        idempotency_key=_render_context_idempotency_key(
                            step.run_id,
                            turn=turn + 1,
                            transient_messages=transient_messages,
                        ),
                        max_attempts=2,
                    )
                ],
                activity_summary={
                    "activity_type": "persist_tool_result",
                    **outcome,
                    "publish_fail_open_continue": True,
                    "critique_publish_status": critique_publish_status,
                },
            )
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"runtime_status": "running", "run_state": "finalizing", "turn_status": "running"},
            messages=messages,
            events=events,
            next_steps=[
                StepSpec(
                    step_type=STEP_FINALIZE,
                    input={"payload": payload, "turn": turn, "reason": "artifact_published"},
                    # Per-publish unique key: a single run can publish more than once
                    # (e.g. a fail-open round followed by a genuine ship). A fixed key
                    # let the first publish consume it, so the final ship's finalize was
                    # deduped away — leaving the run RUNNING with no steps until the
                    # stuck-run janitor failed it. Scope by turn + call_id so every
                    # publish enqueues its own finalize while retries of the *same*
                    # publish still dedupe.
                    idempotency_key=(
                        f"run:{step.run_id}:step:{STEP_FINALIZE}:after-publish-output:{turn}:{call_id or 'publish'}"
                    ),
                )
            ],
            activity_summary={"activity_type": "persist_tool_result", **outcome, "finalize_after_publish": True},
        )
    if (
        tool_name == "publish_output"
        and not tool_succeeded
        and reason_code.startswith("critique_")
    ):
        repair_instruction = str(
            tool_metadata.get("repair_instruction")
            or ((tool_metadata.get("recovery_hint") or {}).get("instruction") if isinstance(tool_metadata.get("recovery_hint"), dict) else "")
            or output
            or "Repair the Design Jury must-fix items, then register_artifact and publish_output again."
        )
        if reason_code == "critique_not_authorized" and repair_instruction:
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch={"runtime_status": "running", "run_state": "rendering_context", "turn_status": "running"},
                messages=messages,
                events=events,
                next_steps=[
                    StepSpec(
                        step_type=STEP_RENDER_CONTEXT,
                        input={
                            "payload": payload,
                            "turn": turn + 1,
                            "transient_messages": [{"role": "user", "content": repair_instruction}],
                            **_presentation_scope_input(step),
                        },
                        idempotency_key=_render_context_idempotency_key(
                            step.run_id,
                            turn=turn + 1,
                            transient_messages=[{"role": "user", "content": repair_instruction}],
                        ),
                        max_attempts=2,
                    )
                ],
                activity_summary={
                    "activity_type": "persist_tool_result",
                    **outcome,
                    "publish_critique_repair_enqueued": True,
                },
            )
        summary = str((result_payload.get("review") or {}).get("summary") or output or "publish_output failed")[:500]
        runtime_patch = {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "failure": {
                "error_type": reason_code,
                "summary": summary,
            },
        }
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch=runtime_patch,
            messages=messages,
            events=[
                *events,
                _turn_completed_event(
                    step,
                    status="failed",
                    runtime_snapshot=runtime_patch,
                    error=build_turn_error(reason_code, summary),
                ),
            ],
            activity_summary={
                "activity_type": "persist_tool_result",
                **outcome,
                "publish_critique_guard_failed": True,
            },
            error=StepError(reason_code, summary),
        )
    if (
        tool_name == "publish_output"
        and not tool_succeeded
        and str(call_id).startswith("system_publish:")
    ):
        if reason_code == "open_design_artifact_lint_failed":
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch=runtime_patch,
                messages=messages,
                events=events,
                next_steps=[
                    StepSpec(
                        step_type=STEP_RENDER_CONTEXT,
                        input={"payload": payload, "turn": turn + 1, **_presentation_scope_input(step)},
                        idempotency_key=f"run:{step.run_id}:step:{STEP_RENDER_CONTEXT}:{turn + 1}:artifact-lint",
                    )
                ],
                activity_summary={
                    "activity_type": "persist_tool_result",
                    **outcome,
                    "system_publish_lint_repair": True,
                },
            )
        summary = str((result_payload.get("review") or {}).get("summary") or output or "publish_output failed")[:500]
        runtime_patch = {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "failure": {
                "error_type": reason_code or "system_publish_failed",
                "summary": summary,
            },
        }
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch=runtime_patch,
            messages=messages,
            events=[
                *events,
                _turn_completed_event(
                    step,
                    status="failed",
                    runtime_snapshot=runtime_patch,
                    error=build_turn_error(reason_code or "system_publish_failed", summary),
                ),
            ],
            activity_summary={
                "activity_type": "persist_tool_result",
                **outcome,
                "system_publish_failed": True,
            },
            error=StepError(reason_code or "system_publish_failed", summary),
        )
    if duplicate_media_generation_reuse:
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"runtime_status": "running", "run_state": "finalizing", "turn_status": "running"},
            messages=messages,
            events=events,
            next_steps=[
                StepSpec(
                    step_type=STEP_FINALIZE,
                    input={"payload": payload, "turn": turn, "reason": "duplicate_media_generation_reuse"},
                    idempotency_key=_finalize_step_idempotency_key(
                        step.run_id,
                        turn=turn,
                        reason="duplicate_media_generation_reuse",
                    ),
                )
            ],
            activity_summary={
                "activity_type": "persist_tool_result",
                **outcome,
                "duplicate_media_generation_reuse_finalized": True,
            },
        )
    next_outcome_index = outcome_index + 1
    if next_outcome_index < len(outcomes):
        next_outcome = dict(outcomes[next_outcome_index] or {})
        next_call_id = str(next_outcome.get("call_id") or next_outcome.get("tool_index") or next_outcome_index)
        next_step = StepSpec(
            step_type=STEP_PERSIST_TOOL_RESULT,
            input={
                "payload": payload,
                "turn": turn,
                "tool_calls": tool_calls,
                "segment_start_index": segment_start_index,
                "next_tool_index": next_tool_index,
                "outcomes": outcomes,
                "outcome_index": next_outcome_index,
                **_presentation_scope_input(step),
            },
            idempotency_key=f"run:{step.run_id}:turn:{turn}:tool:{next_call_id}:persist-result",
        )
    elif next_tool_index < len(tool_calls):
        next_step = StepSpec(
            step_type=STEP_EXECUTE_TOOL,
            input={
                "payload": payload,
                "turn": turn,
                "tool_calls": tool_calls,
                "segment_start_index": next_tool_index,
                **_presentation_scope_input(step),
            },
            idempotency_key=f"run:{step.run_id}:turn:{turn}:tool-segment:{next_tool_index}:execute",
            max_attempts=2,
        )
    else:
        next_step = StepSpec(
            step_type=STEP_RENDER_CONTEXT,
            input={"payload": payload, "turn": turn + 1, **_presentation_scope_input(step)},
            idempotency_key=f"run:{step.run_id}:step:{STEP_RENDER_CONTEXT}:{turn + 1}",
        )
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch=runtime_patch,
        messages=messages,
        events=events,
        next_steps=[next_step],
        activity_summary={"activity_type": "persist_tool_result", **outcome},
    )


async def _plan_lifecycle(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    kind = str(step.input.get("kind") or "")
    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:plan_lifecycle:{step.attempts}",
        activity_type="plan_lifecycle",
        status="succeeded",
        attempt=step.attempts,
    )
    if kind == RUN_KIND_START_PLAN:
        runtime_patch, events = start_plan_execution_projection(
            run_id=step.run_id,
            step_id=step.step_id,
            conversation=conversation,
            payload=payload,
        )
        events = [*_user_message_event_specs(payload, run_id=step.run_id), *events]
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch=runtime_patch,
            events=events,
            next_steps=[
                StepSpec(
                    step_type=STEP_PREPARE_CONTEXT_SESSION,
                    input={
                        "payload": payload,
                        "turn": int(step.input.get("turn") or 0),
                        **({"kind": kind} if kind else {}),
                    },
                    idempotency_key=f"run:{step.run_id}:step:{STEP_PREPARE_CONTEXT_SESSION}:after-plan-start",
                )
            ],
            activity_summary={"activity_type": "plan_lifecycle", "kind": kind},
        )
    planning_phase = "revising_plan" if kind == RUN_KIND_REVISE_PLAN or payload.get("instruction") else "planning"
    resume_request_id = _resume_interaction_request_id_for_plan_lifecycle(step, kind=kind, payload=payload)
    context_suffix = f"after-interaction:{resume_request_id}" if resume_request_id else "after-plan"
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={
            "phase": planning_phase,
            "runtime_status": "running",
            "run_state": planning_phase,
            "turn_status": "running",
            "activity": "planning_outline",
        },
        next_steps=[
            StepSpec(
                step_type=STEP_PREPARE_CONTEXT_SESSION,
                input={
                    "payload": payload,
                    "turn": int(step.input.get("turn") or 0),
                    **({"kind": kind} if kind else {}),
                },
                idempotency_key=f"run:{step.run_id}:step:{STEP_PREPARE_CONTEXT_SESSION}:{context_suffix}",
            )
        ],
        activity_summary={"activity_type": "plan_lifecycle"},
    )


def _resume_interaction_request_id_for_plan_lifecycle(
    step: WorkflowStepRecord,
    *,
    kind: str,
    payload: dict[str, Any],
) -> str:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        return ""
    if kind == RUN_KIND_RESUME_INTERACTION:
        return request_id
    marker = f":step:{STEP_PLAN_LIFECYCLE}:after-interaction:"
    key = str(step.idempotency_key or "")
    if marker not in key:
        return ""
    return request_id


async def _final_summary_turn_context(
    step: WorkflowStepRecord,
    *,
    payload: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    try:
        context_session = await _load_context_session(step)
    except ContextSessionUnavailable:
        return None
    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
    language = str(payload.get("language") or context_session.get("language") or conversation.get("language") or "zh")
    title = str(
        (manifest or {}).get("title")
        or conversation.get("title")
        or "当前任务"
    ).strip()
    artifact_path = _published_artifact_path(manifest)
    runtime_critique = await asyncio.to_thread(critique_runtime_payload, harness_run_id=step.run_id)
    bundle = PromptRuntime().build_bundle(
        TurnSpec(
            mode=PromptMode.FINAL_SUMMARY,
            phase=Phase.FINALIZING,
            language=language,
            conversation=conversation,
            side_payload=_final_summary_side_payload(
                title=title,
                artifact_path=artifact_path,
                manifest=manifest,
                conversation=conversation,
                runtime_critique=runtime_critique,
            ),
        )
    )
    system = "\n\n".join(
        block.content
        for block in [*bundle.system_blocks, *bundle.developer_blocks, *bundle.state_blocks]
        if str(block.content or "").strip()
    )
    return {
        "messages": list(bundle.messages),
        "system": system,
        "tools": [],
        "model": str(context_session.get("model") or resolve_harness_multimodal_model(conversation)),
        "language": language,
    }


async def _pre_final_artifact_manifest_turn_context(
    step: WorkflowStepRecord,
    *,
    payload: dict[str, Any],
    conversation: dict[str, Any],
    gate_payload: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        context_session = await _load_context_session(step)
    except ContextSessionUnavailable:
        return None
    language = str(payload.get("language") or context_session.get("language") or conversation.get("language") or "zh")
    bundle = PromptRuntime().build_bundle(
        TurnSpec(
            mode=PromptMode.PRE_FINAL_GATE,
            phase=Phase.FINALIZING,
            language=language,
            conversation=conversation,
            side_payload=gate_payload,
        )
    )
    system = "\n\n".join(
        block.content
        for block in [*bundle.system_blocks, *bundle.developer_blocks, *bundle.state_blocks]
        if str(block.content or "").strip()
    )
    return {
        "messages": list(bundle.messages),
        "system": system,
        "tools": list(context_session.get("tool_schemas") or []),
        "model": str(context_session.get("model") or resolve_harness_multimodal_model(conversation)),
        "language": language,
    }


def _plan_completion_sync(
    step: WorkflowStepRecord,
    conversation: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[EventSpec]]:
    """Mark an in-progress plan completed at finalize after a successful publish.

    The model frequently publishes the deliverable without calling
    update_execution_progress to sync the last step / plan status to completed,
    leaving plan_state in_progress. That both trips the no-progress gate and leaves
    the plan card showing a lingering unfinished step. When we reach a clean finalize
    with a published artifact, synthesize the "all steps completed" projection so the
    persisted plan reflects reality. Best-effort: returns empty patch/events when
    there is no in-progress plan to sync.
    """
    plan_state = conversation.get("plan_state") if isinstance(conversation, dict) else None
    if not isinstance(plan_state, dict):
        return {}, []
    if str(plan_state.get("status") or "").strip().lower() == "completed":
        return {}, []
    execution = plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else {}
    steps = execution.get("steps") if isinstance(execution.get("steps"), list) else plan_state.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}, []
    next_plan = deepcopy(plan_state)
    next_execution = deepcopy(execution) if isinstance(execution, dict) else {}
    next_execution["steps"] = [
        {**dict(item), "status": "completed"} if isinstance(item, dict) else item for item in steps
    ]
    next_execution["status"] = "completed"
    next_plan["execution_state"] = next_execution
    next_plan["status"] = "completed"
    try:
        return apply_execution_progress_projection(
            run_id=step.run_id,
            step_id=step.step_id,
            plan_state=next_plan,
        )
    except Exception:
        return {}, []


async def _finalize(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    payload = dict(step.input.get("payload") or {})
    turn = int(step.input.get("turn") or 0)
    manifest = await asyncio.to_thread(read_artifact_manifest, step.user_id, step.conversation_id)
    if _artifact_manifest_needs_publish(manifest):
        tool_call = {
            "id": f"system_publish:{step.run_id}",
            "type": "function",
            "name": "publish_output",
            "arguments": {},
        }
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={
                "runtime_status": "running",
                "run_state": "waiting_tool",
                "turn_status": "running",
                "activity": "publishing_output",
            },
            next_steps=[
                StepSpec(
                    step_type=STEP_EXECUTE_TOOL,
                    input={
                        "payload": payload,
                        "turn": turn,
                        "tool_calls": [tool_call],
                        "segment_start_index": 0,
                        "system_injected": True,
                    },
                    idempotency_key=SYSTEM_PUBLISH_OUTPUT_STEP_KEY_TEMPLATE.format(run_id=step.run_id),
                    max_attempts=2,
                )
            ],
            activity_summary={"activity_type": "finalize", "system_publish_output_enqueued": True},
        )
    if manifest is None:
        conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
        gate_payload = _artifact_manifest_gate_payload(
            conversation,
            payload,
            user_id=step.user_id,
            conversation_id=step.conversation_id,
        )
        if gate_payload is not None:
            turn_context = await _pre_final_artifact_manifest_turn_context(
                step,
                payload=payload,
                conversation=conversation,
                gate_payload=gate_payload,
            )
            if turn_context is not None:
                next_turn = turn + 1
                return StepResult(
                    status=STEP_STATUS_SUCCEEDED,
                    runtime_patch={
                        "runtime_status": "running",
                        "run_state": "model_turn",
                        "turn_status": "running",
                        "activity": "pre_final_artifact_manifest_gate",
                    },
                    next_steps=[
                        StepSpec(
                            step_type=STEP_MODEL_TURN,
                            input={
                                "payload": payload,
                                "turn": next_turn,
                                "turn_context": turn_context,
                            },
                            idempotency_key=ARTIFACT_MANIFEST_GATE_STEP_KEY_TEMPLATE.format(
                                run_id=step.run_id,
                                turn=next_turn,
                            ),
                            max_attempts=2,
                        )
                    ],
                    activity_summary={
                        "activity_type": "finalize",
                        "pre_final_artifact_manifest_gate": True,
                        "entry": gate_payload.get("entry"),
                        "artifact_kind": gate_payload.get("artifact_kind"),
                    },
                )
    latest_assistant = await gateway.get_latest_assistant_message()
    final_answer_events: list[EventSpec] = []
    should_summarize_after_publish = (
        str(step.input.get("reason") or "").strip() == "artifact_published"
        and _artifact_manifest_is_published(manifest)
    )
    if should_summarize_after_publish:
        turn_context = await _final_summary_turn_context(step, payload=payload, manifest=manifest)
        if turn_context is not None:
            next_turn = turn + 1
            return StepResult(
                status=STEP_STATUS_SUCCEEDED,
                runtime_patch={
                    "runtime_status": "running",
                    "run_state": "summarizing",
                    "turn_status": "running",
                    "activity": "final_summary",
                },
                next_steps=[
                    StepSpec(
                        step_type=STEP_MODEL_TURN,
                        input={
                            "payload": payload,
                            "turn": next_turn,
                            "turn_context": turn_context,
                            "final_summary": True,
                        },
                        idempotency_key=f"run:{step.run_id}:step:{STEP_MODEL_TURN}:{next_turn}:final-summary",
                        max_attempts=2,
                    )
                ],
                activity_summary={"activity_type": "finalize", "final_summary_enqueued": True},
            )
    conversation_for_progress = await get_conversation_async(step.user_id, step.conversation_id) or {
        "id": step.conversation_id
    }
    # The post-summary finalize (reason="final_summary_completed") is the legitimate
    # terminal turn: the closing summary is text-only by design. Don't run the
    # no-progress gate on it — mirrors the same exemption applied to the plain-text
    # lifecycle violation below. (The model_turn handler already exempts the
    # final-summary turn itself.)
    if str(step.input.get("reason") or "").strip() != "final_summary_completed":
        execution_no_progress = _execution_no_progress_gate_result(
            step,
            phase=_normalize_workflow_phase(conversation_for_progress, payload),
            conversation=conversation_for_progress,
            payload=payload,
            turn=turn,
            events=[],
        )
        if execution_no_progress is not None:
            return execution_no_progress
    if isinstance(latest_assistant, dict):
        latest_message_id = str(latest_assistant.get("id") or "").strip()
        latest_metadata = latest_assistant.get("metadata") if isinstance(latest_assistant.get("metadata"), dict) else {}
        latest_text = str(latest_metadata.get("model_session_content") or latest_assistant.get("content") or "").strip()
        if latest_message_id and latest_text:
            if str(step.input.get("reason") or "").strip() != "final_summary_completed":
                payload_phase = _normalize_workflow_phase(None, payload)
                if payload_phase in PLANNING_PHASES:
                    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {
                        "id": step.conversation_id
                    }
                    plain_text_violation = _plain_text_lifecycle_violation_result(
                        step,
                        phase=_normalize_workflow_phase(conversation, payload),
                        conversation=conversation,
                        payload=payload,
                        turn=turn,
                        events=[],
                    )
                    if plain_text_violation is not None:
                        return plain_text_violation
            # Reuse the streaming text block id (recorded by model_turn) so the final
            # answer replaces the per-turn assistant_text block in place instead of
            # rendering the same text twice. Fall back to a dedicated block id for
            # paths that did not stream a model turn (e.g. system publish_output).
            final_block_id = (
                str(latest_metadata.get("text_block_id") or "").strip()
                or f"run:{step.run_id}:final-answer"
            )
            final_answer_events.extend(
                [
                    event_spec_from_presentation_draft(
                        presentation_v2.event_draft(
                            presentation_v2.text_block_complete(
                                conversation_id=step.conversation_id,
                                run_id=step.run_id,
                                block_key=final_block_id,
                                message_key=latest_message_id,
                                text=latest_text,
                                ui_kind="text",
                                payload_extra={"message_kind": "final_answer"},
                            ),
                            block_id=final_block_id,
                            idempotency_key=f"run:{step.run_id}:final-answer",
                        )
                    ),
                    EventSpec(
                        event_type="assistant_message_finalized",
                        payload={"message_id": latest_message_id, "status": "completed"},
                        lane="projection",
                        idempotency_key=f"run:{step.run_id}:assistant-message-finalized",
                    ),
                ]
            )
    await gateway.refresh_parent_usage_log(status="success")
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:finalize:{step.attempts}",
        activity_type="finalize",
        status="succeeded",
        attempt=step.attempts,
    )
    runtime_patch = {
        "runtime_status": "completed",
        "run_state": "completed",
        "turn_status": "completed",
        "finalized": True,
    }
    # On a clean finalize with a published deliverable, sync any still-in-progress
    # plan to completed so the plan card and runtime state reflect the real outcome
    # (the model often publishes without a final update_execution_progress sync).
    plan_sync_events: list[EventSpec] = []
    if _artifact_manifest_is_published(manifest):
        plan_patch, plan_sync_events = _plan_completion_sync(step, conversation_for_progress)
        # Only layer the plan projection data; the terminal run-state fields
        # (completed/finalized) stay authoritative — do not let the projection's
        # executing/running fields leak into the completed snapshot.
        for key in ("plan_state", "outline_runtime"):
            if key in plan_patch:
                runtime_patch[key] = plan_patch[key]
    return StepResult(
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch=runtime_patch,
        events=[
            *plan_sync_events,
            *final_answer_events,
            _turn_completed_event(step, status="completed", runtime_snapshot=runtime_patch),
        ],
        activity_summary={"activity_type": "finalize"},
    )


async def _fail_or_cancel(step: WorkflowStepRecord, gateway: AgentRuntimeGateway) -> StepResult:
    status = STEP_STATUS_CANCELLED if step.cancel_requested or step.input.get("cancelled") else STEP_STATUS_FAILED
    run_status = "cancelled" if status == STEP_STATUS_CANCELLED else "failed"
    error_type = str(step.input.get("error_type") or ("Cancelled" if status == STEP_STATUS_CANCELLED else "WorkflowFailed"))
    error_summary = str(step.input.get("error_summary") or run_status)[:500]
    payload = dict(step.input.get("payload") or {})
    await asyncio.to_thread(terminate_critique_run, harness_run_id=step.run_id, status=run_status)
    await gateway.record_activity(
        activity_id=f"run:{step.run_id}:step:{step.step_id}:activity:fail_or_cancel:{step.attempts}",
        activity_type="fail_or_cancel",
        status=run_status,
        attempt=step.attempts,
        error_type=error_type,
        error_summary=error_summary,
    )
    runtime_patch = {
        "runtime_status": run_status,
        "run_state": run_status,
        "turn_status": run_status,
        "failure": {"error_type": error_type, "summary": error_summary} if status == STEP_STATUS_FAILED else None,
    }
    return StepResult(
        status=status,
        runtime_patch=runtime_patch,
        events=[
            _turn_completed_event(
                step,
                status=run_status,
                runtime_snapshot=runtime_patch,
                error=build_turn_error(error_type, error_summary) if status == STEP_STATUS_FAILED else None,
            ),
        ],
        activity_summary={"activity_type": "fail_or_cancel", "status": run_status},
        error=StepError(error_type, error_summary) if status == STEP_STATUS_FAILED else None,
    )


def _is_timeout_error(error_type: str, error_summary: str) -> bool:
    haystack = f"{error_type} {error_summary}".lower()
    return any(marker in haystack for marker in ("timeout", "timed out", "timedout", "deadline"))


async def _not_implemented(step: WorkflowStepRecord, _gateway: AgentRuntimeGateway) -> StepResult:
    return StepResult(
        status=STEP_STATUS_FAILED,
        runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
        error=StepError(
            error_type="WorkflowStepNotImplemented",
            summary=f"workflow step {step.step_type} is not implemented yet",
        ),
    )


HANDLERS: dict[str, StepHandler] = {
    STEP_PREPARE_SKILL: _prepare_skill,
    STEP_DISCOVERY_SCHEMA: _discovery_schema,
    STEP_WAIT_USER_INPUT: _wait_user_input,
    STEP_APPLY_USER_INPUT: _apply_user_input,
    STEP_PREPARE_CONTEXT_SESSION: _prepare_context_session,
    STEP_RENDER_CONTEXT: _render_context,
    STEP_MODEL_TURN: _model_turn,
    STEP_EXECUTE_TOOL: _execute_tool,
    STEP_PERSIST_TOOL_RESULT: _persist_tool_result,
    STEP_PLAN_LIFECYCLE: _plan_lifecycle,
    STEP_FINALIZE: _finalize,
    STEP_FAIL_OR_CANCEL: _fail_or_cancel,
}


def get_step_handler(step_type: str) -> StepHandler:
    return HANDLERS.get(str(step_type), _not_implemented)
