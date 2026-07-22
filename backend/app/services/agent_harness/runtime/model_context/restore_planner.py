from __future__ import annotations

import json
from typing import Any

from .models import RestorePlan


def build_restore_plan(
    *,
    runtime_contract: dict[str, Any] | None = None,
    workspace_runtime_session: dict[str, Any] | None = None,
) -> RestorePlan:
    messages: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    active_refs = _active_reference_payload(runtime_contract, workspace_runtime_session)
    if active_refs:
        anchors.extend(active_refs.get("anchors") or [])
        messages.append(
            {
                "role": "user",
                "content": "Post-compact restore context:\n"
                + _compact_restore_text(active_refs.get("context") or {}),
            }
        )
    return RestorePlan(messages=messages, anchors=anchors)


def _active_reference_payload(
    runtime_contract: dict[str, Any] | None,
    workspace_runtime_session: dict[str, Any] | None,
) -> dict[str, Any] | None:
    context: dict[str, Any] = {}
    anchors: list[dict[str, Any]] = []
    contract = runtime_contract if isinstance(runtime_contract, dict) else {}
    execution_contract = (
        contract.get("runtime_execution_contract")
        if isinstance(contract.get("runtime_execution_contract"), dict)
        else {}
    )
    active_design_system_context = (
        contract.get("active_design_system_context")
        if isinstance(contract.get("active_design_system_context"), dict)
        else {}
    )
    runtime = workspace_runtime_session if isinstance(workspace_runtime_session, dict) else {}

    scalar_fields = {
        "active_entry": _first_text(runtime.get("active_entry"), contract.get("active_entry"), execution_contract.get("active_entry")),
        "artifact_work_root": _first_text(
            runtime.get("artifact_work_root"),
            contract.get("artifact_work_root"),
            execution_contract.get("artifact_work_root"),
        ),
        "agent_cwd": _first_text(runtime.get("agent_cwd")),
        "selected_direction": _first_text(
            runtime.get("selected_direction"),
            contract.get("direction_id"),
        ),
        "selected_design_system": _first_text(
            runtime.get("selected_design_system"),
            active_design_system_context.get("design_system_id"),
        ),
        "active_file": _first_text(runtime.get("active_file"), runtime.get("entry_path")),
    }
    for key, value in scalar_fields.items():
        if not value:
            continue
        context[key] = value
        anchor_kind = "file" if key in {"active_entry", "active_file"} else "runtime_context"
        anchors.append({"kind": anchor_kind, "value": value, "source": key})
    return {"context": context, "anchors": anchors} if context else None


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").replace("\\", "/").strip().strip("/")
        if text:
            return text
    return ""


def _compact_restore_text(payload: dict[str, Any]) -> str:
    lines = []
    for key, value in sorted(payload.items()):
        if isinstance(value, list | dict):
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines)
