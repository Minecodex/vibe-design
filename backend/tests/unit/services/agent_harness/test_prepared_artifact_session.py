from __future__ import annotations

from pathlib import Path

from app.services.agent_harness.runtime.state.runtime_snapshot import build_runtime_state_snapshot
from app.services.agent_harness.capabilities.skill_protocols.base import prepared_workspace_from_payload
from app.services.agent_harness.capabilities.skill_protocols.open_design.materializer import (
    materialize_open_design_prepared_workspace,
)
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.runtime.state.runtime_projection_store import persist_runtime_session
from app.services.agent_harness.runtime.state.store_core import read_runtime_state
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def test_prepared_workspace_does_not_select_matching_full_deck_template(tmp_path):
    skill = get_skill("html-ppt")
    assert skill is not None
    assert skill.skill_dir is not None

    session = materialize_open_design_prepared_workspace(
        skill_root=Path(skill.skill_dir),
        work_dir=tmp_path,
        candidate_name="html-ppt-prepared-test",
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
    )

    assert session.strategy == "template_driven_deck"
    assert session.selected_template is None
    assert session.source_root == "skill"
    assert session.entry_file == "index.html"


def test_prepared_workspace_materializes_only_inside_workdir(tmp_path):
    skill = get_skill("html-ppt")
    assert skill is not None
    assert skill.skill_dir is not None

    session = materialize_open_design_prepared_workspace(
        skill_root=Path(skill.skill_dir),
        work_dir=tmp_path,
        candidate_name="html-ppt-prepared",
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
    )

    entry = tmp_path / session.artifact_work_root / session.entry_file
    assets_runtime = tmp_path / session.artifact_work_root / "assets" / "runtime.js"

    assert session.family == "harness_full_deck_runtime"
    assert session.strategy == "template_driven_deck"
    assert session.entry_path == "html-ppt-prepared/index.html"
    assert session.source_root == "skill"
    assert entry.resolve().is_relative_to(tmp_path.resolve())
    assert entry.parent.is_dir()
    # A skill without a seed template prepares a directory for authoring.
    assert entry.is_file() == (Path(skill.skill_dir) / "assets" / "template.html").is_file()
    assert not assets_runtime.exists()


def test_prepared_workspace_round_trips_from_payload(tmp_path):
    skill = get_skill("html-ppt")
    assert skill is not None
    assert skill.skill_dir is not None

    session = materialize_open_design_prepared_workspace(
        skill_root=Path(skill.skill_dir),
        work_dir=tmp_path,
        candidate_name="html-ppt-prepared",
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
    )

    restored = prepared_workspace_from_payload(session.to_payload())

    assert restored is not None
    assert restored.family == session.family
    assert session.to_payload()["artifact_work_root"] == session.artifact_work_root
    assert restored.entry_path == session.entry_path
    assert restored.selected_template == session.selected_template


def test_runtime_state_snapshot_keeps_prepared_workspace_during_execution():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-1",
        conversation={
            "phase": "executing",
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
            "run_id": "run-1",
        },
        outline_runtime_state={},
        runtime_state={
            "prepared_workspace": {
                "family": "harness_full_deck_runtime",
                "strategy": "template_driven_deck",
                "skill_id": "html-ppt",
                "artifact_work_root": "html-ppt-prepared",
                "entry_file": "index.html",
                "entry_path": "html-ppt-prepared/index.html",
                "selected_template": "tech-sharing",
                "source_root": "templates/full-decks/tech-sharing",
            },
            "runtime_contract": {
                "execution_strategy": "template_driven_deck",
                "secondary_outputs": ["speaker-notes.md"],
            },
        },
    )

    assert snapshot["phase"] == "executing"
    assert snapshot["prepared_workspace"]["entry_file"] == "index.html"
    assert snapshot["runtime_contract"]["secondary_outputs"] == ["speaker-notes.md"]


def test_runtime_state_snapshot_keeps_discovery_direction_and_workspace_session():
    snapshot = build_runtime_state_snapshot(
        conversation_id="conv-discovery",
        conversation={
            "phase": "discovery",
            "runtime_status": "waiting_input",
            "run_state": "discovery",
            "turn_status": "waiting_input",
            "run_id": "run-discovery",
        },
        outline_runtime_state={},
        runtime_state={
            "discovery_status": "waiting_input",
            "discovery_started_at": "2026-05-06T00:00:00Z",
            "discovery_completed_at": None,
            "discovery_payload": {"brand": "Open Design"},
            "discovery_schema": [{"id": "brand", "required": True}],
            "workspace_runtime_session": {
                "active_entry": "open-design-landing-prepared/index.html",
                "selected_skill": "open-design-landing",
                "selected_direction": "atelier-zero",
                "selected_design_system": "atelier-zero",
                "artifact_work_root": "open-design-landing-prepared",
            },
            "runtime_contract": {
                "direction_id": "atelier-zero",
                "direction_selection_mode": "auto",
                "direction_resolution_source": "skill",
            },
        },
    )

    assert snapshot["phase"] == "discovery"
    assert snapshot["discovery_status"] == "waiting_input"
    assert snapshot["workspace_runtime_session"]["active_entry"] == "open-design-landing-prepared/index.html"
    assert snapshot["runtime_contract"]["direction_id"] == "atelier-zero"


def test_runtime_state_persists_prepared_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(1, title="Runtime session")

    persist_runtime_session(
        1,
        conversation["id"],
        prepared_workspace={
            "family": "harness_full_deck_runtime",
            "artifact_work_root": "dashboard",
            "entry_file": "index.html",
            "entry_path": "dashboard/index.html",
        },
        workspace_runtime_session={
            "active_entry": "dashboard/index.html",
            "selected_skill": "dashboard",
            "selected_direction": None,
            "selected_design_system": None,
        },
        discovery_status="completed",
        discovery_started_at="2026-05-06T00:00:00Z",
        discovery_completed_at="2026-05-06T00:01:00Z",
        discovery_payload={"product_name": "Pulse"},
        discovery_schema=[{"id": "product_name", "required": True}],
    )

    runtime_state = read_runtime_state(1, conversation["id"])

    assert runtime_state["prepared_workspace"]["entry_path"] == "dashboard/index.html"
    assert runtime_state["workspace_runtime_session"]["active_entry"] == "dashboard/index.html"
    assert runtime_state["discovery_status"] == "completed"
    assert runtime_state["discovery_payload"]["product_name"] == "Pulse"
