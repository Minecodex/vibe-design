from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.agent_harness.capabilities.skills.active_manifest import (
    build_active_skill_manifest,
)
from app.services.agent_harness.prompt_runtime.assembler import PromptRuntime
from app.services.agent_harness.prompt_runtime.models import (
    Phase,
    PromptMode,
    RenderedPromptBundle,
    TurnSpec,
)
from app.services.agent_harness.prompt_runtime.policy_engine import PolicyEngine
from app.services.agent_harness.prompt_runtime.side_classifier import classify_side_payload
from app.services.agent_harness.prompt_runtime.summary_providers import ProtocolSummaryProvider


def _base_spec(**overrides) -> TurnSpec:
    skill = SimpleNamespace(id="landing", name="Landing", name_en="Landing")
    conversation = {
        "phase": "executing",
        "artifact_mode": "web",
        "plan_state": {
            "title": "Landing page",
            "status": "in_progress",
            "current_step": "hero",
            "steps": [
                {"id": "hero", "title": "Hero", "status": "in_progress"},
                {"id": "proof", "title": "Proof", "status": "pending"},
            ],
        },
    }
    spec = TurnSpec(
        mode=PromptMode.MAIN_TURN,
        phase=Phase.EXECUTING,
        language="en",
        conversation=conversation,
        message_history=[{"role": "user", "content": "Build a premium landing page."}],
        artifact_mode="web",
        planning_directive="Keep the plan synchronized.",
        skill=skill,
        skill_id="landing",
        skill_prompt="Use the landing skill carefully.\n" + ("skill-rule " * 600),
        active_skill_manifest={
            "version": 1,
            "selected_skill_id": "landing",
            "skills": [
                {
                    "id": "landing",
                    "name": "Landing",
                    "activation_role": "selected_skill",
                    "purpose": "Use the landing skill carefully.",
                    "when_to_use": "Build or refine a landing page deliverable.",
                    "available_side_files": ["skill/references/authoring-guide.md", "skill/scripts/build.py"],
                    "side_file_index": ["skill/references/authoring-guide.md", "skill/scripts/build.py"],
                    "must_follow_constraints": [
                        'Read skill inputs through `base="skill"` or `SKILL_DIR`.',
                        "Prefer targeted reads before broad listing.",
                    ],
                }
            ],
        },
        workspace_runtime_session={
            "active_entry": "landing/index.html",
            "selected_direction": "editorial-contrast",
        },
        runtime_contract={
            "execution_strategy": "template_driven",
            "plan_context": {"brief": "Premium launch site"},
            "active_skill_context": {
                "kind": "selected_skill_active_context",
                "skill_id": "landing",
                "runtime_body": "Loaded active skill body.",
                "source_path": "SKILL.md",
                "truncation_mode": "full",
            },
            "active_design_system_context": {
                "kind": "active_design_system_context",
                "design_system_id": "atelier-zero",
                "title": "Atelier Zero",
                "usage_md": "Use the active design system before composing UI.",
                "design_md": "## Tokens\n- Primary: #111111\n- Accent: #D4B483",
                "tokens_css": ":root { --accent: #D4B483; --fg: #111111; }",
                "components_manifest": "selectors: .btn, .card\ncomponentGroups:\n- Buttons; selectors=.btn",
                "loaded_paths": ["design_system/atelier-zero/DESIGN.md"],
                "source_digest": "design-digest",
                "import_mode": "normalized",
            },
        },
        manifest_summary={"files": [{"path": "work/index.html", "kind": "html"}]},
        past_context_recall="Use search_harness_history for older turns.",
        current_outline={"status": "in_progress"},
    )
    for key, value in overrides.items():
        setattr(spec, key, value)
    if "active_skill_manifest" not in overrides and {"skill", "skill_id", "skill_prompt"} & set(overrides):
        spec.active_skill_manifest = None
    return spec


def test_prompt_runtime_main_turn_assembly_order_and_rule_uniqueness():
    bundle = PromptRuntime().build_bundle(_base_spec())

    ordered_ids = [block.id for block in bundle.all_blocks]
    assert ordered_ids[:4] == [
        "base.instructions",
        "environment.workspace_contract",
        "environment.runtime_capabilities",
        "environment.artifact_mode",
    ]
    assert ordered_ids.index("state.active_design_system_usage") < ordered_ids.index("state.active_skill_body")
    assert ordered_ids.index("state.active_design_system_body") < ordered_ids.index("state.active_skill_body")
    assert ordered_ids.index("state.active_design_system_tokens") < ordered_ids.index("state.active_skill_body")
    assert ordered_ids.index("state.active_design_system_components") < ordered_ids.index("state.active_skill_body")
    assert ordered_ids.index("state.active_skill_body") < ordered_ids.index("environment.artifact_manifest_workflow")
    assert ordered_ids.index("environment.artifact_manifest_workflow") < ordered_ids.index("summary.skill")
    assert ordered_ids.index("summary.skill") < ordered_ids.index("phase.policy")
    assert ordered_ids.index("phase.policy") < ordered_ids.index("state.workspace_runtime")
    assert ordered_ids.index("summary.skill") < ordered_ids.index("delta.planning")
    assert ordered_ids[-1] == "state.workspace_runtime"
    assert bundle.trace["rule_family_counts"]["identity"] == 1
    assert bundle.trace["rule_family_counts"]["filesystem_runtime_publish"] == 1
    assert bundle.trace["rule_family_counts"]["phase_behavior"] == 1


def test_prompt_runtime_injects_craft_references_before_skill_body():
    spec = _base_spec(
        skill=SimpleNamespace(
            id="landing",
            name="Landing",
            name_en="Landing",
            craft=SimpleNamespace(requires=["future-craft", "anti-ai-slop", "anti-ai-slop"]),
        ),
        active_skill_manifest=None,
    )
    bundle = PromptRuntime().build_bundle(spec)

    ordered_ids = [block.id for block in bundle.all_blocks]
    assert "state.active_craft_refs" in ordered_ids
    assert ordered_ids.index("state.active_craft_refs") < ordered_ids.index("state.active_skill_body")

    craft_block = next(block for block in bundle.all_blocks if block.id == "state.active_craft_refs")
    assert "## Active craft references - anti-ai-slop" in craft_block.content
    assert "# Anti-AI-slop rules" in craft_block.content
    assert "The seven cardinal sins" in craft_block.content
    assert "future-craft" not in craft_block.content
    assert craft_block.content.count("# Anti-AI-slop rules") == 1
    assert craft_block.metadata["craft_requires"] == ["anti-ai-slop"]


def test_prompt_runtime_omits_craft_references_without_requires():
    spec = _base_spec(
        skill=SimpleNamespace(id="landing", name="Landing", name_en="Landing", craft=SimpleNamespace(requires=[])),
    )
    bundle = PromptRuntime().build_bundle(spec)
    assert "state.active_craft_refs" not in [block.id for block in bundle.all_blocks]


def test_prompt_runtime_omits_craft_references_when_no_required_files_resolve():
    spec = _base_spec(
        skill=SimpleNamespace(
            id="landing",
            name="Landing",
            name_en="Landing",
            craft=SimpleNamespace(requires=["future-craft"]),
        ),
    )
    bundle = PromptRuntime().build_bundle(spec)
    assert "state.active_craft_refs" not in [block.id for block in bundle.all_blocks]


def test_prompt_runtime_does_not_inject_prompt_only_quality_gate():
    bundle = PromptRuntime().build_bundle(_base_spec(artifact_mode="web"))

    assert "environment.artifact_quality_gate" not in [block.id for block in bundle.all_blocks]


def test_prompt_runtime_prepared_workspace_does_not_inject_compose_recipe(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "scripts" / "compose.ts").write_text("// composer", encoding="utf-8")
    (skill_dir / "inputs.example.json").write_text("{}", encoding="utf-8")
    spec = _base_spec(
        skill=SimpleNamespace(id="script-skill", name="Script Skill", name_en="Script Skill", skill_dir=skill_dir),
        prepared_workspace={"artifact_work_root": "script-prepared", "entry_file": "index.html"},
    )

    bundle = PromptRuntime().build_bundle(spec)
    block = next(block for block in bundle.all_blocks if block.id == "environment.prepared_workspace")

    assert "Script-driven compose recipe" not in block.content
    assert "scripts/compose.ts" not in block.content


def test_prompt_runtime_places_loaded_skill_body_before_volatile_turn_policy():
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            runtime_contract={
                "active_skill_context": {
                    "skill_id": "landing",
                    "runtime_body": "Loaded skill body.",
                    "source_path": "SKILL.md",
                    "truncation_mode": "full",
                }
            }
        )
    )

    ordered_ids = [block.id for block in bundle.all_blocks]

    assert ordered_ids.index("state.active_skill_body") < ordered_ids.index("phase.policy")
    assert ordered_ids.index("state.active_skill_body") < ordered_ids.index("state.workspace_runtime")


def test_prompt_runtime_injects_canvas_media_contract_before_skill_body():
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            conversation={"phase": "executing", "artifact_mode": "image", "runtime_profile": "canvas"},
            artifact_mode="image",
        )
    )

    ordered_ids = [block.id for block in bundle.all_blocks]
    canvas_block = next(block for block in bundle.all_blocks if block.id == "environment.canvas_media_operation")

    assert ordered_ids.index("environment.canvas_media_operation") < ordered_ids.index("state.active_skill_body")
    assert canvas_block.layer == "system"
    assert "Canvas media operation contract:" in canvas_block.content
    assert "copy the relevant tool_reference exactly into reference_image_urls" in canvas_block.content
    assert "override selected skill workflows" in canvas_block.content


def test_prompt_runtime_home_open_design_html_allows_conditional_artifact_emission():
    bundle = PromptRuntime().build_bundle(_base_spec())

    workflow_block = next(block for block in bundle.all_blocks if block.id == "environment.artifact_manifest_workflow")

    assert "must never emit `<artifact>`" not in workflow_block.content
    assert "you may emit exactly one complete artifact" in workflow_block.content
    assert "write_file + register_artifact + publish_output" in workflow_block.content


def test_prompt_runtime_canvas_media_does_not_get_home_artifact_emission_rule():
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            conversation={"phase": "executing", "artifact_mode": "image", "runtime_profile": "canvas"},
            artifact_mode="image",
        )
    )

    assert "environment.artifact_manifest_workflow" not in [block.id for block in bundle.all_blocks]


def test_prompt_runtime_uses_manifest_summary_for_skill_and_full_active_design_system():
    spec = _base_spec(phase=Phase.PLANNING, conversation={"phase": "planning"})
    bundle = PromptRuntime().build_bundle(spec)

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")
    design_block = next(block for block in bundle.all_blocks if block.id == "state.active_design_system_body")
    tokens_block = next(block for block in bundle.all_blocks if block.id == "state.active_design_system_tokens")

    assert "skill-rule skill-rule skill-rule" in skill_block.content
    assert "Use the landing skill carefully." in skill_block.content
    assert len(skill_block.content) > len(spec.skill_prompt)
    assert skill_block.metadata["injection_mode"] == "full_skill_body"
    assert "Recommended first reads:" not in skill_block.content
    assert "preferred_first_action" not in skill_block.content
    assert "Read `skill/SKILL.md" not in skill_block.content
    assert "## Active design system - Atelier Zero" in design_block.content
    assert "- Accent: #D4B483" in design_block.content
    assert "--accent: #D4B483" in tokens_block.content
    assert {"fragment_id": "summary.protocol", "provider": "ProtocolSummaryProvider"} in bundle.trace["long_doc_summaries"]


def test_prompt_runtime_observability_trace_records_fragment_tokens_and_omissions():
    bundle = PromptRuntime().build_bundle(_base_spec(skill_prompt=None, skill=None, skill_id=None))

    assert bundle.trace["mode"] == "main_turn"
    assert bundle.trace["phase"] == "executing"
    assert bundle.trace["included_fragments"]
    assert all("token_estimate" in item for item in bundle.trace["included_fragments"])
    assert bundle.trace["state_payload_sizes"]["manifest_summary"] > 0
    omitted_ids = {item["id"] for item in bundle.trace["omitted_fragments"]}
    assert "summary.skill" in omitted_ids


def test_prompt_runtime_fragment_plan_is_provider_independent():
    runtime = PromptRuntime()

    anthropic_bundle = runtime.build_bundle(_base_spec(builtin_provider="anthropic"))
    generic_bundle = runtime.build_bundle(_base_spec(builtin_provider="openai"))

    anthropic_ids = [item["id"] for item in anthropic_bundle.trace["included_fragments"]]
    generic_ids = [item["id"] for item in generic_bundle.trace["included_fragments"]]

    assert anthropic_ids == generic_ids


def test_prompt_runtime_main_turn_carries_message_history_into_bundle():
    messages = [
        {"role": "user", "content": "Build a premium landing page."},
        {"role": "assistant", "content": "I will inspect the current files first."},
    ]
    bundle = PromptRuntime().build_bundle(_base_spec(message_history=messages))

    assert bundle.messages == messages
    assert bundle.trace["message_token_estimate"] > 0


def test_policy_engine_limits_planning_tools_and_routes_plan_lifecycle_tools():
    decision = PolicyEngine().resolve(
        TurnSpec(
            mode=PromptMode.MAIN_TURN,
            phase=Phase.PLANNING,
            language="en",
            conversation={"phase": "planning"},
            web_search_call_count=3,
        )
    )

    assert "update_planning_draft" in decision.allowed_tools
    assert "request_plan_approval" in decision.allowed_tools
    assert "generate_image" in decision.allowed_tools
    assert "generate_video" in decision.allowed_tools
    assert "web_search" not in decision.allowed_tools
    assert decision.require_plan_sync is False
    assert "deliverable_plan" in decision.required_outputs
    assert "Do not modify workspace files during planning; media generation is allowed when it helps validate direction or references." in decision.notes
    assert "Use update_planning_draft for non-approval planning notes, ask_user for unresolved user decisions, and request_plan_approval only when the plan is complete enough for execution approval." in decision.notes
    assert "During planning, call web_search at most 3 times; after that use fetch_webpage or proceed with known information." in decision.notes


def test_policy_engine_carries_execution_progress_rules():
    decision = PolicyEngine().resolve(
        TurnSpec(
            mode=PromptMode.MAIN_TURN,
            phase=Phase.EXECUTING,
            language="en",
            conversation={"phase": "executing"},
        )
    )

    assert decision.require_plan_sync is False
    assert "Use update_execution_progress only when user-visible execution state changes or major milestones complete." in decision.notes
    assert "When a step starts, mark it in_progress; when it finishes, mark it completed." in decision.notes
    assert "Normal assistant progress text does not update the plan card." in decision.notes
    assert any("For missing-input collection" in note for note in decision.notes)
    assert any("does not override canvas or active-skill stage gates" in note for note in decision.notes)
    assert any("then call ask_user for the decision" in note for note in decision.notes)
    assert any("Narrate as you work" in note for note in decision.notes)


def test_executing_phase_policy_does_not_advertise_empty_allowed_tools():
    bundle = PromptRuntime().build_bundle(_base_spec())
    phase_block = next(block for block in bundle.all_blocks if block.id == "phase.policy")

    assert '"allowed_tools"' not in phase_block.content
    assert "then call ask_user for the decision" in phase_block.content


def test_policy_engine_resolves_pre_final_gate_actions():
    engine = PolicyEngine()

    plan_sync = engine.resolve_pre_final_gate(
        tool_calls_present=False,
        plan_gate_used=False,
        plan_needs_sync=True,
        artifact_manifest_action=None,
    )
    manifest_gate = engine.resolve_pre_final_gate(
        tool_calls_present=False,
        plan_gate_used=True,
        plan_needs_sync=False,
        artifact_manifest_action="register",
    )
    none_case = engine.resolve_pre_final_gate(
        tool_calls_present=True,
        plan_gate_used=False,
        plan_needs_sync=True,
        artifact_manifest_action="register",
    )

    assert plan_sync.action == "plan_sync"
    assert manifest_gate.action == "artifact_manifest"
    assert none_case.action is None


def test_policy_engine_resolves_recovery_stop_actions():
    engine = PolicyEngine()

    finalize = engine.resolve_recovery_stop_action(
        phase="executing",
        artifact_available=True,
        revision_plan_updated=False,
    )
    fail_revision = engine.resolve_recovery_stop_action(
        phase="revising_plan",
        artifact_available=False,
        revision_plan_updated=False,
    )
    block = engine.resolve_recovery_stop_action(
        phase="executing",
        artifact_available=False,
        revision_plan_updated=True,
    )

    assert finalize.action == "finalize_after_artifact"
    assert fail_revision.action == "fail_plan_revision"
    assert block.action == "block"


def test_prompt_runtime_home_open_design_full_skill_body_stays_bounded():
    spec = _base_spec(phase=Phase.PLANNING, conversation={"phase": "planning"})
    bundle = PromptRuntime().build_bundle(spec)
    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")

    assert skill_block.metadata["injection_mode"] == "full_skill_body"
    assert "skill-rule skill-rule skill-rule" in skill_block.content
    # Drift-guardrail baseline (raised from 9500 for accumulated runtime/prompt content;
    # actual ~9583). Keep tight to catch real prompt bloat.
    assert bundle.token_estimate < 9700


def test_prompt_runtime_uses_active_skill_manifest_from_runtime_root(tmp_path):
    source_dir = tmp_path / "skills" / "landing"
    source_dir.mkdir(parents=True)
    (source_dir / "SKILL.md").write_text(
        "---\nname: landing\n---\nSource intro\nSource trailing rule\n",
        encoding="utf-8",
    )

    runtime_dir = tmp_path / "work" / ".skill_runtime" / "landing"
    (runtime_dir / "assets").mkdir(parents=True)
    (runtime_dir / "references").mkdir()
    (runtime_dir / "scripts").mkdir()
    (runtime_dir / "SKILL.md").write_text(
        "---\nname: landing\n---\nRuntime intro\nRuntime trailing rule\n",
        encoding="utf-8",
    )

    spec = _base_spec(
        language="zh",
        skill=SimpleNamespace(id="landing", name="Landing", name_en="Landing", skill_dir=source_dir),
        skill_id="landing",
        skill_prompt="Fallback text should not win.",
        skill_runtime_dir=runtime_dir,
        active_skill_manifest=build_active_skill_manifest(
            language="zh",
            skill=SimpleNamespace(id="landing", name="Landing", name_en="Landing", skill_dir=source_dir),
            skill_id="landing",
            prompt_body="Fallback text should not win.",
            runtime_skill_dir=runtime_dir,
            runtime_contract=None,
        ),
    )
    bundle = PromptRuntime().build_bundle(spec)

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")

    assert skill_block.metadata["injection_mode"] == "full_skill_body"
    assert skill_block.metadata["used_runtime_root"] is True
    assert skill_block.metadata["resolved_language"] == "zh"
    assert "skill/SKILL.md" not in skill_block.content
    assert "Runtime intro" in skill_block.content
    assert ".skill_runtime" not in skill_block.content
    assert {"fragment_id": "summary.skill", "provider": "SkillSummaryProvider"} not in bundle.trace["long_doc_summaries"]


def test_prompt_runtime_injects_selected_skill_body_and_side_file_hints_from_runtime_contract():
    runtime_contract = {
        "active_skill_context": {
            "skill_id": "landing",
            "language": "en",
            "source_path": "SKILL.md",
            "source_body": "Full selected skill body",
            "runtime_body": "# Workflow\nFollow the selected skill steps.",
            "source_digest": "abc123",
            "truncation_mode": "full",
            "builder_version": 1,
            "loaded_paths": ["skill/SKILL.md"],
            "on_demand_paths": ["skill/references", "skill/scripts/build.py", "skill/example.html"],
            "link_targets": ["skill/references/authoring-guide.md"],
        }
    }

    bundle = PromptRuntime().build_bundle(_base_spec(runtime_contract=runtime_contract))

    active_body_block = next(block for block in bundle.all_blocks if block.id == "state.active_skill_body")
    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")

    assert "Active selected skill body:" in active_body_block.content
    assert "Follow the selected skill steps." in active_body_block.content
    assert "Selected skill side files are not preloaded by default." in active_body_block.content
    assert "read_file(path=\"skill/" in active_body_block.content
    assert "list_files(path=\"skill/references\", recursive=false)" in active_body_block.content
    assert "skill/references/authoring-guide.md" in active_body_block.content
    assert "skill/SKILL.md" in active_body_block.content
    assert "Active skill instructions:" in skill_block.content
    assert ".skill_runtime" not in active_body_block.content


def test_prompt_runtime_does_not_inject_template_preflight_or_master_body():
    runtime_contract = {
        "active_skill_context": {
            "skill_id": "html-ppt-product-launch",
            "language": "en",
            "source_path": "SKILL.md",
            "source_body": "Wrapper source",
            "runtime_body": "# Wrapper body\nUse product-launch rules.",
            "source_digest": "abc123",
            "truncation_mode": "full",
            "builder_version": 1,
            "loaded_paths": ["skill/SKILL.md"],
            "on_demand_paths": [],
            "link_targets": [],
            "template_support_state": "supported",
            "template_relation": {"kind": "wrapper", "primary_master_id": "html-ppt"},
            "template_preflight": {
                "runtime_entry_strategy": "edit-example",
                "context_sources": ["skill/_linked/html-ppt/SKILL.md"],
                "available_side_files": ["skill/example.html"],
                "seed_template_files": ["skill/template.json"],
                "execution_constraints": ["Keep final deliverables under project/."],
            },
            "linked_template_contexts": [
                {
                    "template_id": "html-ppt",
                    "source_path": "skill/_linked/html-ppt/SKILL.md",
                    "runtime_body": "# Master body\nPreserve deck runtime.",
                }
            ],
        }
    }

    bundle = PromptRuntime().build_bundle(
        _base_spec(
            skill=SimpleNamespace(id="html-ppt-product-launch", name="Product Launch", name_en="Product Launch"),
            skill_id="html-ppt-product-launch",
            runtime_contract=runtime_contract,
        )
    )

    active_body_block = next(block for block in bundle.all_blocks if block.id == "state.active_skill_body")
    content = active_body_block.content

    assert "Template preflight:" not in content
    assert "Linked master template body:" not in content
    assert "Template relation:" not in content
    assert "Runtime entry strategy: edit-example" not in content
    assert "skill/template.json" not in content
    assert "Use product-launch rules." in content
    assert "Preserve deck runtime." not in content


def test_prompt_runtime_injects_full_design_system_from_active_context():
    design_body = "## Tokens\n" + "\n".join(f"- Rule {index}" for index in range(40))
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            skill=SimpleNamespace(id="kami-landing", name="Kami", name_en="Kami"),
            skill_id="kami-landing",
            runtime_contract={
                "active_design_system_context": {
                    "kind": "active_design_system_context",
                    "design_system_id": "kami",
                    "title": "Kami",
                    "usage_md": "Use Kami before writing UI.",
                    "design_md": design_body,
                    "tokens_css": ":root { --paper: #ffffff; }",
                    "components_manifest": "selectors: .kami-card",
                },
                "active_skill_context": {
                    "skill_id": "kami-landing",
                    "runtime_body": "# Kami body",
                    "truncation_mode": "full",
                    "template_support_state": "supported",
                }
            },
        )
    )

    design_block = next(block for block in bundle.all_blocks if block.id == "state.active_design_system_body")
    tokens_block = next(block for block in bundle.all_blocks if block.id == "state.active_design_system_tokens")

    assert "## Active design system - Kami" in design_block.content
    assert "Rule 39" in design_block.content
    assert "--paper" in tokens_block.content
    # Guidance is co-located with the injected DESIGN.md body and only appears
    # when the design system is materialized into runtime context.
    assert "legacy design-system summaries" in design_block.content
    assert "do not call read_file on DESIGN.md again" in design_block.content


def test_prompt_runtime_does_not_inject_helper_skill_body_as_selected_skill_body():
    runtime_contract = {
        "internal_hidden_skills": [{"id": "critique"}],
        "active_skill_context": {
            "skill_id": "landing",
            "language": "en",
            "source_path": "SKILL.md",
            "source_body": "Selected source",
            "runtime_body": "Selected runtime body only.",
            "source_digest": "abc123",
            "truncation_mode": "full",
            "builder_version": 1,
            "loaded_paths": ["skill/SKILL.md"],
            "on_demand_paths": [],
            "link_targets": [],
        },
    }

    bundle = PromptRuntime().build_bundle(
        _base_spec(
            runtime_contract=runtime_contract,
            active_skill_manifest={
                "version": 1,
                "selected_skill_id": "landing",
                "skills": [
                    {
                        "id": "landing",
                        "name": "Landing",
                        "activation_role": "selected_skill",
                        "purpose": "Primary landing page skill.",
                        "available_side_files": [],
                        "side_file_index": [],
                        "must_follow_constraints": [],
                    },
                    {
                        "id": "critique",
                        "name": "Critique",
                        "activation_role": "internal_helper",
                        "purpose": "Review choices.",
                        "available_side_files": ["skill/references/critique-guide.md"],
                        "side_file_index": ["skill/references/critique-guide.md"],
                        "must_follow_constraints": [],
                    },
                ],
            },
        )
    )

    active_body_block = next(block for block in bundle.all_blocks if block.id == "state.active_skill_body")

    assert "Selected runtime body only." in active_body_block.content
    assert "critique-guide" not in active_body_block.content


def test_prompt_runtime_includes_internal_helper_skill_manifest_guidance():
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            runtime_contract={"internal_hidden_skills": [{"id": "critique"}]},
            active_skill_manifest={
                "version": 1,
                "selected_skill_id": "landing",
                "skills": [
                    {
                        "id": "landing",
                        "name": "Landing",
                        "activation_role": "selected_skill",
                        "purpose": "Primary landing page skill.",
                        "available_side_files": [],
                        "side_file_index": [],
                        "must_follow_constraints": [],
                    },
                    {
                        "id": "critique",
                        "name": "Critique",
                        "activation_role": "internal_helper",
                        "purpose": "Review structure and tighten choices.",
                        "available_side_files": ["skill/references/critique-guide.md"],
                        "side_file_index": ["skill/references/critique-guide.md"],
                        "must_follow_constraints": [],
                    },
                ],
            },
        )
    )

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")

    assert "Loaded helper skill: Critique" in skill_block.content
    assert "skill/references/critique-guide.md" in skill_block.content
    assert ".skill_runtime" not in skill_block.content


def test_prompt_runtime_design_skill_summary_surfaces_visual_chain_rules():
    design_prompt = """
## 视觉资产继承规则
- 若下一步与上一轮结果存在明显的继承关系，应优先沿用上一轮已确认结果的引用继续推进，不要只把它改写成文字描述后重做一个看似相近的新版本。
- 若下一步属于独立探索、横向比稿或故意脱离前序成果的新方向，可以不继续沿用上一轮结果，但应把它视为新的设计分支。
"""
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            language="zh",
            skill=SimpleNamespace(id="logo", name="Logo", name_en="Logo", scenario="design", tools=["generate_image", "ask_user"]),
            skill_prompt=design_prompt,
        )
    )

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")
    system_prompt = bundle.system_blocks[0].content

    assert "视觉资产继承规则" in skill_block.content
    assert "优先沿用上一轮已确认结果的引用继续推进" in skill_block.content
    assert "同一设计链上的工作应优先沿用该结果的引用继续推进" not in system_prompt


def test_prompt_runtime_canvas_selected_skill_injects_full_skill_body():
    design_prompt = """
# Logo 设计总监

## 图片生成确认与依赖硬规则
- 所有图片生成都是“确认后的单步执行”：先说明要基于哪张已确认图片继续、当前步骤要生成什么，再获得用户确认，最后才允许调用 `generate_image`
- 图片生成完成后必须停在当前资产评审，不在同一轮自动生成下一张依赖图片

## 阶段六：Logo 核心方案推演
- 生成前必须让用户确认：是否基于阶段五已确认色彩/字体系统图片和阶段四已确认情绪板图片继续生成 Logo 核心方案图
"""
    bundle = PromptRuntime().build_bundle(
        _base_spec(
            language="zh",
            conversation={"phase": "executing", "runtime_profile": "canvas"},
            skill=SimpleNamespace(id="logo", name="Logo", name_en="Logo", scenario="design", tools=["generate_image", "ask_user"]),
            skill_id="logo",
            skill_prompt=design_prompt,
            active_skill_manifest=None,
        )
    )

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")

    assert "Skill 文档正文:" in skill_block.content
    assert "所有图片生成都是“确认后的单步执行”" in skill_block.content
    assert "图片生成完成后必须停在当前资产评审" in skill_block.content
    assert "阶段六：Logo 核心方案推演" in skill_block.content
    assert skill_block.metadata["injection_mode"] == "full_skill_body"


def test_side_call_prompt_builders_delegate_to_prompt_runtime(monkeypatch):
    from app.services.agent_harness.authoring.planning import (
        decision_resolver,
        design_system_selection_resolver,
        discovery_runtime,
    )

    seen: list[tuple[str, str]] = []

    class FakeRuntime:
        def build_bundle(self, spec: TurnSpec) -> RenderedPromptBundle:
            seen.append((spec.mode.value, spec.language))
            return RenderedPromptBundle(
                mode=spec.mode,
                phase=spec.phase_value,
                system_blocks=[],
                messages=[{"role": "user", "content": "{}"}],
                trace={},
            )

    monkeypatch.setattr(discovery_runtime, "_PROMPT_RUNTIME", FakeRuntime())
    monkeypatch.setattr(decision_resolver, "_PROMPT_RUNTIME", FakeRuntime())
    monkeypatch.setattr(design_system_selection_resolver, "_PROMPT_RUNTIME", FakeRuntime())

    discovery_runtime._build_discovery_schema_system_prompt("en", design_system_selected=False)  # noqa: SLF001
    discovery_runtime._build_discovery_schema_user_prompt(  # noqa: SLF001
        conversation={},
        language="en",
        artifact_family="web",
        skill=None,
        has_reference_attachments=False,
        user_id=None,
    )
    decision_resolver._selection_resolver_system_prompt()  # noqa: SLF001
    design_system_selection_resolver._design_system_selection_system_prompt()  # noqa: SLF001

    assert ("planning_schema_generation", "en") in seen
    assert ("skill_selection", "en") in seen
    assert ("design_system_selection", "en") in seen


def test_prompt_runtime_side_modes_use_mode_specific_fragment_plans():
    runtime = PromptRuntime()

    selection_bundle = runtime.build_bundle(
        TurnSpec(
            mode=PromptMode.SKILL_SELECTION,
            phase=Phase.PLANNING,
            language="en",
            side_payload={
                "runtime_time": {"date": "2026-05-15"},
                "artifact_mode": "web",
                "request": "Create a launch page",
                "attachments_summary": "none",
                "current_skill_id": None,
                "resolve_skill": True,
                "skill_candidates": [{"id": "landing", "name": "Landing"}],
            },
        )
    )
    recovery_bundle = runtime.build_bundle(
        TurnSpec(
            mode=PromptMode.RECOVERY_TURN,
            phase=Phase.RECOVERY,
            language="en",
            recovery_decision="switch_strategy",
            recovery_review={
                "failure_kind": "read_timeout",
                "output_excerpt": "timeout",
                "recovery_hint": {"preferred_tools": ["read_file"]},
            },
        )
    )

    selection_ids = [item["id"] for item in selection_bundle.trace["included_fragments"]]
    recovery_ids = [item["id"] for item in recovery_bundle.trace["included_fragments"]]
    assert "state.selection_request" in selection_ids
    assert "state.runtime_time_payload" in selection_ids
    assert "phase.policy" not in selection_ids
    assert "state.failure_state" in recovery_ids
    assert "delta.recovery" in recovery_ids


def test_summary_providers_emit_structured_fields_in_metadata():
    bundle = PromptRuntime().build_bundle(_base_spec())

    skill_block = next(block for block in bundle.all_blocks if block.id == "summary.skill")
    protocol_block = next(block for block in bundle.all_blocks if block.id == "summary.protocol")

    for block in (skill_block, protocol_block):
        fields = block.metadata.get("summary_fields")
        assert isinstance(fields, dict)
        assert "purpose" in fields
        assert "must_follow_constraints" in fields
        assert "source_paths" in fields


def test_protocol_summary_provider_normalizes_skill_local_paths_for_model(tmp_path):
    skill_dir = tmp_path / "skill"
    (skill_dir / "assets").mkdir(parents=True)
    (skill_dir / "references").mkdir(parents=True)
    skill = SimpleNamespace(
        id="seed-template",
        mode="prototype",
        surface=None,
        system_prompt="Read assets/template.html and references/checklist.md first.",
        skill_dir=skill_dir,
    )

    content, metadata = ProtocolSummaryProvider().summarize(
        language="en",
        skill=skill,
        artifact_mode="web",
        prepared_workspace=None,
        workspace_runtime_session=None,
    )

    assert "Read these skill protocol files before generating" not in content
    assert "continue from skill/assets/template.html" not in content
    assert metadata["summary_fields"]["source_paths"] == []


def test_prompt_runtime_token_baselines_stay_bounded():
    runtime = PromptRuntime()
    planning_bundle = runtime.build_bundle(_base_spec(phase=Phase.PLANNING, conversation={"phase": "planning"}))
    main_bundle = runtime.build_bundle(_base_spec())
    recovery_bundle = runtime.build_bundle(
        TurnSpec(
            mode=PromptMode.RECOVERY_TURN,
            phase=Phase.RECOVERY,
            language="en",
            recovery_decision="switch_strategy",
            recovery_review={
                "failure_kind": "read_timeout",
                "output_excerpt": "timeout",
                "recovery_hint": {"preferred_tools": ["read_file"], "constraints": ["Do not repeat the same check."]},
            },
        )
    )
    final_bundle = runtime.build_bundle(
        TurnSpec(
            mode=PromptMode.FINAL_SUMMARY,
            phase=Phase.FINALIZING,
            language="en",
            side_payload={"title": "Landing", "artifact_path": "published/report.html"},
        )
    )

    assert planning_bundle.token_estimate < 9700
    # Raised from 10000 (actual ~10110) for the executing-phase "narrate as you work"
    # tool-preamble guidance that brings per-step explanations in line with peer CLIs.
    assert main_bundle.token_estimate < 10300
    assert recovery_bundle.token_estimate < 1200
    # Raised from 800 (actual ~955) for accumulated final-bundle prompt content.
    assert final_bundle.token_estimate < 1000


def test_side_classifier_uses_prompt_runtime_mode(monkeypatch):
    traces: list[dict] = []

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, response_schema: dict, provider_code=None):
        assert "runtime_time" in user_prompt
        return {"label": "needs_skill", "confidence": 0.82}

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier._call_side_classifier_model",
        _fake_call,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier.persist_prompt_bundle_trace",
        lambda user_id, conversation_id, run_id, bundle, summary=None: traces.append(
            {"user_id": user_id, "conversation_id": conversation_id, "run_id": run_id, "trace_type": "prompt_bundle_assembled", "payload": bundle.trace, "summary": summary}
        ),
    )

    result = asyncio.run(
        classify_side_payload(
            label_space=["needs_skill", "generic"],
            payload={"request": "做一个产品落地页", "runtime_time": {"current_date": "2026-05-15"}},
            model_name="gpt-4.1",
            user_id=7,
            conversation_id="conv-classifier",
            run_id="run-classifier-1",
        )
    )

    assert result["label"] == "needs_skill"
    assert traces[0]["payload"]["mode"] == "side_classifier"


def test_side_classifier_preserves_preflight_model_call(monkeypatch):
    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, response_schema: dict, provider_code=None):
        return {
            "label": "artifact_creation",
            "confidence": 0.92,
            "_preflight_model_call": {
                "model_name": model_name,
                "usage": {"input_tokens": 11, "output_tokens": 4},
                "elapsed_ms": 29,
                "kind": "home_turn_router",
            },
        }

    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier._call_side_classifier_model",
        _fake_call,
    )

    result = asyncio.run(
        classify_side_payload(
            label_space=["artifact_creation", "informational_turn"],
            payload={"request": "做一个网站"},
            model_name="router-model",
        )
    )

    assert result == {
        "label": "artifact_creation",
        "confidence": 0.92,
        "_preflight_model_call": {
            "model_name": "router-model",
            "usage": {"input_tokens": 11, "output_tokens": 4},
            "elapsed_ms": 29,
            "kind": "home_turn_router",
        },
    }


def test_side_classifier_uses_runtime_rendered_system_prompt(monkeypatch):
    seen: dict[str, str] = {}

    class FakeRuntime:
        def build_bundle(self, spec: TurnSpec) -> RenderedPromptBundle:
            return RenderedPromptBundle(
                mode=spec.mode,
                phase=spec.phase_value,
                system_blocks=[
                    type("Block", (), {"content": "runtime-side-system"})(),
                ],
                messages=[{"role": "user", "content": '{"label_space":["needs_skill"]}'}],
                trace={},
            )

    async def _fake_call(*, system_prompt: str, user_prompt: str, model_name: str, response_schema: dict, provider_code=None):
        seen["system_prompt"] = system_prompt
        seen["user_prompt"] = user_prompt
        return {"label": "needs_skill", "confidence": 0.9}

    monkeypatch.setattr("app.services.agent_harness.prompt_runtime.side_classifier._PROMPT_RUNTIME", FakeRuntime())
    monkeypatch.setattr(
        "app.services.agent_harness.prompt_runtime.side_classifier._call_side_classifier_model",
        _fake_call,
    )

    result = asyncio.run(
        classify_side_payload(
            label_space=["needs_skill", "generic"],
            payload={"request": "做一个产品落地页", "runtime_time": {"current_date": "2026-05-15"}},
            model_name="gpt-4.1",
        )
    )

    assert result["label"] == "needs_skill"
    assert seen["system_prompt"] == "runtime-side-system"

