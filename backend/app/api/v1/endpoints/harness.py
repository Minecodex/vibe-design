"""Harness agent API endpoints.

All conversation data (metadata + messages) is stored in workspace directories.
Routes are mounted under /agent/harness.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import uuid
from collections.abc import AsyncGenerator, Callable
from copy import deepcopy
from datetime import timedelta
from functools import partial
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession
from app.core.config import API_V1_STR, SSE_CONVERSATION_MARKER_QUEUE_MAX_SIZE, settings
from app.schemas.harness import (
    AgentUiConfigRead,
    AnalyzeElementRequest,
    AnalyzeElementResponse,
    CloseWorkspaceOfficeSessionRead,
    CloseWorkspaceOfficeSessionRequest,
    CleanupRequest,
    CleanupResultRead,
    CreateHarnessConversationRequest,
    HarnessConversationDetailRead,
    HarnessConversationListRead,
    HarnessConversationRead,
    HarnessDesignSystemDetailRead,
    HarnessDesignSystemRead,
    HarnessGenerationRetryRead,
    HarnessSkillRead,
    OpenWorkspaceOfficeSessionRead,
    OpenWorkspaceOfficeSessionRequest,
    PatchHarnessPlanRequest,
    PlanRevisionRequest,
    RetryHarnessGenerationArtifactRequest,
    ResolveHarnessSelectionRead,
    ResolveHarnessSelectionRequest,
    ResolvedHarnessSelectionItemRead,
    RespondToHarnessAgentRequest,
    SendHarnessMessageRequest,
    WorkspaceFileRead,
    WorkspaceStatsRead,
)
from app.services.agent_harness.capabilities.skills.runtime_profiles import (
    CANVAS_DEFAULT_SKILL_ID,
    canonical_skill_id,
)
from app.services.agent_harness.generation_retry_service import (
    HarnessGenerationRetryNotFoundError,
    HarnessGenerationRetryValidationError,
    retry_generation_artifact,
)

from ._agent_common import get_request_language

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/harness", tags=["harness"])
_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_PREVIEW_TOKEN_TTL_SECONDS = 300
_STREAM_STATUS_POLL_SECONDS = 5.0
_WPS_ADDINS = {
    "WpsOAAssist": "wps",
    "EtOAAssist": "et",
    "WppOAAssist": "wpp",
}


_WPS_ADDIN_VERSION = "1.0.3"
WPS_ADDIN_RIBBON_XML = """<customUI xmlns="http://schemas.microsoft.com/office/2006/01/customui" onLoad="OnWPSWorkTabLoad">
  <ribbon startFromScratch="false">
    <tabs>
      <tab id="AiCodeWpsOpenTab" label="AiCode WPS" />
    </tabs>
  </ribbon>
</customUI>
"""
WPS_ADDIN_INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Ai Code WPS Open</title>
  <script src="./js/index.js"></script>
</head>
<body></body>
</html>
"""
WPS_ADDIN_INDEX_JS = """var aiCodeWpsAddinVersion = "__AICODE_WPS_ADDIN_VERSION__";
var wpsExtReg = /\\.(doc|docx|wps|txt|pdf)$/i;
var etExtReg = /\\.(xls|xlsx|et|csv)$/i;
var wppExtReg = /\\.(ppt|pptx|wpp)$/i;

document.write('<script src="js/dispatcher.js?v=' + aiCodeWpsAddinVersion + '"></script>');
document.write('<script src="js/handler.js?v=' + aiCodeWpsAddinVersion + '"></script>');
"""
WPS_ADDIN_DISPATCHER_JS = """function dispatcher(ops) {
  try {
    var list = ops;
    if (!list) {
      return { status: 1, message: "Missing WPS operations" };
    }
    if (Object.prototype.toString.call(list) !== "[object Array]") {
      list = [list];
    }
    for (var i = 0; i < list.length; i += 1) {
      var op = list[i];
      if (op && op.name === "OpenDoc") {
        OpenFile(op.params);
      }
    }
    return { status: 0, message: "ok" };
  } catch (error) {
    return OnAiCodeOpenFail(error);
  }
}

function OnWPSWorkTabLoad() {
  return true;
}

function OnAiCodeOpenFail(error) {
  var message = error && error.message ? error.message : String(error || "WPS open failed");
  if (typeof wps !== "undefined" && wps && typeof wps.alert === "function") {
    wps.alert(message);
  } else if (typeof alert === "function") {
    alert(message);
  }
  return { status: 1, message: message };
}
"""
WPS_ADDIN_HANDLER_JS = """function OpenFile(url) {
  if (!url) {
    OnAiCodeOpenFail("Missing file url");
    return;
  }
  if (/^https?:/i.test(url)) {
    downloadFile(url, function (path) {
      openLocalFile(path);
    });
    return;
  }
  openLocalFile(url);
}

function downloadFile(url, callback) {
  var xhr = new XMLHttpRequest();
  xhr.onreadystatechange = function () {
    if (xhr.readyState !== 4) {
      return;
    }
    if (xhr.status < 200 || xhr.status >= 300) {
      OnAiCodeOpenFail("Download failed: HTTP " + xhr.status);
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var path = getTempFilePath(url, xhr);
      var ok = wps.FileSystem.writeAsBinaryString(path, reader.result);
      if (!ok) {
        OnAiCodeOpenFail("Downloaded file cannot be written");
        return;
      }
      callback(path);
    };
    reader.onerror = function () {
      OnAiCodeOpenFail("Downloaded file cannot be read");
    };
    reader.readAsBinaryString(xhr.response);
  };
  xhr.onerror = function () {
    OnAiCodeOpenFail("Download request failed");
  };
  xhr.open("GET", url);
  xhr.responseType = "blob";
  xhr.send();
}

function getTempFilePath(url, request) {
  var tempPath = wps.Env.GetTempPath();
  var slash = tempPath.lastIndexOf("/") === tempPath.length - 1 || tempPath.lastIndexOf("\\\\") === tempPath.length - 1 ? "" : "/";
  return tempPath + slash + "aicode_wps_" + new Date().getTime() + "_" + getFileName(url, request);
}

function getFileName(url, request) {
  var disposition = request.getResponseHeader("Content-Disposition") || "";
  var match = /filename\\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition);
  var name = match ? (match[1] || match[2]) : "";
  if (!name) {
    name = String(url).split("?")[0].split("/").pop();
  }
  try {
    name = decodeURIComponent(name);
  } catch (ignore) {}
  name = String(name || "document").replace(/[\\\\/:*?"<>|]/g, "_");
  if (!/\\.[A-Za-z0-9]+$/.test(name)) {
    name += ".tmp";
  }
  return name;
}

function openLocalFile(path) {
  if (wpsExtReg.test(path)) {
    wps.WpsApplication().Documents.Open(path, false, true);
    wps.WpsApplication().Activate();
    wps.WpsApplication().ActiveDocument.Saved = true;
    return;
  }
  if (etExtReg.test(path)) {
    wps.EtApplication().Workbooks.Open(path, false, true);
    return;
  }
  if (wppExtReg.test(path)) {
    wps.WppApplication().Presentations.Open(path, true);
    return;
  }
  OnAiCodeOpenFail("Unsupported file type: " + path);
}
"""
_WPS_ADDIN_STATIC_ASSETS = {
    "ribbon.xml": (WPS_ADDIN_RIBBON_XML, "application/xml"),
    "index.html": (WPS_ADDIN_INDEX_HTML, "text/html"),
    "js/dispatcher.js": (WPS_ADDIN_DISPATCHER_JS, "application/javascript"),
    "js/handler.js": (WPS_ADDIN_HANDLER_JS, "application/javascript"),
}


def _build_preview_file_url(conversation_id: str, relative_path: str, preview_token: str) -> str:
    encoded_path = quote(str(relative_path or "").replace("\\", "/").lstrip("/"), safe="/")
    encoded_token = quote(preview_token, safe="")
    return (
        f"/api/v1/agent/harness/conversations/{conversation_id}/preview-files/"
        f"{encoded_path}?preview_token={encoded_token}"
    )


def _build_wps_addin_base_url(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}{API_V1_STR}/agent/harness/wps-addin"


def _validate_harness_skill_id(skill_id: str | None) -> str | None:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, get_skill_summary_sync

    normalized = canonical_skill_id(skill_id) or None
    if not normalized:
        return None
    try:
        skill = get_skill_summary_sync(normalized)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown harness skill: {normalized}",
        )
    capabilities = skill.capabilities
    if isinstance(capabilities, dict):
        if capabilities.get("phase_enabled") is False:
            reason = str(capabilities.get("classification_notes") or "phase_disabled").strip()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Harness skill is not enabled for this rollout: {normalized} ({reason})",
            )
        if capabilities.get("imported_design_template") and capabilities.get("template_support_state") == "deferred":
            reason = str(capabilities.get("template_deferred_reason") or "deferred").strip()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Harness skill is a deferred imported template: {normalized} ({reason})",
            )
    return normalized


def _get_harness_skill_capabilities(skill_id: str | None) -> dict[str, object]:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, get_skill_summary_sync

    try:
        skill = get_skill_summary_sync(skill_id)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if skill is None:
        return {}
    return dict(skill.capabilities)


def _get_harness_skill_artifact_mode(skill_id: str | None) -> str | None:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, get_skill_summary_sync

    try:
        skill = get_skill_summary_sync(skill_id)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if skill is None:
        return None
    artifact_mode = str(skill.artifact_mode or "").strip().lower()
    return artifact_mode or None


def _list_canvas_explicit_skill_ids() -> list[str]:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, list_skill_summaries_sync

    try:
        skills = list_skill_summaries_sync()
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return sorted(skill.id for skill in skills if skill.capabilities.get("canvas_explicit") is True)

def _normalize_runtime_profile(runtime_profile: str | None) -> str:
    normalized = str(runtime_profile or "home").strip().lower() or "home"
    if normalized not in {"home", "canvas"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported runtime_profile: {normalized}",
        )
    return normalized


def _normalize_canvas_project_id(project_id: int | None) -> int | None:
    if project_id is None:
        return None
    try:
        normalized = int(project_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id must be an integer",
        ) from exc
    if normalized <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id must be a positive integer",
        )
    return normalized


def _resolve_conversation_scope(
    runtime_profile: str | None,
    project_id: int | None,
) -> tuple[str, int | None]:
    normalized_profile = _normalize_runtime_profile(runtime_profile)
    normalized_project_id = _normalize_canvas_project_id(project_id)
    if normalized_profile == "canvas" and normalized_project_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id is required for canvas runtime_profile",
        )
    if normalized_profile == "home":
        return "home", None
    return "canvas", normalized_project_id


def _resolve_skill_for_runtime(
    runtime_profile: str,
    skill_id: str | None,
) -> tuple[str | None, str]:
    normalized_skill_id = _validate_harness_skill_id(skill_id)
    if runtime_profile != "canvas":
        return normalized_skill_id, ("manual" if normalized_skill_id else "auto")

    if normalized_skill_id is None:
        return CANVAS_DEFAULT_SKILL_ID, "auto"
    if _get_harness_skill_capabilities(normalized_skill_id).get("canvas_explicit") is not True:
        allowed = ", ".join(_list_canvas_explicit_skill_ids())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Canvas harness skill must be one of: {allowed}",
        )
    return normalized_skill_id, "manual"


async def _require_canvas_project_access(db, *, user_id: int, project_id: int):
    from app.services.project_service import ProjectService

    return await ProjectService(db).get(project_id, user_id, is_admin=False)


@router.get("/ui-config", response_model=AgentUiConfigRead)
async def get_harness_ui_config():
    return AgentUiConfigRead(
        hidden_tool_calls=settings.agent_hidden_tool_calls,
        canvas_default_skill_id=CANVAS_DEFAULT_SKILL_ID,
        canvas_explicit_skill_ids=_list_canvas_explicit_skill_ids(),
    )


@router.post("/analyze-element", response_model=AnalyzeElementResponse)
async def analyze_element(
    data: AnalyzeElementRequest,
    db: DbSession = None,
    user: CurrentUser = None,
):
    import re as _re

    from app.core.default_models import (
        get_default_mark_recognition_model,
        get_default_mark_recognition_provider,
    )
    from app.services.agent_harness.core.utils.media_utils import resolve_url_for_api
    from app.services.multimodal_service import MultimodalService

    svc = MultimodalService(db)
    resolved = resolve_url_for_api(data.image_url, prefer="base64")
    resolved_debug = (resolved or {}).get("debug", {}) if isinstance(resolved, dict) else {}

    if resolved and resolved["type"] == "base64":
        image_url = f"data:{resolved['mime_type']};base64,{resolved['data']}"
    elif resolved and resolved["type"] == "url":
        image_url = resolved["url"]
    else:
        image_url = data.image_url

    lang = data.language or "zh"
    prompt = (
        f"I have placed a marker on this image at approximately "
        f"({data.relative_x:.0%} from left, {data.relative_y:.0%} from top). "
        f"What object or element is at or near this marked position? "
        f"Return a JSON array of 1-3 possible object/element names in {'Chinese' if lang == 'zh' else 'English'}. "
        f'Format: ["object1", "object2", ...]. Only return the JSON array, nothing else.'
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]
    model_name = get_default_mark_recognition_model()
    provider_code = get_default_mark_recognition_provider()

    logger.info(
        "Mark recognition image prepared: user_id=%s source_kind=%s resolved_kind=%s "
        "original_size=%s processed_size=%s original_bytes=%s processed_bytes=%s "
        "base64_chars=%s mime_type=%s image_url_kind=%s model=%s provider=%s",
        getattr(user, "id", None),
        resolved_debug.get("source_kind"),
        resolved_debug.get("resolved_kind"),
        resolved_debug.get("original_size"),
        resolved_debug.get("processed_size"),
        resolved_debug.get("original_bytes"),
        resolved_debug.get("processed_bytes"),
        resolved_debug.get("base64_chars"),
        resolved.get("mime_type") if isinstance(resolved, dict) else None,
        resolved.get("type") if isinstance(resolved, dict) else "raw",
        model_name,
        provider_code,
    )

    try:
        result = await svc.chat(
            user_id=user.id,
            model_name=model_name,
            provider_code=provider_code,
            messages=messages,
            task_type="mark_recognition",
            billing_label="billing.labels.mark_recognition",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Element analysis failed")
        raise HTTPException(status_code=500, detail=f"Element analysis failed: {str(exc)}") from exc

    choices = result.get("choices", [])
    labels: list[str] = []
    if choices:
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
        text = message.get("content", "") if isinstance(message, dict) else ""

        logger.info(
            "Mark recognition raw response: finish_reason=%s content_type=%s content_preview=%s",
            first_choice.get("finish_reason") if isinstance(first_choice, dict) else None,
            type(text).__name__,
            str(text)[:500],
        )
        if isinstance(text, list):
            text = "\n".join(
                str(part.get("text") or "")
                for part in text
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if isinstance(text, str):
            match = _re.search(r"\[[\s\S]*\]", text)
            payload = match.group(0) if match else text
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                labels = [str(item).strip() for item in parsed if str(item).strip()][:3]

    return AnalyzeElementResponse(labels=labels or ["unknown"])


def _validate_harness_design_system_id(design_system_id: str | None) -> str | None:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, get_design_system_summary_sync

    normalized = str(design_system_id or "").strip() or None
    if not normalized:
        return None
    try:
        design_system = get_design_system_summary_sync(normalized)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if design_system is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown design system: {normalized}",
        )
    return normalized


def _validate_artifact_mode(artifact_mode: str | None) -> str:
    from app.services.agent_harness.capabilities.skills.router import normalize_artifact_mode

    return normalize_artifact_mode(artifact_mode)


def _rederive_harness_phase(conversation: dict) -> str:
    from app.services.agent_harness.runtime.execution_support.plan_gate_controller import PlanGateController

    return PlanGateController.initial_phase(conversation)


def _phase_diagnostic_payload(
    conversation: dict,
    *,
    source: str,
    derived_phase: str | None = None,
    request_fields: set[str] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    plan_state = conversation.get("plan_state")
    plan_state_payload: dict[str, object] = {
        "plan_state_type": "none" if plan_state is None else type(plan_state).__name__,
        "plan_state_truthy": bool(plan_state),
        "has_valid_plan_state": isinstance(plan_state, dict),
    }
    if isinstance(plan_state, dict):
        plan_state_payload["plan_state_status"] = str(plan_state.get("status") or "")
        plan_state_payload["plan_state_keys"] = sorted(str(key) for key in plan_state.keys())

    payload: dict[str, object] = {
        "source": source,
        "conversation_phase": str(conversation.get("phase") or ""),
        "derived_phase": str(derived_phase or ""),
        "artifact_mode": str(conversation.get("artifact_mode") or ""),
        "skill_id": str(conversation.get("skill_id") or ""),
        "resolved_skill_id": str(conversation.get("resolved_skill_id") or ""),
        "skill_selection_mode": str(conversation.get("skill_selection_mode") or ""),
        "skill_resolution_source": str(conversation.get("skill_resolution_source") or ""),
        "runtime_status": str(conversation.get("runtime_status") or ""),
        "run_state": str(conversation.get("run_state") or ""),
        "turn_status": str(conversation.get("turn_status") or ""),
        **plan_state_payload,
    }
    if request_fields is not None:
        payload["request_fields"] = sorted(str(field) for field in request_fields)
    if extra:
        payload.update(extra)
    return payload


def _selection_source(selection_mode: str | None, value: str | None, *, manual_source: str, auto_source: str) -> str | None:
    normalized_mode = str(selection_mode or "").strip().lower()
    if normalized_mode == "manual":
        return manual_source if value else None
    if normalized_mode == "auto":
        return auto_source if value else None
    return None


def _materialize_internal_hidden_skills(internal_skill_ids: list[str] | None) -> list[dict[str, str]]:
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, get_skill_summary_sync

    materialized: list[dict[str, str]] = []
    for raw_skill_id in list(internal_skill_ids or []):
        try:
            skill = get_skill_summary_sync(raw_skill_id)
        except AgentCatalogUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if skill is None:
            continue
        materialized.append(
            {
                "id": skill.id,
                "activation_source": "ai_resolved",
            }
        )
    return materialized


def _persist_internal_hidden_skill_activation(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
    selected_skill_id: str | None,
    internal_skill_ids: list[str] | None,
    language: str,
) -> None:
    from app.services.agent_harness.workspace.conversation.conversation_service import (
        build_internal_skill_activation_message,
    )
    from app.services.agent_harness.workspace.session_v2.service import get_conversation, patch_runtime_state

    normalized_selected_skill_id = str(selected_skill_id or "").strip() or None
    if not normalized_selected_skill_id:
        return

    internal_hidden_skills = _materialize_internal_hidden_skills(internal_skill_ids)
    current = get_conversation(user_id, conversation_id) or conversation
    runtime_state = current.get("runtime_state") if isinstance(current.get("runtime_state"), dict) else {}
    existing_contract = dict(runtime_state.get("runtime_contract") or {}) if isinstance(runtime_state, dict) else {}
    existing_session = dict(runtime_state.get("workspace_runtime_session") or {}) if isinstance(runtime_state, dict) else {}
    previous_internal_ids = [
        str(item.get("id") or "").strip()
        for item in list(existing_contract.get("internal_hidden_skills") or [])
        if isinstance(item, dict)
    ]
    existing_contract["internal_hidden_skill_resolution"] = {
        "selected_skill_id": normalized_selected_skill_id,
        "resolved": True,
    }
    existing_contract["internal_hidden_skills"] = internal_hidden_skills
    existing_session["selected_skill"] = normalized_selected_skill_id
    existing_session["internal_hidden_skill_resolution"] = {
        "selected_skill_id": normalized_selected_skill_id,
        "resolved": True,
    }
    existing_session["internal_hidden_skills"] = internal_hidden_skills
    next_runtime_state = {
        **(conversation.get("runtime_state") if isinstance(conversation.get("runtime_state"), dict) else {}),
        "runtime_contract": existing_contract,
        "workspace_runtime_session": existing_session,
    }
    patch_runtime_state(user_id, conversation_id, {"runtime_state": next_runtime_state}, touch_updated_at=False)
    conversation["runtime_state"] = next_runtime_state
    next_internal_ids = [str(item.get("id") or "").strip() for item in internal_hidden_skills]
    if next_internal_ids and next_internal_ids != previous_internal_ids:
        pending_message = build_internal_skill_activation_message(
            selected_skill_id=normalized_selected_skill_id,
            internal_skill_ids=next_internal_ids,
            language=language,
        )
        if pending_message:
            conversation["_pending_internal_hidden_skill_announcement_message"] = pending_message


def _read_conversation_runtime_state(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
) -> dict[str, Any]:
    runtime_state = conversation.get("runtime_state")
    if isinstance(runtime_state, dict):
        return runtime_state
    from app.services.agent_harness.workspace.session_v2.service import get_conversation

    loaded = get_conversation(user_id, conversation_id) or {}
    loaded_state = loaded.get("runtime_state")
    if isinstance(loaded_state, dict):
        conversation["runtime_state"] = loaded_state
        return loaded_state
    return {}


def _latched_internal_hidden_skill_ids(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
    selected_skill_id: str | None,
) -> tuple[bool, list[str]]:
    normalized_selected_skill_id = str(selected_skill_id or "").strip() or None
    if not normalized_selected_skill_id:
        return False, []
    runtime_state = _read_conversation_runtime_state(
        user_id=user_id,
        conversation_id=conversation_id,
        conversation=conversation,
    )
    runtime_contract = runtime_state.get("runtime_contract") if isinstance(runtime_state.get("runtime_contract"), dict) else {}
    workspace_session = (
        runtime_state.get("workspace_runtime_session")
        if isinstance(runtime_state.get("workspace_runtime_session"), dict)
        else {}
    )
    resolution = runtime_contract.get("internal_hidden_skill_resolution") if isinstance(runtime_contract, dict) else None
    latched_selected_skill_id = str((workspace_session or {}).get("selected_skill") or "").strip() or None
    if isinstance(resolution, dict):
        latched_selected_skill_id = str(resolution.get("selected_skill_id") or latched_selected_skill_id or "").strip() or None
        if resolution.get("resolved") and (
            latched_selected_skill_id is None or latched_selected_skill_id == normalized_selected_skill_id
        ):
            return True, [
                str(item.get("id") or "").strip()
                for item in list(runtime_contract.get("internal_hidden_skills") or [])
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]
        return False, []
    if latched_selected_skill_id and latched_selected_skill_id != normalized_selected_skill_id:
        return False, []
    existing_ids = [
        str(item.get("id") or "").strip()
        for item in list(runtime_contract.get("internal_hidden_skills") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if existing_ids:
        return True, existing_ids
    return False, []


def _clear_internal_hidden_skill_activation_state(
    *,
    user_id: int,
    conversation_id: str,
    conversation: dict[str, Any],
) -> None:
    from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

    runtime_state = _read_conversation_runtime_state(
        user_id=user_id,
        conversation_id=conversation_id,
        conversation=conversation,
    )
    existing_contract = dict(runtime_state.get("runtime_contract") or {}) if isinstance(runtime_state, dict) else {}
    existing_session = dict(runtime_state.get("workspace_runtime_session") or {}) if isinstance(runtime_state, dict) else {}
    existing_contract.pop("internal_hidden_skills", None)
    existing_contract.pop("internal_hidden_skill_resolution", None)
    existing_session.pop("selected_skill", None)
    existing_session.pop("internal_hidden_skills", None)
    existing_session.pop("internal_hidden_skill_resolution", None)
    next_runtime_state = {
        **(conversation.get("runtime_state") if isinstance(conversation.get("runtime_state"), dict) else {}),
        "runtime_contract": existing_contract,
        "workspace_runtime_session": existing_session,
    }
    patch_runtime_state(user_id, conversation_id, {"runtime_state": next_runtime_state}, touch_updated_at=False)
    conversation["runtime_state"] = next_runtime_state


def _validate_harness_preview_token(preview_token: str, conversation_id: str) -> int:
    from app.core.security import decode_token

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(preview_token)
    except ValueError as exc:
        raise credentials_exception from exc

    if payload.get("type") != "harness_preview":
        raise credentials_exception
    if str(payload.get("conversation_id") or "") != str(conversation_id):
        raise credentials_exception

    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise credentials_exception from exc


@router.get("/wps-addin/jsplugins.xml")
async def get_wps_addin_manifest(request: Request):
    base_url = _build_wps_addin_base_url(request)
    plugin_lines = [
        (
            f'  <jspluginonline name="{escape(name)}" type="{escape(addon_type)}" '
            f'url="{escape(base_url)}/{escape(name)}/" version="{escape(_WPS_ADDIN_VERSION)}" />'
        )
        for name, addon_type in _WPS_ADDINS.items()
    ]
    body = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<jsplugins>",
        *plugin_lines,
        "</jsplugins>",
        "",
    ])
    return Response(content=body, media_type="application/xml")


@router.get("/wps-addin/{addon_name}/{asset_path:path}")
async def get_wps_addin_asset(addon_name: str, asset_path: str):
    if addon_name not in _WPS_ADDINS:
        raise HTTPException(status_code=404, detail="WPS add-in not found")

    normalized_asset = str(asset_path or "").strip().replace("\\", "/").lstrip("/").lower()
    if ".." in normalized_asset.split("/"):
        raise HTTPException(status_code=404, detail="WPS add-in asset not found")
    if normalized_asset == "js/index.js":
        return Response(
            content=WPS_ADDIN_INDEX_JS.replace("__AICODE_WPS_ADDIN_VERSION__", _WPS_ADDIN_VERSION),
            media_type="application/javascript",
        )

    static_asset = _WPS_ADDIN_STATIC_ASSETS.get(normalized_asset)
    if static_asset:
        content, media_type = static_asset
        if media_type == "text/html":
            return HTMLResponse(content)
        return Response(content=content, media_type=media_type)

    raise HTTPException(status_code=404, detail="WPS add-in asset not found")


async def _stream_live_events(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    transient_queue: asyncio.Queue[dict] | None = None,
    unsubscribe: Callable[[], None] | None = None,
) -> AsyncGenerator[str, None]:
    from app.services.agent_harness.runtime.eventing.conversation_stream_session import stream_conversation_events

    async for chunk in stream_conversation_events(
        user_id,
        conversation_id,
        after_sequence=after_sequence,
        transient_queue=transient_queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=_STREAM_STATUS_POLL_SECONDS,
    ):
        yield chunk


def _subscribe_live_user_events(
    user_id: int,
    conversation_id: str,
) -> tuple[asyncio.Queue[dict], Callable[[], None]]:
    from app.services.agent_harness.runtime.eventing.event_log import subscribe_to_events
    from app.services.sse_queue import bounded_queue

    loop = asyncio.get_running_loop()
    transient_queue: asyncio.Queue[dict] = bounded_queue(SSE_CONVERSATION_MARKER_QUEUE_MAX_SIZE)

    def _on_event(event: dict) -> None:
        if str(event.get("lane") or "user") != "user":
            return
        _enqueue_live_user_event(loop, transient_queue, {"lane": "user"})

    return transient_queue, subscribe_to_events(user_id, conversation_id, _on_event)


def _enqueue_live_user_event(
    loop: asyncio.AbstractEventLoop,
    transient_queue: asyncio.Queue[dict],
    event: dict,
) -> None:
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is loop:
        from app.services.sse_queue import put_marker_nowait

        put_marker_nowait(transient_queue, event, name="conversation.marker")
        return

    from app.services.sse_queue import put_marker_nowait

    loop.call_soon_threadsafe(partial(put_marker_nowait, transient_queue, event, name="conversation.marker"))


def _build_live_streaming_response(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    run_id: str | None = None,
    request_id: int | None = None,
) -> StreamingResponse:
    del run_id, request_id
    return StreamingResponse(
        _stream_live_events(
            user_id,
            conversation_id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


# ------------------------------------------------------------------
# Conversations (directory-based)
# ------------------------------------------------------------------


@router.get("/conversations", response_model=HarnessConversationListRead)
async def list_conversations(
    user: CurrentUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
    runtime_profile: str = "home",
    project_id: int | None = None,
):
    """List harness conversations with pagination."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        list_conversations as list_convs,
    )
    normalized_runtime_profile, normalized_project_id = _resolve_conversation_scope(
        runtime_profile,
        project_id,
    )
    if normalized_runtime_profile == "canvas" and normalized_project_id is not None:
        await _require_canvas_project_access(db, user_id=user.id, project_id=normalized_project_id)
    items, total = list_convs(
        user.id,
        runtime_profile=normalized_runtime_profile,
        project_id=normalized_project_id,
        page=page,
        page_size=page_size,
    )
    return HarnessConversationListRead(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.post("/conversations", response_model=HarnessConversationRead)
async def create_conversation(
    data: CreateHarnessConversationRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Create a new harness conversation with workspace isolation."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        create_conversation as create_harness_conv,
        normalize_runtime_meta,
    )
    runtime_profile, project_id = _resolve_conversation_scope(
        data.runtime_profile,
        data.project_id,
    )
    if runtime_profile == "canvas" and project_id is not None:
        await _require_canvas_project_access(db, user_id=user.id, project_id=project_id)
    skill_id, default_skill_selection_mode = _resolve_skill_for_runtime(
        runtime_profile,
        data.skill_id,
    )
    artifact_mode = _validate_artifact_mode(data.artifact_mode)
    if runtime_profile == "canvas" and skill_id:
        artifact_mode = _get_harness_skill_artifact_mode(skill_id) or artifact_mode
    design_system_id = _validate_harness_design_system_id(data.design_system_id)
    if data.skill_selection_mode in {"auto", "manual"}:
        skill_selection_mode = data.skill_selection_mode
    else:
        skill_selection_mode = default_skill_selection_mode
    conv = create_harness_conv(
        user_id=user.id,
        title="新会话",
        runtime_profile=runtime_profile,
        project_id=project_id,
        skill_id=skill_id,
        resolved_skill_id=skill_id,
        skill_resolution_source=_selection_source(
            skill_selection_mode,
            skill_id,
            manual_source="user_selected",
            auto_source="ai_resolved",
        ),
        skill_selection_mode=skill_selection_mode,
        artifact_mode=artifact_mode,
        design_system_id=design_system_id,
        mode=data.mode,
        web_search_enabled=data.web_search_enabled,
        model_preferences=data.model_preferences,
    )
    return normalize_runtime_meta(dict(conv))


@router.get("/conversations/{conversation_id}", response_model=HarnessConversationDetailRead)
async def get_conversation(
    conversation_id: str,
    user: CurrentUser,
):
    """Get harness conversation detail with messages (from directory)."""
    from app.services.agent_harness.workspace.conversation.conversation_snapshot import build_conversation_detail_snapshot

    snapshot = build_conversation_detail_snapshot(user.id, conversation_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        return HarnessConversationDetailRead(**snapshot)
    except ValidationError as exc:
        logger.exception(
            "Conversation snapshot failed schema validation: user=%s conversation=%s",
            user.id,
            conversation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Conversation snapshot schema mismatch", "errors": exc.errors()},
        ) from exc


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser,
):
    """Delete a harness conversation and its workspace."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        delete_conversation as delete_conv,
    )
    from app.services.agent_harness.runtime.eventing.event_log import clear_conversation_event_caches
    deleted = delete_conv(user.id, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    clear_conversation_event_caches(user.id, conversation_id)
    return {"ok": True}


@router.post("/conversations/{conversation_id}/cancel", response_model=HarnessConversationDetailRead)
async def cancel_conversation(
    conversation_id: str,
    user: CurrentUser,
):
    """Request cancellation of an active harness run."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
        update_conversation as update_conv,
    )
    from app.services.agent_harness.workspace.conversation.conversation_snapshot import (
        build_conversation_detail_snapshot,
    )
    from app.services.agent_harness.agent_coordination.run_wakeup_bus import wake_agent_run_worker
    from app.services.agent_harness.agent_run.control.active_run_guard import has_active_agent_run
    from app.services.agent_harness.workflow.repositories import request_cancel
    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.runtime.eventing.turn_protocol import (
        TURN_COMPLETED,
        build_turn_completed_payload,
    )
    from app.services.agent_harness.runtime.state.store_core import utc_now

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from app.services.agent_harness.workspace.conversation.home_turn_router import route_from_ui_action

    turn_route = route_from_ui_action(action_type="cancel")
    update_conv(user.id, conversation_id, turn_route=turn_route, activity=turn_route.get("activity"))

    if request_cancel(conversation_id, reason="user"):
        if not has_active_agent_run(conversation_id):
            update_conv(
                user.id,
                conversation_id,
                runtime_status="cancelled",
                run_state="cancelled",
                turn_status="cancelled",
                activity="cancelled",
                user_interaction=None,
                finished_at=utc_now(),
            )
        else:
            update_conv(
                user.id,
                conversation_id,
                run_state="cancelling",
                turn_status="cancelling",
                activity="cancelling",
            )
        await wake_agent_run_worker()
    elif str(conv.get("runtime_status") or "").lower() == "waiting_input":
        update_conv(
            user.id,
            conversation_id,
            runtime_status="cancelled",
            run_state="cancelled",
            turn_status="cancelled",
            activity="cancelled",
            user_interaction=None,
            finished_at=utc_now(),
        )
        append_event(
            user_id=user.id,
            conversation_id=conversation_id,
            run_id=str(conv.get("run_id") or ""),
            event_type=TURN_COMPLETED,
            data=build_turn_completed_payload(
                conversation_id=conversation_id,
                run_id=str(conv.get("run_id") or ""),
                status="cancelled",
                runtime_snapshot={
                    "runtime_status": "cancelled",
                    "run_state": "cancelled",
                    "turn_status": "cancelled",
                    "activity": "cancelled",
                    "user_interaction": None,
                },
            ),
            lane="user",
            idempotency_key=f"run:{conv.get('run_id') or ''}:turn-completed",
        )
    snapshot = build_conversation_detail_snapshot(user.id, conversation_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return snapshot


@router.get("/conversations/{conversation_id}/stream")
async def stream_harness_events(
    conversation_id: str,
    user: CurrentUser,
    after_sequence: int | None = None,
):
    """Stream live harness UI events for an already-running conversation."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
    )

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return StreamingResponse(
        _stream_live_events(
            user.id,
            conversation_id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


# ------------------------------------------------------------------
# Messages (SSE streaming)
# ------------------------------------------------------------------


@router.get("/conversations/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: str,
    user: CurrentUser,
    before_seq: int | None = None,
    limit: int = 80,
):
    """Page older homepage-visible messages without loading the detail snapshot."""
    from app.services.agent_harness.workspace.session_v2.service import read_ui_messages_page
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation as get_conv

    if not get_conv(user.id, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    safe_limit = max(1, min(int(limit or 80), 200))
    return read_ui_messages_page(user.id, conversation_id, before_seq=before_seq, limit=safe_limit)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    data: SendHarnessMessageRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    after_sequence: int | None = None,
):
    """Send a user message and stream the harness agent response via SSE."""
    from app.services.agent_harness.workspace.conversation.send_message_service import (
        HarnessSendMessageDependencies,
        send_harness_message,
    )

    return await send_harness_message(
        conversation_id=conversation_id,
        data=data,
        request=request,
        db=db,
        user=user,
        after_sequence=after_sequence,
        deps=HarnessSendMessageDependencies(
            get_request_language=get_request_language,
            validate_harness_skill_id=_validate_harness_skill_id,
            selection_source=_selection_source,
            rederive_harness_phase=_rederive_harness_phase,
            clear_internal_hidden_skill_activation_state=_clear_internal_hidden_skill_activation_state,
            validate_artifact_mode=_validate_artifact_mode,
            validate_design_system_id=_validate_harness_design_system_id,
            phase_diagnostic_payload=_phase_diagnostic_payload,
            require_canvas_project_access=_require_canvas_project_access,
            build_live_streaming_response=_build_live_streaming_response,
            latched_internal_hidden_skill_ids=_latched_internal_hidden_skill_ids,
            persist_internal_hidden_skill_activation=_persist_internal_hidden_skill_activation,
        ),
    )


@router.post("/resolve-selection", response_model=ResolveHarnessSelectionRead)
async def resolve_harness_selection(
    data: ResolveHarnessSelectionRequest,
    user: CurrentUser,
):
    from app.services.agent_harness.authoring.planning.decision_resolver import resolve_selection
    from app.services.agent_harness.workspace.conversation.preflight_lifecycle_service import (
        persist_skill_resolution,
    )

    conversation = None
    if data.conversation_id:
        from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation as get_conv

        conversation = get_conv(user.id, data.conversation_id)

    result = await resolve_selection(
        artifact_mode=_validate_artifact_mode(data.artifact_mode),
        prompt=data.prompt,
        attachments=data.attachments,
        current_skill_id=_validate_harness_skill_id(data.current_skill_id),
        resolve_skill=data.resolve_skill,
        model_preferences=data.model_preferences or ((conversation or {}).get("model_preferences") if conversation else None),
    )
    preflight_model_calls = list(getattr(result, "preflight_model_calls", []) or [])
    if conversation is not None and preflight_model_calls:
        from app.services.agent_harness.workspace.conversation.turns.preflight_billing import (
            record_turn_preflight_model_calls,
        )
        from app.services.agent_harness.workspace.conversation.turns.turn_preparation import (
            build_turn_idempotency_key,
        )

        # The resolve-selection endpoint is idempotent on the same prompt /
        # current skill / attachments. We tag preflight charges with a stable
        # key derived from those inputs so client retries dedupe at the DB.
        resolve_idempotency_key = build_turn_idempotency_key(
            "resolve_selection",
            data.conversation_id or "",
            data.prompt,
            data.attachments,
            _validate_harness_skill_id(data.current_skill_id),
            bool(data.resolve_skill),
            _validate_artifact_mode(data.artifact_mode or conversation.get("artifact_mode")),
        )
        parent_usage_log_id = await record_turn_preflight_model_calls(
            user_id=user.id,
            conversation=conversation,
            artifact_mode=_validate_artifact_mode(data.artifact_mode or conversation.get("artifact_mode")),
            run_id=str(conversation.get("run_id") or "selection-resolver"),
            preflight_model_calls=preflight_model_calls,
            turn_idempotency_key=resolve_idempotency_key,
        )
        if parent_usage_log_id is not None:
            conversation["parent_usage_log_id"] = parent_usage_log_id
    if conversation is not None and data.resolve_skill and result.skill is not None:
        persist_skill_resolution(
            user_id=user.id,
            conversation_id=str(conversation["id"]),
            previous_skill_id=conversation.get("skill_id"),
            next_skill_id=result.skill.id,
            artifact_mode=_validate_artifact_mode(data.artifact_mode or conversation.get("artifact_mode")),
            model_preferences=data.model_preferences or conversation.get("model_preferences"),
            reason=result.skill.reasoning_summary,
            confidence=result.skill.confidence,
            language="zh",
        )
    return ResolveHarnessSelectionRead(
        skill=(
            ResolvedHarnessSelectionItemRead(
                id=result.skill.id,
                confidence=result.skill.confidence,
                reasoning_summary=result.skill.reasoning_summary,
                should_replace_current=result.skill.should_replace_current,
            )
            if result.skill is not None
            else None
        ),
    )


# ------------------------------------------------------------------
# Respond to ask_user interaction
# ------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/respond")
async def respond_to_agent(
    conversation_id: str,
    data: RespondToHarnessAgentRequest,
    request: Request,
    user: CurrentUser,
    after_sequence: int | None = None,
):
    """Respond to a harness agent ask_user question and resume execution."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
        update_conversation as update_conv,
    )
    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_resume_interaction_run
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.workflow.repositories import get_active_run_for_conversation
    from app.services.agent_harness.workflow.status import RUN_STATUS_WAITING_INPUT
    from app.services.agent_harness.workspace.conversation.turns.interaction_turn import prepare_resume_interaction_payload
    from app.services.agent_harness.workspace.conversation.turns.turn_preparation import build_turn_idempotency_key
    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    lang = get_request_language(request)

    runtime_state = conv.get("runtime_state") if isinstance(conv.get("runtime_state"), dict) else {}
    if isinstance(runtime_state, dict) and bool(runtime_state.get("cancel_requested")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation cancellation already requested",
        )
    pending = runtime_state.get("user_interaction") if isinstance(runtime_state, dict) else None
    if not isinstance(pending, dict):
        pending = conv.get("user_interaction") if isinstance(conv.get("user_interaction"), dict) else None
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending interaction",
        )
    pending_kind = str(pending.get("kind") or "").strip()
    pending_schema = pending.get("schema") if isinstance(pending.get("schema"), dict) else {}
    pending_questions = pending_schema.get("questions")
    if pending_kind == "ask_user" and (not isinstance(pending_questions, list) or len(pending_questions) == 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported legacy ask_user interaction",
        )

    active_run = get_active_run_for_conversation(conversation_id)
    if active_run is not None and active_run.status != RUN_STATUS_WAITING_INPUT:
        raise HTTPException(status_code=409, detail="Conversation already has an active run")

    from app.services.agent_harness.authoring.planning.discovery_runtime import normalize_interaction_answers

    normalized_answers = normalize_interaction_answers(
        raw_answers=data.answers,
        answer=data.answer,
        display_label=data.display_label,
        pending_interaction=pending,
    )
    from app.services.agent_harness.workspace.conversation.home_turn_router import (
        route_after_interaction_submission,
    )

    turn_route = route_after_interaction_submission(
        conversation=conv,
        pending_interaction=pending,
    )
    conv["turn_route"] = turn_route
    conv["activity"] = turn_route.get("activity")

    try:
        run_request = await enqueue_resume_interaction_run(
            user_id=user.id,
            conversation_id=conversation_id,
            payload=prepare_resume_interaction_payload(
                conversation=conv,
                request_id=data.request_id,
                answer=data.answer,
                answers=normalized_answers,
                display_label=data.display_label,
                approved=data.approved,
                language=lang,
            ),
            idempotency_key=build_turn_idempotency_key(
                "resume",
                conversation_id,
                data.request_id,
                data.answer,
                normalized_answers,
                data.display_label,
                data.approved,
            ),
        )
    except AgentRunAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail="Conversation already has an active run") from exc

    update_conv(user.id, conversation_id, turn_route=turn_route, activity=turn_route.get("activity"))
    append_event(
        user_id=user.id,
        conversation_id=conversation_id,
        run_id=run_request.run_id,
        event_type="interaction_submitted",
        data={
            "request_id": data.request_id,
            "question": pending.get("question") or "",
            "kind": pending.get("kind") or None,
            "schema": pending.get("schema") if isinstance(pending.get("schema"), dict) else None,
            "answer": data.answer,
            "answers": normalized_answers,
            "display_label": data.display_label or data.answer,
            "approved": data.approved,
        },
        idempotency_key=build_turn_idempotency_key(
            "interaction_submitted",
            conversation_id,
            data.request_id,
            data.answer,
            normalized_answers,
            data.display_label,
            data.approved,
        ),
    )

    return _build_live_streaming_response(
        user.id,
        conversation_id,
        after_sequence=after_sequence,
        run_id=run_request.run_id,
        request_id=run_request.id,
    )


@router.post("/conversations/{conversation_id}/plan/start")
async def start_plan_execution(
    conversation_id: str,
    request: Request,
    user: CurrentUser,
    after_sequence: int | None = None,
):
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation as get_conv, update_conversation as update_conv
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_start_plan_run
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.workflow.repositories import get_active_run_for_conversation
    from app.services.agent_harness.workflow.status import RUN_STATUS_WAITING_INPUT
    from app.services.agent_harness.workspace.conversation.turns.plan_turn import (
        build_plan_execution_approval_user_event,
        plan_execution_approval_user_event,
        prepare_start_plan_payload,
    )

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    active_run = get_active_run_for_conversation(conversation_id)
    if active_run is not None and active_run.status != RUN_STATUS_WAITING_INPUT:
        raise HTTPException(status_code=409, detail="Conversation already has an active run")
    phase = str(conv.get("phase") or "").strip().lower()
    if phase not in {"planning_ready", "awaiting_plan_review"}:
        raise HTTPException(status_code=409, detail="Plan is not waiting for execution approval")
    outline_runtime = conv.get("outline_runtime") if isinstance(conv.get("outline_runtime"), dict) else None
    outline_state = outline_runtime.get("current_outline") if isinstance(outline_runtime, dict) else None
    execution_state = outline_runtime.get("execution_state") if isinstance(outline_runtime, dict) else None
    if not isinstance(outline_state, dict):
        raise HTTPException(status_code=409, detail="Current outline is required before starting execution")
    if not isinstance(execution_state, dict) or str(execution_state.get("status") or "").strip().lower() != "planning_ready":
        raise HTTPException(status_code=409, detail="Approved execution plan is required before starting execution")
    lang = get_request_language(request)
    approval_message = await build_plan_execution_approval_user_event(
        conversation_id=conversation_id,
        conversation=conv,
        language=lang,
    )
    from app.services.agent_harness.workspace.conversation.home_turn_router import route_from_ui_action

    turn_route = route_from_ui_action(action_type="plan_start")
    update_conv(user.id, conversation_id, turn_route=turn_route, activity=turn_route.get("activity"))
    conv["turn_route"] = turn_route
    conv["activity"] = turn_route.get("activity")

    try:
        run_request = await enqueue_start_plan_run(
            user_id=user.id,
            conversation_id=conversation_id,
            payload=prepare_start_plan_payload(
                conversation=conv,
                language=lang,
                turn_route=turn_route,
                user_message_event=plan_execution_approval_user_event(approval_message),
            ),
            idempotency_key=f"plan_start:{conversation_id}:{lang}",
            priority=5,
        )
    except AgentRunAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail="Conversation already has an active run") from exc

    return _build_live_streaming_response(
        user.id,
        conversation_id,
        after_sequence=after_sequence,
        run_id=run_request.run_id,
        request_id=run_request.id,
    )

@router.post("/conversations/{conversation_id}/plan/revise")
async def revise_plan(
    conversation_id: str,
    data: PlanRevisionRequest,
    request: Request,
    user: CurrentUser,
    after_sequence: int | None = None,
):
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation as get_conv, update_conversation as update_conv
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_revise_plan_run
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.workflow.repositories import get_active_run_for_conversation
    from app.services.agent_harness.workflow.status import RUN_STATUS_WAITING_INPUT
    from app.services.agent_harness.workspace.conversation.turns.plan_turn import prepare_revise_plan_payload
    from app.services.agent_harness.workspace.conversation.turns.turn_preparation import build_turn_idempotency_key

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    active_run = get_active_run_for_conversation(conversation_id)
    if active_run is not None and active_run.status != RUN_STATUS_WAITING_INPUT:
        raise HTTPException(status_code=409, detail="Conversation already has an active run")
    phase = str(conv.get("phase") or "").strip().lower()
    if phase not in {"planning_ready", "awaiting_plan_review", "revising_plan"}:
        raise HTTPException(status_code=409, detail="Plan is not available for revision")
    lang = get_request_language(request)
    from app.services.agent_harness.workspace.conversation.home_turn_router import route_from_ui_action

    turn_route = route_from_ui_action(action_type="revise_plan")
    update_conv(user.id, conversation_id, turn_route=turn_route, activity=turn_route.get("activity"))
    conv["turn_route"] = turn_route
    conv["activity"] = turn_route.get("activity")

    try:
        run_request = await enqueue_revise_plan_run(
            user_id=user.id,
            conversation_id=conversation_id,
            payload=prepare_revise_plan_payload(
                conversation=conv,
                instruction=data.instruction,
                language=lang,
                turn_route=turn_route,
            ),
            idempotency_key=build_turn_idempotency_key("plan_revise", conversation_id, data.instruction),
            priority=5,
        )
    except AgentRunAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail="Conversation already has an active run") from exc

    return _build_live_streaming_response(
        user.id,
        conversation_id,
        after_sequence=after_sequence,
        run_id=run_request.run_id,
        request_id=run_request.id,
    )


@router.post("/conversations/{conversation_id}/plan/patch", response_model=HarnessConversationDetailRead)
async def patch_plan(
    conversation_id: str,
    data: PatchHarnessPlanRequest,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation as get_conv, update_conversation as update_conv
    from app.services.agent_harness.workspace.conversation.conversation_snapshot import build_conversation_detail_snapshot
    from app.services.agent_harness.workspace.conversation.turns.plan_turn import apply_manual_plan_patch

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from app.services.agent_harness.workspace.conversation.home_turn_router import route_from_ui_action

    turn_route = route_from_ui_action(action_type="patch_plan")
    update_conv(user.id, conversation_id, turn_route=turn_route, activity=turn_route.get("activity"))
    conv["turn_route"] = turn_route
    conv["activity"] = turn_route.get("activity")

    apply_manual_plan_patch(user_id=user.id, conversation=conv, plan=data.plan.model_dump())
    snapshot = build_conversation_detail_snapshot(user.id, conversation_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return snapshot

# ------------------------------------------------------------------
# File upload
# ------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/upload")
async def upload_harness_attachment(
    conversation_id: str,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    """Upload a file to the harness workspace for use as an attachment."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
        get_conversation_dir,
    )

    conv = get_conv(user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    original_name = file.filename or f"upload_{uuid.uuid4().hex}"
    content_type = str(file.content_type or "").strip().lower()
    guessed_mime = mimetypes.guess_type(original_name)[0] or content_type
    from app.services.agent_harness.capabilities.tools._internal.harness_file_readers import (
        is_supported_harness_upload,
    )

    if not is_supported_harness_upload(original_name, guessed_mime):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file format. Supported uploads include images, text files, "
                "doc/docx, xlsx, csv, and common code/text formats."
            ),
        )

    from app.services.agent_harness.workspace.generated_content.asset_store import register_asset
    from app.services.upload_writer import IMAGE_RASTER_EXTENSIONS, verify_image_file, write_upload_with_limit

    mime = guessed_mime or "application/octet-stream"
    max_bytes = max(1, int(settings.HARNESS_ATTACHMENT_UPLOAD_MAX_BYTES or 0))
    conversation_root = get_conversation_dir(user.id, conversation_id).resolve()
    temp_dir = conversation_root / ".meta" / "upload_tmp"
    suffix = Path(original_name).suffix
    temp_path = temp_dir / f"{uuid.uuid4().hex}{suffix}"
    size = await write_upload_with_limit(
        file,
        temp_path,
        max_bytes=max_bytes,
    )
    try:
        looks_like_image = mime.startswith("image/") or suffix.lower() in IMAGE_RASTER_EXTENSIONS
        if looks_like_image:
            verify_image_file(
                temp_path,
                allowed_extensions=IMAGE_RASTER_EXTENSIONS,
                content_type=mime,
            )
        asset = register_asset(
            user.id,
            conversation_id,
            source_path=temp_path,
            kind="input",
            original_name=original_name,
            mime_type=mime,
            source="upload",
        )
    finally:
        temp_path.unlink(missing_ok=True)

    # Determine file type
    file_type = "image" if mime.startswith("image/") else "file"

    relative_path = str(asset.get("path") or "")

    return {
        "url": relative_path,
        "filename": original_name,
        "type": file_type,
        "size": int(asset.get("size") or size),
        "asset_id": asset.get("asset_id"),
    }


# ------------------------------------------------------------------
# Workspace files
# ------------------------------------------------------------------


@router.get("/conversations/{conversation_id}/files", response_model=list[WorkspaceFileRead])
async def list_workspace_files(
    conversation_id: str,
    user: CurrentUser,
):
    """List generated files in the harness workspace."""
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        list_workspace_files as list_files,
    )
    return list_files(user.id, conversation_id)


@router.get("/conversations/{conversation_id}/files/{file_id}/versions")
async def list_workspace_file_versions(
    conversation_id: str,
    file_id: str,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.generated_content.file_version_store import get_versioned_file

    try:
        file = get_versioned_file(user.id, conversation_id, file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    return [
        {
            "version_id": version.version_id,
            "label": version.label,
            "size": version.size,
            "sha256": version.sha256,
            "created_at": version.created_at,
            "created_by": version.created_by,
            "run_id": version.run_id,
            "parent_version_id": version.parent_version_id,
            "parent_input_asset_ids": version.parent_input_asset_ids,
            "referenced_asset_ids": version.referenced_asset_ids,
            "note": version.note,
        }
        for version in file.versions
    ]


@router.post("/conversations/{conversation_id}/files/{file_id}/current-version")
async def set_workspace_file_current_version(
    conversation_id: str,
    file_id: str,
    data: dict,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        set_current_version,
        workspace_file_event_payload,
    )
    from app.services.agent_harness.runtime.eventing.event_log import append_event

    version_id = str(data.get("version_id") or "").strip()
    if not version_id:
        raise HTTPException(status_code=422, detail="version_id is required")
    try:
        file = set_current_version(user.id, conversation_id, file_id, version_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File version not found") from None
    append_event(
        user.id,
        conversation_id,
        run_id=None,
        event_type="file_current_version_changed",
        data=workspace_file_event_payload(file),
    )
    return file


@router.get("/conversations/{conversation_id}/files/{file_id}/versions/{version_id}/download")
async def download_workspace_file_version(
    conversation_id: str,
    file_id: str,
    version_id: str,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        get_versioned_file,
        resolve_version_path,
    )

    try:
        file = get_versioned_file(user.id, conversation_id, file_id)
        resolved = resolve_version_path(user.id, conversation_id, file_id, version_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File version not found") from None
    return FileResponse(
        resolved,
        filename=file.name,
        media_type="application/octet-stream",
    )


@router.get("/conversations/{conversation_id}/files/{file_path:path}")
async def download_workspace_file(
    conversation_id: str,
    file_path: str,
    user: CurrentUser,
):
    """Download a generated file from the harness workspace."""
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        guess_workspace_preview_media_type,
        get_workspace_file_path,
    )
    resolved = get_workspace_file_path(user.id, conversation_id, file_path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="File not found")

    media_type = guess_workspace_preview_media_type(resolved)
    return FileResponse(
        resolved,
        filename=resolved.name,
        media_type=media_type,
    )


@router.post(
    "/conversations/{conversation_id}/office/open",
    response_model=OpenWorkspaceOfficeSessionRead,
)
async def open_workspace_office_session(
    conversation_id: str,
    data: OpenWorkspaceOfficeSessionRequest,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.conversation.office_session_service import (
        open_workspace_office_session as open_session,
    )
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        get_versioned_file,
        resolve_version_path,
    )

    try:
        if data.file_id:
            file = get_versioned_file(user.id, conversation_id, data.file_id)
            resolved = resolve_version_path(
                user.id,
                conversation_id,
                data.file_id,
                data.version_id,
            )
            return open_session(
                user.id,
                conversation_id,
                file.name,
                resolved_path=resolved,
            )
        if not data.file_path:
            raise ValueError("file_path or file_id is required")
        return open_session(user.id, conversation_id, data.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/conversations/{conversation_id}/office/close",
    response_model=CloseWorkspaceOfficeSessionRead,
)
async def close_workspace_office_session(
    conversation_id: str,
    data: CloseWorkspaceOfficeSessionRequest,
    user: CurrentUser,
):
    from app.services.agent_harness.workspace.conversation.office_session_service import (
        close_workspace_office_session as close_session,
    )

    try:
        return close_session(user.id, conversation_id, data.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/conversations/{conversation_id}/preview-token")
async def create_workspace_preview_token(
    conversation_id: str,
    user: CurrentUser,
):
    from app.core.security import create_harness_preview_token
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation

    if get_conversation(user.id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    token = create_harness_preview_token(
        user.id,
        conversation_id,
        expires_delta=timedelta(seconds=_PREVIEW_TOKEN_TTL_SECONDS),
    )
    return {
        "preview_token": token,
        "expires_in_seconds": _PREVIEW_TOKEN_TTL_SECONDS,
    }


@router.get("/conversations/{conversation_id}/preview-html/{file_path:path}")
async def preview_workspace_html(
    conversation_id: str,
    file_path: str,
    preview_token: str,
):
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import render_html_preview_document

    user_id = _validate_harness_preview_token(preview_token, conversation_id)
    try:
        rendered = render_html_preview_document(
            user_id,
            conversation_id,
            file_path,
            preview_url_builder=lambda relative_path: _build_preview_file_url(
                conversation_id,
                relative_path,
                preview_token,
            ),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HTMLResponse(rendered)


@router.get("/conversations/{conversation_id}/preview-html-version/{file_id}/{version_id}")
async def preview_workspace_html_version(
    conversation_id: str,
    file_id: str,
    version_id: str,
    preview_token: str,
    entry: str | None = None,
):
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        render_html_bundle_preview_document_async,
        render_html_preview_document,
    )
    from app.services.agent_harness.workspace.generated_content.file_version_store import resolve_version_path

    user_id = _validate_harness_preview_token(preview_token, conversation_id)
    try:
        resolved = resolve_version_path(user_id, conversation_id, file_id, version_id)
        if resolved.suffix.lower() == ".zip":
            rendered = await render_html_bundle_preview_document_async(
                user_id,
                conversation_id,
                file_id,
                version_id,
                entry=entry,
                preview_url_builder=lambda relative_path: _build_preview_file_url(
                    conversation_id,
                    relative_path,
                    preview_token,
                ),
            )
        else:
            conversation_root = get_conversation_dir(user_id, conversation_id).resolve()
            file_path = resolved.relative_to(conversation_root).as_posix()
            rendered = render_html_preview_document(
                user_id,
                conversation_id,
                file_path,
                preview_url_builder=lambda relative_path: _build_preview_file_url(
                    conversation_id,
                    relative_path,
                    preview_token,
                ),
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HTMLResponse(rendered)


@router.get("/conversations/{conversation_id}/preview-files/{file_path:path}")
async def preview_workspace_file(
    conversation_id: str,
    file_path: str,
    preview_token: str,
    w: int | None = None,
):
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        get_preview_workspace_file_path,
        guess_workspace_preview_media_type,
        render_css_preview_document,
        resolve_workspace_image_thumbnail,
        resolve_pending_generated_asset,
    )

    user_id = _validate_harness_preview_token(preview_token, conversation_id)
    preview_member = get_preview_workspace_file_path(user_id, conversation_id, file_path)
    if preview_member is None:
        pending = resolve_pending_generated_asset(user_id, conversation_id, file_path)
        if pending is not None and pending.get("status") == "processing":
            # Asset is still generating (or just landed but not flushed). Return a
            # non-2xx so <img>/<video> fires `error` and the client retries; the UI
            # shows its own "生成中" placeholder meanwhile.
            return Response(
                status_code=503,
                headers={"Retry-After": "3", "Cache-Control": "no-store"},
            )
        raise HTTPException(status_code=404, detail="File not found")
    resolved, base_dir = preview_member

    if resolved.suffix.lower() == ".css":
        rendered_css = render_css_preview_document(
            user_id,
            conversation_id,
            file_path,
            preview_url_builder=lambda relative_path: _build_preview_file_url(
                conversation_id,
                relative_path,
                preview_token,
            ),
        )
        return Response(content=rendered_css, media_type="text/css; charset=utf-8")

    media_type = guess_workspace_preview_media_type(resolved)
    thumbnail_path = resolve_workspace_image_thumbnail(resolved, base_dir / ".agent" / "preview_cache", w)
    if thumbnail_path is not None:
        return FileResponse(
            thumbnail_path,
            filename=thumbnail_path.name,
            media_type="image/png",
        )
    return FileResponse(
        resolved,
        filename=resolved.name,
        media_type=media_type,
    )


@router.get("/conversations/{conversation_id}/preview-file-version/{file_id}/{version_id}/{download_name}")
@router.get("/conversations/{conversation_id}/preview-file-version/{file_id}/{version_id}")
async def preview_workspace_file_version(
    conversation_id: str,
    file_id: str,
    version_id: str,
    preview_token: str,
    download_name: str | None = None,
):
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        get_versioned_file,
        resolve_version_path,
    )
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        guess_workspace_preview_media_type,
    )

    user_id = _validate_harness_preview_token(preview_token, conversation_id)
    try:
        file = get_versioned_file(user_id, conversation_id, file_id)
        resolved = resolve_version_path(user_id, conversation_id, file_id, version_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File version not found") from None

    media_type = guess_workspace_preview_media_type(resolved)
    return FileResponse(
        resolved,
        filename=file.name,
        media_type=media_type,
    )


@router.get("/conversations/{conversation_id}/file-bundles/{file_path:path}")
async def download_workspace_html_bundle(
    conversation_id: str,
    file_path: str,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    """Download an HTML workspace file as a self-contained zip bundle."""
    from app.services.agent_harness.workspace.conversation.workspace_preview_service import create_html_bundle

    try:
        bundle_path = create_html_bundle(user.id, conversation_id, file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(bundle_path.unlink, missing_ok=True)
    download_name = f"{bundle_path.stem}.zip"
    requested_name = file_path.replace("\\", "/").split("/")[-1]
    if requested_name.lower().endswith((".html", ".htm")):
        download_name = f"{requested_name.rsplit('.', 1)[0]}.zip"

    return FileResponse(
        bundle_path,
        filename=download_name,
        media_type="application/zip",
        background=background_tasks,
    )

# ------------------------------------------------------------------
# Generation task status (for frontend polling)
# ------------------------------------------------------------------


def _generation_task_status_response(data: dict[str, Any], fallback_task_id: str | int) -> dict[str, Any]:
    return {
        "task_id": data.get("task_id", fallback_task_id),
        "artifact_ref": data.get("artifact_ref"),
        "status": data.get("status"),
        "result_url": data.get("result_url"),
        "result_urls": data.get("result_urls"),
        "planned_result_url": data.get("planned_result_url"),
        "artifact": data.get("artifact"),
        "error_message": data.get("error") or data.get("error_message"),
        "kind": data.get("kind"),
        "progress": data.get("progress"),
        "prompt": data.get("prompt"),
        "params": data.get("params"),
        "provider_code": data.get("provider_code"),
        "model_name": data.get("model_name"),
        "model_label": data.get("model_label"),
        "resolution": data.get("resolution"),
        "duration": data.get("duration"),
        "quality": data.get("quality"),
        "reference_diagnostics": data.get("reference_diagnostics"),
        "suppress_standard_media_card": data.get("suppress_standard_media_card"),
        "presentation_surface": data.get("presentation_surface"),
        "canvas_item": data.get("canvas_item"),
        "canvas_revision": data.get("canvas_revision"),
        "canvas_item_deleted": data.get("canvas_item_deleted"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


@router.get("/conversations/{conversation_id}/generation-tasks/{task_id}")
async def get_generation_task_status(
    conversation_id: str,
    task_id: str,
    user: CurrentUser,
):
    """Get the status of a generation task (for frontend polling)."""
    from app.services.agent_harness.core.context import create_context
    from app.services.agent_harness.core.utils import generation_store
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
    )

    conversation = get_conv(user.id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ctx = create_context(
        user_id=user.id,
        conversation_id=conversation_id,
        run_id="_lookup",
        conversation=conversation,
    )
    data = await generation_store.read_effective_generation_task(ctx, task_id)
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")

    return _generation_task_status_response(data, task_id)


@router.get("/conversations/{conversation_id}/generation-artifacts/{artifact_ref}/task")
async def get_generation_artifact_task_status(
    conversation_id: str,
    artifact_ref: str,
    user: CurrentUser,
):
    """Get the effective generation task status by artifact_ref."""
    from app.services.agent_harness.core.context import create_context
    from app.services.agent_harness.core.utils import generation_store
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        get_conversation as get_conv,
    )

    conversation = get_conv(user.id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ctx = create_context(
        user_id=user.id,
        conversation_id=conversation_id,
        run_id="_lookup",
        conversation=conversation,
    )
    data = await generation_store.read_effective_generation_task_by_artifact_ref(ctx, artifact_ref)
    if not data:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return _generation_task_status_response(data, data.get("task_id") or artifact_ref)


@router.post(
    "/conversations/{conversation_id}/generation-artifacts/retry",
    response_model=HarnessGenerationRetryRead,
)
async def retry_generation_artifact_endpoint(
    conversation_id: str,
    data: RetryHarnessGenerationArtifactRequest,
    user: CurrentUser,
):
    try:
        return await retry_generation_artifact(
            user_id=user.id,
            conversation_id=conversation_id,
            artifact_ref=data.artifact_ref,
        )
    except HarnessGenerationRetryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HarnessGenerationRetryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Skills
# ------------------------------------------------------------------


@router.get("/skills", response_model=list[HarnessSkillRead])
async def list_harness_skills():
    """List available harness skills."""
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, skill_catalog_response

    try:
        body, etag = await skill_catalog_response()
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/skills/{skill_id}/example-html", response_class=HTMLResponse)
async def get_harness_skill_example_html(skill_id: str):
    """Return the root example.html for a harness skill when present."""
    from app.services.agent_harness.catalog import (
        AgentCatalogAssetNotFoundError,
        AgentCatalogUnavailableError,
        skill_example_html_path,
    )

    try:
        example_path = skill_example_html_path(skill_id)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentCatalogAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse(content=example_path.read_text(encoding="utf-8"))


@router.get("/skills/{skill_id}/files/{file_path:path}")
async def get_harness_skill_file(skill_id: str, file_path: str):
    """Serve files from a harness skill root directory with root restriction."""
    from app.services.agent_harness.catalog import (
        AgentCatalogAssetNotFoundError,
        AgentCatalogUnavailableError,
        skill_asset_file_path,
    )

    try:
        resolved = skill_asset_file_path(skill_id, file_path)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentCatalogAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(path=str(resolved), media_type=media_type or "application/octet-stream")


@router.get("/design-systems", response_model=list[HarnessDesignSystemRead])
async def list_harness_design_systems():
    """List available Home Harness design systems."""
    from app.services.agent_harness.catalog import AgentCatalogUnavailableError, design_system_catalog_response

    try:
        body, etag = await design_system_catalog_response()
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/design-systems/{design_system_id}", response_model=HarnessDesignSystemDetailRead)
async def get_harness_design_system(design_system_id: str):
    """Get a Home Harness design system including its DESIGN.md body."""
    from app.services.agent_harness.capabilities.design_systems import get_design_system

    design_system = get_design_system(design_system_id)
    if design_system is None:
        raise HTTPException(status_code=404, detail=f"Unknown design system: {design_system_id}")

    return HarnessDesignSystemDetailRead(
        id=design_system.id,
        title=design_system.title,
        description=design_system.description,
        category=design_system.category,
        sections=design_system.sections,
        palette=design_system.palette,
        preview=design_system.preview,
        featured=design_system.featured,
        is_default=design_system.is_default,
        body=design_system.body,
        design_md=design_system.design_md or design_system.body,
        usage_md=design_system.usage_md,
        tokens_css=design_system.tokens_css,
        components_manifest=design_system.components_manifest,
        import_mode=design_system.import_mode or "normalized",
        health=design_system.health.to_payload() if design_system.health is not None else None,
        source_digest=design_system.source_digest,
    )


@router.get("/design-systems/{design_system_id}/preview-html", response_class=HTMLResponse)
async def get_harness_design_system_preview_html(design_system_id: str):
    """Return the bundled HTML preview for a single design system."""
    from app.services.agent_harness.catalog import (
        AgentCatalogAssetNotFoundError,
        AgentCatalogUnavailableError,
        design_system_preview_html_path,
    )

    try:
        preview_path = design_system_preview_html_path(design_system_id)
    except AgentCatalogUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentCatalogAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse(content=preview_path.read_text(encoding="utf-8"))

# ------------------------------------------------------------------
# Workspace management
# ------------------------------------------------------------------


@router.get("/workspace-stats", response_model=WorkspaceStatsRead)
async def get_workspace_stats(
    user: CurrentUser,
):
    """Get workspace usage stats for the current user."""
    from app.services.agent_harness.runtime.execution_support.cleanup import get_workspace_stats
    return get_workspace_stats(user.id)


@router.post("/cleanup", response_model=CleanupResultRead)
async def run_workspace_cleanup(
    data: CleanupRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Run workspace cleanup. Default dry_run=true for safety."""
    from app.services.agent_harness.runtime.execution_support.cleanup import cleanup_workspaces
    stats = await cleanup_workspaces(db, dry_run=data.dry_run)
    return CleanupResultRead(
        orphan_dirs_removed=stats.orphan_dirs_removed,
        expired_dirs_removed=stats.expired_dirs_removed,
        oversized_dirs_trimmed=stats.oversized_dirs_trimmed,
        bytes_freed=stats.bytes_freed,
        errors=stats.errors,
        dry_run=data.dry_run,
    )



