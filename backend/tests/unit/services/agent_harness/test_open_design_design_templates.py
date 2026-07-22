from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.agent_harness.capabilities.skill_protocols.open_design.design_templates import (
    HTML_PPT_FIRST_WAVE_WRAPPER_IDS,
    STANDALONE_FIRST_WAVE_TEMPLATE_IDS,
    build_design_template_catalog,
    build_imported_template_metadata,
    normalize_template_body_for_workspace,
)
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.skills.active_context import (
    build_selected_skill_active_context,
)
from app.services.agent_harness.workspace.skill_staging_v2 import stage_active_skill_v2


def _write_skill(root: Path, skill_id: str, body: str, *, extra_files: dict[str, str] | None = None) -> Path:
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    for rel_path, content in dict(extra_files or {}).items():
        target = skill_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return skill_dir


def test_design_template_catalog_marks_wrappers_without_deferred_runtime_gating(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "html-ppt",
        "# html-ppt\nRead templates/full-decks/pitch-deck/index.html before writing.",
        extra_files={
            "templates/full-decks/pitch-deck/index.html": "<main></main>",
            "assets/runtime.js": "console.log('runtime')",
        },
    )
    _write_skill(
        tmp_path,
        "html-ppt-product-launch",
        "# Product launch\nRead the master skill first: ../html-ppt/SKILL.md.\nUse template.json.",
        extra_files={"template.json": "{}"},
    )
    _write_skill(tmp_path, "kami-landing", "# Kami\nRead ../../design-systems/kami/DESIGN.md.")
    _write_skill(tmp_path, "live-artifact", "# Live Artifact\nUse connectors and refresh-contract.md.")

    catalog = build_design_template_catalog(tmp_path)

    wrapper = catalog["html-ppt-product-launch"]
    assert wrapper.relation.kind == "wrapper"
    assert wrapper.relation.primary_master_id == "html-ppt"
    assert wrapper.runtime_entry_strategy == "edit-example"
    assert "skill/template.json" in wrapper.preflight.seed_template_files
    assert "skill/_linked/html-ppt/SKILL.md" in wrapper.preflight.context_sources

    standalone = catalog["kami-landing"]
    assert standalone.relation.kind == "standalone"
    assert standalone.support_state == "supported"
    assert standalone.rollout_wave == "standalone_first_wave"
    assert "design_system:kami" in standalone.preflight.context_sources

    deferred = catalog["live-artifact"]
    assert deferred.support_state == "supported"
    assert deferred.deferred_reason is None
    assert deferred.reentry_criteria is None


def test_template_body_normalization_rewrites_upstream_path_contracts() -> None:
    normalized = normalize_template_body_for_workspace(
        "Read .od-skills/html-ppt/SKILL.md, skills/html-ppt/assets/runtime.js, "
        "and ../../design-systems/kami/DESIGN.md. Write final HTML beside SKILL.md."
    )

    assert ".od-skills" not in normalized
    assert "skills/html-ppt" not in normalized
    assert "skill/_linked/html-ppt/SKILL.md" in normalized
    assert "skill/_linked/html-ppt/assets/runtime.js" in normalized
    assert "design_system:kami" in normalized
    assert "Template files under `skill/` are read-only" in normalized
    assert "write final deliverables under `project/`" in normalized


def test_real_imported_templates_expose_runtime_metadata() -> None:
    html_wrapper = get_skill("html-ppt-taste-brutalist")
    html_master = get_skill("html-ppt")
    kami = get_skill("kami-landing")
    live_artifact = get_skill("live-artifact")

    assert html_wrapper is not None
    assert html_wrapper.runtime_capabilities["template_relation"]["kind"] == "wrapper"
    assert html_wrapper.runtime_capabilities["template_relation"]["primary_master_id"] == "html-ppt"
    assert html_wrapper.runtime_capabilities["template_support_state"] == "supported"
    assert html_wrapper.runtime_capabilities["template_rollout_wave"] == "html_ppt_first_wave"
    assert html_wrapper.runtime_capabilities["template_preflight"]["runtime_entry_strategy"] == "edit-example"
    assert html_wrapper.id in HTML_PPT_FIRST_WAVE_WRAPPER_IDS

    assert html_master is not None
    assert html_master.runtime_capabilities["template_relation"]["kind"] == "standalone"

    assert kami is not None
    assert kami.id in STANDALONE_FIRST_WAVE_TEMPLATE_IDS
    assert kami.runtime_capabilities["template_rollout_wave"] == "standalone_first_wave"

    assert live_artifact is not None
    assert live_artifact.runtime_capabilities["template_support_state"] == "supported"
    assert live_artifact.runtime_capabilities["template_reentry_criteria"] is None


def test_imported_template_active_context_preserves_full_normalized_body(tmp_path: Path) -> None:
    skill_dir = _write_skill(
        tmp_path,
        "html-ppt-product-launch",
        "# Wrapper\nRead .od-skills/html-ppt/SKILL.md first.\n" + ("keep this later rule\n" * 200),
        extra_files={"template.json": "{}"},
    )
    metadata = build_imported_template_metadata("html-ppt-product-launch", skill_dir)
    skill = SimpleNamespace(id="html-ppt-product-launch", skill_dir=skill_dir, runtime_capabilities=metadata.to_runtime_capabilities())

    context = build_selected_skill_active_context(skill, language="en")

    assert context["kind"] == "selected_skill_active_context"
    assert context["template_support_state"] == "supported"
    assert context["truncation_mode"] == "full"
    assert ".od-skills" not in context["runtime_body"]
    assert "skill/_linked/html-ppt/SKILL.md" in context["runtime_body"]
    assert "keep this later rule" in context["runtime_body"]
    assert "skill/template.json" in context["template_preflight"]["seed_template_files"]


def test_selected_skill_active_context_uses_open_design_preflight_paths(tmp_path: Path) -> None:
    skill_dir = _write_skill(
        tmp_path,
        "hyperframes",
        "# Hyperframes\nRead assets/template.html and references/html-in-canvas.md before building.",
        extra_files={"assets/template.html": "<main></main>", "references/html-in-canvas.md": "# Canvas"},
    )
    skill = SimpleNamespace(id="hyperframes", skill_dir=skill_dir, system_prompt=(skill_dir / "SKILL.md").read_text(encoding="utf-8"))

    context = build_selected_skill_active_context(skill, language="en")

    assert context["preflight_paths"] == ["assets/template.html", "references/html-in-canvas.md"]
    assert "`references/html-in-canvas.md`" in context["runtime_body"]


def test_wrapper_template_staging_exposes_linked_master_under_skill_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_skill(source_root, "html-ppt", "# Master\nUse the deck runtime.")
    wrapper_dir = _write_skill(source_root, "html-ppt-product-launch", "# Wrapper\nRead ../html-ppt/SKILL.md.")
    ctx = SimpleNamespace(conversation_dir=tmp_path / "conversation")

    result = stage_active_skill_v2(ctx, wrapper_dir)

    assert result["ok"] is True
    linked_master = ctx.skill_dir / "_linked" / "html-ppt" / "SKILL.md"
    assert linked_master.is_file()
    assert "Use the deck runtime." in linked_master.read_text(encoding="utf-8")


def test_skill_staging_does_not_seed_project_inputs_from_example(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_dir = _write_skill(
        source_root,
        "script-skill",
        "# Script skill",
        extra_files={"inputs.example.json": '{"brand":{"name":"Example"}}\n'},
    )
    ctx = SimpleNamespace(conversation_dir=tmp_path / "conversation", project_dir=tmp_path / "conversation" / "project")

    result = stage_active_skill_v2(ctx, skill_dir)

    assert result["ok"] is True
    assert "seeded_inputs" not in result
    assert not (ctx.project_dir / "inputs.json").exists()


def test_skill_staging_leaves_existing_project_inputs_untouched(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_dir = _write_skill(
        source_root,
        "script-skill",
        "# Script skill",
        extra_files={"inputs.example.json": '{"brand":{"name":"Example"}}\n'},
    )
    project_dir = tmp_path / "conversation" / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "inputs.json").write_text('{"brand":{"name":"Custom"}}\n', encoding="utf-8")
    ctx = SimpleNamespace(conversation_dir=tmp_path / "conversation", project_dir=project_dir)

    result = stage_active_skill_v2(ctx, skill_dir)

    assert result["ok"] is True
    assert "seeded_inputs" not in result
    assert (project_dir / "inputs.json").read_text(encoding="utf-8") == '{"brand":{"name":"Custom"}}\n'
