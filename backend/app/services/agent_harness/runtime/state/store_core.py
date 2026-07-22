from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.message_visibility import assert_transcript_persistable_message
from app.services.agent_harness.workspace.conversation.conversation_service import (
    get_conversation_dir,
)
from app.services.agent_harness.workspace.conversation import transcript_store

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
def _default_outline_runtime_state() -> dict[str, Any]:
    return {
        "current_outline": None,
        "execution_state": None,
        "projection_state": None,
        "execution_run": None,
        "last_revision": None,
        "updated_at": None,
    }
def _default_runtime_state() -> dict[str, Any]:
    return {
        "conversation_id": None,
        "parent_usage_log_id": None,
        "updated_at": None,
        "phase": "planning",
        "run_status": "idle",
        "current_item_id": None,
        "current_action": None,
        "item_progress": [],
        "artifacts": [],
        "failure": None,
        "runtime_status": "idle",
        "turn_status": "idle",
        "run_state": "idle",
        "run_id": None,
        "last_tool": None,
        "discovery_status": "idle",
        "discovery_started_at": None,
        "discovery_completed_at": None,
        "discovery_payload": None,
        "discovery_schema": None,
        "prepared_workspace": None,
        "workspace_runtime_session": None,
        "runtime_contract": None,
    }
def _default_session_state() -> dict[str, Any]:
    return {
        "outline_runtime": _default_outline_runtime_state(),
        "runtime": _default_runtime_state(),
    }


def ensure_harness_meta(user_id: int, conversation_id: str) -> Path:
    conv_dir = get_conversation_dir(user_id, conversation_id)
    meta_dir = conv_dir / ".meta"
    (meta_dir / "tool_blobs").mkdir(parents=True, exist_ok=True)
    return meta_dir
def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(
            json.dumps(sanitize_persistent_payload(data), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
def append_model_message(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    message = sanitize_persistent_payload(message)
    assert_transcript_persistable_message(message)
    return transcript_store.save_message(user_id, conversation_id, message)
def runtime_state_path(user_id: int, conversation_id: str) -> Path:
    return ensure_harness_meta(user_id, conversation_id) / "runtime_state.json"


def plan_state_path(user_id: int, conversation_id: str) -> Path:
    return ensure_harness_meta(user_id, conversation_id) / "plan_state.json"


def read_runtime_snapshot_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    try:
        from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload

        state = read_runtime_state_payload(user_id, conversation_id) or {}
    except Exception:
        state = {}
    outline_runtime = state.get("outline_runtime")
    stored_runtime = state.get("runtime_state")
    runtime = dict(stored_runtime) if isinstance(stored_runtime, dict) else _default_runtime_state()
    if isinstance(state, dict):
        for key in (
            "conversation_id",
            "parent_usage_log_id",
            "phase",
            "failure",
            "runtime_status",
            "turn_status",
            "run_state",
            "run_id",
            "last_tool",
            "last_error_summary",
            "last_activity_at",
            "last_activity_source",
            "user_interaction",
            "cancel_requested",
            "heartbeat_at",
            "updated_at",
        ):
            if key in state:
                runtime[key] = state.get(key)
    return {
        "outline_runtime": (
            outline_runtime
            if isinstance(outline_runtime, dict)
            else _default_outline_runtime_state()
        ),
        "runtime": runtime,
    }


def write_runtime_snapshot_state(user_id: int, conversation_id: str, state: dict[str, Any]) -> None:
    payload = {
        "outline_runtime": (
            dict(state.get("outline_runtime") or {})
            if isinstance(state.get("outline_runtime"), dict)
            else _default_outline_runtime_state()
        ),
        "runtime": (
            dict(state.get("runtime") or {})
            if isinstance(state.get("runtime"), dict)
            else _default_runtime_state()
        ),
    }
    from app.services.agent_harness.workspace.session_v2.db_store import update_conversation_record

    update_conversation_record(
        user_id,
        conversation_id,
        {
            "outline_runtime": payload["outline_runtime"],
            "runtime_state": payload["runtime"],
            "updated_at": utc_now(),
        },
    )


def read_runtime_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    return dict(read_runtime_snapshot_state(user_id, conversation_id).get("runtime") or _default_runtime_state())


def read_outline_runtime_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    return dict(read_runtime_snapshot_state(user_id, conversation_id).get("outline_runtime") or _default_outline_runtime_state())
