from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_harness.authoring.prompt import context_builder
from app.services.agent_harness.authoring.prompt.sections import PromptSections


def _render_static(**overrides):
    args = {
        "language": "en",
        "conversation": {"artifact_mode": "web", "runtime_profile": "home"},
        "model_name": "test-model",
        "skill": None,
        "skill_prompt": None,
        "artifact_mode": "web",
        "skill_id": None,
        "skill_runtime_dir": None,
        "prepared_workspace": None,
        "workspace_runtime_session": None,
        "runtime_contract": None,
        "tool_schemas": None,
    }
    args.update(overrides)
    return context_builder.render_static_system_context(**args)


def _render_partitions(**overrides):
    args = {
        "language": "en",
        "conversation": {"artifact_mode": "web", "runtime_profile": "home"},
        "model_name": "test-model",
        "skill": None,
        "skill_prompt": None,
        "artifact_mode": "web",
        "skill_id": None,
        "skill_runtime_dir": None,
        "prepared_workspace": None,
        "workspace_runtime_session": None,
        "runtime_contract": None,
        "tool_schemas": None,
    }
    args.update(overrides)
    return context_builder.render_main_turn_prompt_partitions(**args)


def _context_text(partitions: dict) -> str:
    return "\n\n".join(block["content"] for block in partitions["context_snapshot_blocks"])


def test_static_context_reuses_static_system_prefix(monkeypatch):
    calls = {"count": 0}

    def fake_build_system_prompt(language: str, runtime_profile: str = "home", artifact_mode: str = "web") -> str:
        calls["count"] += 1
        return f"system:{language}:{runtime_profile}:{artifact_mode}"

    context_builder.clear_static_context_cache()
    monkeypatch.setattr(context_builder, "build_system_prompt", fake_build_system_prompt)

    _render_static(language="zh", conversation={"runtime_profile": "home"})
    _render_static(language="zh", conversation={"runtime_profile": "home"})

    assert calls["count"] == 1


def test_static_context_injects_runtime_capability_profile():
    system = _render_static(skill_prompt="Follow this domain skill.")

    assert "Runtime capability profile:" in system
    assert "Default Office author is `Harness`" in system
    assert "HARNESS_REFERENCES_DIR" in system
    assert "HARNESS_GENERATED_DIR" not in system
    assert "Workspace contract:" in system
    assert system.index("Workspace contract:") < system.index("Runtime capability profile:")
    assert "Active skill instructions:" not in system


def test_static_context_excludes_runtime_time_now_injected_per_turn():
    # The current time is no longer baked into the frozen static system; it is
    # appended fresh per turn in ContextProjector.render so it never goes stale
    # while the frozen system stays a stable cache prefix.
    system = _render_static()

    assert "Current runtime time:" not in system


def test_static_context_wraps_skill_prompt_with_runtime_preamble_and_side_file_hints(tmp_path):
    source_skill_dir = tmp_path / "skills" / "landing"
    runtime_skill_dir = tmp_path / "work" / ".skill_runtime" / "landing"
    for skill_dir in (source_skill_dir, runtime_skill_dir):
        (skill_dir / "assets").mkdir(parents=True)
        (skill_dir / "references").mkdir()
        (skill_dir / "scripts").mkdir()
        (skill_dir / "example.html").write_text("<!doctype html><html></html>", encoding="utf-8")
        (skill_dir / "inputs.example.json").write_text("{}", encoding="utf-8")
        (skill_dir / "schema.ts").write_text("export type Input = {};\n", encoding="utf-8")

    partitions = _render_partitions(
        skill=SimpleNamespace(id="landing", skill_dir=source_skill_dir),
        skill_id="landing",
        skill_prompt="Use the template skill carefully.",
        skill_runtime_dir=runtime_skill_dir,
        runtime_contract={
            "active_skill_context": {
                "skill_id": "landing",
                "runtime_body": "Use the template skill carefully.",
                "source_path": "SKILL.md",
                "loaded_paths": ["SKILL.md"],
                "on_demand_paths": ["assets", "references"],
                "link_targets": ["example.html"],
                "truncation_mode": "full",
            }
        },
    )
    system = partitions["stable_system"]
    context = _context_text(partitions)

    assert "Recommended first reads:" not in system
    assert "preferred_first_action" not in system
    assert "Read `skill/SKILL.md" not in system
    assert "Selected skill side files are not preloaded by default." in context
    assert "skill/SKILL.md" not in context
    assert ".skill_runtime" not in system


def test_static_context_injects_internal_hidden_skill_instructions(monkeypatch, tmp_path):
    active_skill_dir = tmp_path / "skills" / "deck"
    active_skill_dir.mkdir(parents=True)
    hidden_skill_dir = tmp_path / "skills" / "critique"
    hidden_skill_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.summary_providers.get_skill",
        lambda skill_id: (
            SimpleNamespace(
                id="critique",
                name="Critique",
                name_en="Critique",
                skill_dir=hidden_skill_dir,
                description="Critique skill",
            )
            if skill_id == "critique"
            else None
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.skills.active_manifest.get_skill",
        lambda skill_id: (
            SimpleNamespace(
                id="critique",
                name="Critique",
                name_en="Critique",
                skill_dir=hidden_skill_dir,
                description="Critique skill",
            )
            if skill_id == "critique"
            else None
        ),
    )

    def fake_resolve_skill_content(skill, language, runtime_skill_dir=None):
        if getattr(skill, "id", None) == "critique":
            return SimpleNamespace(
                body="Point out structural weaknesses before finalizing.",
                source_root=hidden_skill_dir,
                frontmatter_status="ok",
                resolved_language=language,
                used_runtime_root=False,
                helper_files=[],
            )
        return SimpleNamespace(
            body="Build the deck.",
            source_root=active_skill_dir,
            frontmatter_status="ok",
            resolved_language=language,
            used_runtime_root=False,
            helper_files=[],
        )

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.summary_providers.resolve_skill_content",
        fake_resolve_skill_content,
    )

    partitions = _render_partitions(
        skill=SimpleNamespace(id="html-ppt", skill_dir=active_skill_dir, mode="deck", description="Deck skill"),
        skill_id="html-ppt",
        runtime_contract={
            "internal_hidden_skills": [
                {"id": "critique", "activation_source": "ai_resolved"},
            ]
        },
    )
    system = partitions["stable_system"]
    context = _context_text(partitions)

    assert "Internal hidden skill instructions:" in context
    assert "Loaded helper skill: Critique" in context
    assert "skill/SKILL.md" not in context
    assert "Internal hidden skill instructions:" not in system


def test_static_context_does_not_resolve_legacy_design_system_summary():
    system = _render_static(
        conversation={
            "artifact_mode": "web",
            "runtime_profile": "home",
            "design_system_id": {
                "type": "design_system",
                "design_system_id": "atelier-zero",
            },
        }
    )

    assert "Atelier Zero" not in system
    assert "Active design system:" not in system
    # The design system is only selected, not materialized into runtime context,
    # so no DESIGN.md body or its guidance should be injected (no false claims).
    assert "legacy design-system summaries" not in system
    assert "## Active design system -" not in system


def test_plan_gate_prompt_section_is_reusable():
    zh = PromptSections.plan_gate(
        phase="planning",
        language="zh",
        has_skill=True,
        has_plan=False,
        execution_locked=False,
    )
    en = PromptSections.plan_gate(
        phase="executing",
        language="en",
        has_skill=False,
        has_plan=True,
        execution_locked=True,
    )

    assert "request_plan_approval" in zh
    assert "request_plan_approval" in zh
    assert "started execution" in en


def test_main_turn_injects_current_outline_from_outline_runtime():
    partitions = _render_partitions(
        conversation={
            "artifact_mode": "web",
            "runtime_profile": "home",
            "phase": "executing",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"outline_id": "outline-plan", "title": "Fallback outline"},
                "execution_state": {
                    "status": "in_progress",
                    "steps": [{"id": "fallback-step", "status": "pending"}],
                },
            },
            "outline_runtime": {
                "current_outline": {
                    "outline_id": "outline-runtime",
                    "title": "Approved runtime outline",
                    "items": [{"id": "hero", "title": "Hero section"}],
                },
                "execution_state": {
                    "status": "in_progress",
                    "steps": [{"id": "runtime-step", "status": "in_progress"}],
                },
            },
        }
    )
    context = _context_text(partitions)

    assert "Plan state payload:" in context
    assert '"current_outline":{"outline_id":"outline-runtime"' in context
    assert "Approved runtime outline" in context
    assert "runtime-step" in context
    assert '"current_outline":{"outline_id":"outline-plan"' not in context


def test_main_turn_falls_back_to_plan_state_outline_when_runtime_outline_missing():
    partitions = _render_partitions(
        conversation={
            "artifact_mode": "web",
            "runtime_profile": "home",
            "phase": "executing",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {
                    "outline_id": "outline-plan",
                    "title": "Approved plan outline",
                },
                "execution_state": {
                    "status": "in_progress",
                    "steps": [{"id": "plan-step", "status": "pending"}],
                },
            },
            "outline_runtime": {},
        }
    )
    context = _context_text(partitions)

    assert "Plan state payload:" in context
    assert '"current_outline":{"outline_id":"outline-plan"' in context
    assert "Approved plan outline" in context
    assert "plan-step" in context


def test_runtime_profile_forbids_shell_script_writes():
    from app.services.agent_harness.core.contracts.runtime_capabilities import RuntimeCapabilities

    content = RuntimeCapabilities.prompt_section("en")

    assert "edit_file" in content
    assert "heredocs" in content
    assert "cat > file" in content
    assert "old_text/new_text replacements" in content
    # Design-system guidance now lives with the injected DESIGN.md body, not here.
    assert "design system" not in content.lower()
    assert "HARNESS_SKILL_ROOT" in content
    assert ".skill_runtime" not in content


def test_runtime_profile_clarifies_assets_are_media_only():
    from app.services.agent_harness.core.contracts.runtime_capabilities import RuntimeCapabilities

    zh = RuntimeCapabilities.prompt_section("zh")
    en = RuntimeCapabilities.prompt_section("en")

    assert "$HARNESS_REFERENCES_DIR" in zh
    assert "不要假设 project cwd 下存在 `references/...`" in zh
    assert "HARNESS_SKILL_ROOT" in zh
    assert ".skill_runtime" not in zh
    assert "$HARNESS_REFERENCES_DIR" in en
    assert "Do not assume `references/...` or `skill/...` exists under the project cwd" in en
    assert "HARNESS_SKILL_ROOT" in en
    assert ".skill_runtime" not in en
    # Cross-root traversal ban + skill-script copy-then-run guidance.
    assert "`../`" in zh and "path_outside_workspace" in zh
    assert "`../`" in en and "path_outside_workspace" in en
    assert "拷进当前 work 目录" in zh or "拷进 work" in zh
    assert "copy it into the current work directory" in en


def test_static_context_injects_prepared_workspace_block():
    from app.services.agent_harness.capabilities.skill_protocols.base import PreparedWorkspace

    partitions = _render_partitions(
        prepared_workspace=PreparedWorkspace(
            family="harness_full_deck_runtime",
            strategy="template_driven_deck",
            skill_id="html-ppt",
            artifact_work_root="html-ppt-prepared",
            entry_file="index.html",
            selected_template="pitch-deck",
            source_root="templates/full-decks/pitch-deck",
        )
    )
    system = partitions["stable_system"]
    context = _context_text(partitions)

    assert "Prepared workspace:" in context
    assert "Template default entry: index.html" in context
    assert "register_artifact defines the final deliverable identity" in context
    assert "project/html-ppt-prepared/" in context
    assert "Current artifact work directory: project/html-ppt-prepared/" in context
    assert "Prepared workspace:" not in system
