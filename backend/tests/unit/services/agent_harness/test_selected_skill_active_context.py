from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_harness.capabilities.skills.active_context import (
    SELECTED_SKILL_CONTEXT_BUILDER_VERSION,
    build_selected_skill_active_context,
    clear_selected_skill_active_context,
    is_active_skill_context_current,
    persist_selected_skill_active_context,
)
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
)
from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload


def test_selected_skill_active_context_preserves_full_body_and_side_file_hints(tmp_path):
    skill_dir = tmp_path / "skills" / "landing"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "assets").mkdir()
    (skill_dir / "example.html").write_text("<html></html>", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: landing\n---\n"
        "# Workflow\n"
        "Follow the workflow.\n"
        "Read [authoring guide](references/authoring-guide.md) when details matter.\n",
        encoding="utf-8",
    )
    skill = SimpleNamespace(id="landing", skill_dir=skill_dir)

    artifact = build_selected_skill_active_context(skill, language="en")

    assert artifact["skill_id"] == "landing"
    assert artifact["language"] == "en"
    assert artifact["source_path"] == "SKILL.md"
    assert artifact["source_body"] in artifact["runtime_body"]
    assert "Skill root: `skill/`" in artifact["runtime_body"]
    assert 'read_file(base="skill", path="<relative-path>")' in artifact["runtime_body"]
    assert "Known side files:" in artifact["runtime_body"]
    assert artifact["truncation_mode"] == "full"
    assert artifact["builder_version"] == SELECTED_SKILL_CONTEXT_BUILDER_VERSION
    assert "source_digest" in artifact
    assert artifact["loaded_paths"] == ["skill/SKILL.md"]
    assert "skill/references" in artifact["on_demand_paths"]
    assert "skill/scripts" in artifact["on_demand_paths"]
    assert "skill/assets" in artifact["on_demand_paths"]
    assert "skill/example.html" in artifact["on_demand_paths"]
    assert "skill/references/authoring-guide.md" in artifact["link_targets"]
    assert is_active_skill_context_current(
        artifact,
        skill_id="landing",
        language="en",
        source_digest=artifact["source_digest"],
    )


def test_selected_skill_active_context_persists_as_runtime_contract_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    skill_dir = tmp_path / "skills" / "landing"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Workflow\nPersist this selected skill.\n", encoding="utf-8")
    skill = SimpleNamespace(id="landing", skill_dir=skill_dir)
    conversation = create_conversation(7, title="Selected skill", skill_id="landing")

    artifact = persist_selected_skill_active_context(7, conversation["id"], skill, language="en")
    stored = read_runtime_state_payload(7, conversation["id"])

    active_context = stored["runtime_state"]["runtime_contract"]["active_skill_context"]
    assert active_context["kind"] == "selected_skill_active_context"
    assert active_context["skill_id"] == "landing"
    assert "Persist this selected skill." in active_context["runtime_body"]
    assert active_context["source_digest"] == artifact["source_digest"]
    assert active_context["builder_version"] == SELECTED_SKILL_CONTEXT_BUILDER_VERSION

    clear_selected_skill_active_context(7, conversation["id"])
    cleared = read_runtime_state_payload(7, conversation["id"])
    runtime_contract = (cleared["runtime_state"] or {}).get("runtime_contract") or {}
    assert "active_skill_context" not in runtime_contract


def test_selected_skill_active_context_appends_preflight_when_side_files_referenced(tmp_path):
    skill_dir = tmp_path / "skills" / "deck"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "assets").mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deck\n---\n"
        "# Workflow\n"
        "Paste into `assets/template.html` and follow `references/checklist.md` before publishing.\n",
        encoding="utf-8",
    )
    skill = SimpleNamespace(id="deck", skill_dir=skill_dir)

    artifact = build_selected_skill_active_context(skill, language="en")

    assert artifact["preflight_paths"] == ["assets/template.html", "references/checklist.md"]
    assert artifact["runtime_body"] != artifact["source_body"]
    assert "Skill root: `skill/`" in artifact["runtime_body"]
    assert 'read_file(base="skill", path="<relative-path>")' in artifact["runtime_body"]
    assert "Pre-flight" in artifact["runtime_body"]
    assert "assets/template.html" in artifact["runtime_body"]
    assert "references/checklist.md" in artifact["runtime_body"]


def test_selected_skill_active_context_skips_preflight_without_side_files(tmp_path):
    skill_dir = tmp_path / "skills" / "plain"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Workflow\nJust write prose, no side files.\n", encoding="utf-8")
    skill = SimpleNamespace(id="plain", skill_dir=skill_dir)

    artifact = build_selected_skill_active_context(skill, language="en")

    assert artifact["preflight_paths"] == []
    assert artifact["runtime_body"] == artifact["source_body"]


def test_selected_skill_active_context_keeps_large_skill_body_full(tmp_path):
    skill_dir = tmp_path / "skills" / "large"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "# Purpose",
                "Build with this selected skill.",
                "# Workflow",
                *[f"- Step {index}: keep selected skill behavior active." for index in range(20)],
                "# Large Example",
                "```python",
                *[f"print({index})" for index in range(400)],
                "```",
                "# Checklist",
                *[f"- Check {index}" for index in range(20)],
            ]
        ),
        encoding="utf-8",
    )
    skill = SimpleNamespace(id="large", skill_dir=skill_dir)

    artifact = build_selected_skill_active_context(skill, language="en")

    assert artifact["truncation_mode"] == "full"
    assert "Build with this selected skill." in artifact["runtime_body"]
    assert "- Step 0" in artifact["runtime_body"]
    assert "print(399)" in artifact["runtime_body"]
    assert artifact["omission_kinds"] == []
    assert not is_active_skill_context_current(
        artifact,
        skill_id="large",
        language="zh",
        source_digest=artifact["source_digest"],
    )
