from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkspaceRuntimeSession:
    selected_skill: str | None = None
    internal_hidden_skills: list[dict[str, Any]] = field(default_factory=list)
    selected_direction: str | None = None
    selected_design_system: str | None = None
    artifact_work_root: str | None = None
    agent_cwd: str | None = None
    active_entry: str | None = None
    discovered_inputs: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "selected_skill": self.selected_skill,
            "internal_hidden_skills": [dict(item) for item in self.internal_hidden_skills if isinstance(item, dict)],
            "selected_direction": self.selected_direction,
            "selected_design_system": self.selected_design_system,
            "artifact_work_root": self.artifact_work_root,
            "agent_cwd": self.agent_cwd,
            "active_entry": self.active_entry,
            "discovered_inputs": dict(self.discovered_inputs or {}) if isinstance(self.discovered_inputs, dict) else None,
        }


def workspace_runtime_session_from_payload(raw: Any) -> WorkspaceRuntimeSession | None:
    if not isinstance(raw, dict):
        return None
    return WorkspaceRuntimeSession(
        selected_skill=str(raw.get("selected_skill") or "").strip() or None,
        internal_hidden_skills=[dict(item) for item in list(raw.get("internal_hidden_skills") or []) if isinstance(item, dict)],
        selected_direction=str(raw.get("selected_direction") or "").strip() or None,
        selected_design_system=str(raw.get("selected_design_system") or "").strip() or None,
        artifact_work_root=str(raw.get("artifact_work_root") or "").replace("\\", "/").strip().strip("/") or None,
        agent_cwd=str(raw.get("agent_cwd") or "").replace("\\", "/").strip().strip("/") or None,
        active_entry=str(raw.get("active_entry") or "").replace("\\", "/").strip().strip("/") or None,
        discovered_inputs=dict(raw.get("discovered_inputs")) if isinstance(raw.get("discovered_inputs"), dict) else None,
    )
