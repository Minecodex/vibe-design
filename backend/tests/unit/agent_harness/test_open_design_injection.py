from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.agent_harness.capabilities.design_systems import (
    DesignSystemDefinition,
)
from app.services.agent_harness.capabilities.design_systems import (
    active_context as design_active_context,
)
from app.services.agent_harness.capabilities.design_systems.token_contract import (
    evaluate_design_system_health,
)
from app.services.agent_harness.capabilities.design_systems.token_schema import TOKEN_SCHEMA
from app.services.agent_harness.capabilities.skills.active_context import (
    build_selected_skill_active_context,
)
from app.services.agent_harness.prompt_runtime import PromptMode, PromptRuntime, TurnSpec


def _design_systems_module():
    import app.services.agent_harness.capabilities.design_systems as module

    return module


def _token_block(accent: str = "#123456") -> str:
    values = {
        "--bg": "#ffffff",
        "--surface": "#f8fafc",
        "--fg": "#111827",
        "--muted": "#64748b",
        "--border": "#e2e8f0",
        "--accent": accent,
        "--font-display": "Inter, sans-serif",
        "--font-body": "Inter, sans-serif",
        "--text-base": "16px",
        "--radius-md": "12px",
        "--focus-ring": "0 0 0 3px rgba(18, 52, 86, 0.2)",
        "--container-max": "1120px",
    }
    lines = [":root {"]
    for spec in TOKEN_SCHEMA:
        value = values.get(spec.name) or spec.alias_to or spec.fallback or _test_token_fallback(spec.name)
        lines.append(f"  {spec.name}: {value};")
    lines.append("}")
    return "\n".join(lines)


def _test_token_fallback(name: str) -> str:
    if name.startswith("--font-"):
        return "Inter, sans-serif"
    if name.startswith("--text-"):
        return "16px"
    if name.startswith("--leading-"):
        return "1.5"
    if name.startswith("--tracking-"):
        return "0"
    if name.startswith("--section-y-"):
        return "48px"
    if name.startswith("--container-gutter-"):
        return "16px"
    return "initial"


def test_design_system_loader_reads_open_design_assets(monkeypatch, tmp_path):
    module = _design_systems_module()
    root = tmp_path / "systems"
    system_dir = root / "sample"
    system_dir.mkdir(parents=True)
    (system_dir / "manifest.json").write_text(
        json.dumps(
            {
                "files": {
                    "design": "DESIGN.md",
                    "tokens": "tokens.css",
                    "components": "components.html",
                },
                "usage": "USAGE.md",
                "componentsManifest": "components.manifest.json",
                "importMode": "normalized",
            }
        ),
        encoding="utf-8",
    )
    (system_dir / "DESIGN.md").write_text(
        "# Sample System\n> A precise product system.\n> Category: Product & SaaS\n\n## 1. Layout\nUse rhythm.",
        encoding="utf-8",
    )
    (system_dir / "USAGE.md").write_text("Use these assets before writing UI.", encoding="utf-8")
    (system_dir / "tokens.css").write_text(_token_block(), encoding="utf-8")
    (system_dir / "components.html").write_text("<button class='btn'>Run</button>", encoding="utf-8")
    (system_dir / "components.manifest.json").write_text(
        json.dumps(
            {
                "brandId": "sample",
                "fixture": {"title": "Sample fixture", "selectorCount": 1},
                "tokens": {"declared": ["--accent"], "referenced": ["--accent"]},
                "selectors": [".btn"],
                "classes": ["btn"],
                "elements": ["button"],
                "groups": [
                    {
                        "id": "buttons",
                        "label": "Buttons",
                        "present": True,
                        "selectors": [".btn"],
                        "classes": ["btn"],
                        "elements": ["button"],
                        "tokenReferences": ["--accent"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_DESIGN_SYSTEMS_DIR", root)
    loaded = module._load_design_systems()

    system = loaded["sample"]
    assert system.body.startswith("# Sample System")
    assert system.usage_md == "Use these assets before writing UI."
    assert system.tokens_css == _token_block()
    assert system.health is not None
    assert system.health.valid is True
    assert "components.manifest schema v1 for sample" in system.components_manifest
    assert "Buttons: selectors .btn; tokens --accent" in system.components_manifest
    assert system.import_mode == "normalized"
    assert system.asset_paths["components_manifest"] == "design_system/sample/components.manifest.json"
    assert system.source_digest


def test_design_system_loader_rejects_escaped_manifest_paths(monkeypatch, tmp_path):
    module = _design_systems_module()
    root = tmp_path / "systems"
    system_dir = root / "escaped"
    system_dir.mkdir(parents=True)
    (root / "DESIGN.md").write_text("# Escaped\n> Should not load", encoding="utf-8")
    (system_dir / "manifest.json").write_text(
        json.dumps({"files": {"design": "../DESIGN.md"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_DESIGN_SYSTEMS_DIR", root)
    assert "escaped" not in module._load_design_systems()


def test_design_system_loader_extracts_fixture_manifest_when_json_missing(monkeypatch, tmp_path):
    module = _design_systems_module()
    root = tmp_path / "systems"
    system_dir = root / "fixture-only"
    system_dir.mkdir(parents=True)
    (system_dir / "DESIGN.md").write_text("# Fixture Only\n> Fixture fallback", encoding="utf-8")
    (system_dir / "tokens.css").write_text(_token_block(), encoding="utf-8")
    (system_dir / "components.html").write_text(
        """
        <style>.btn { color: var(--accent); } .card { background: var(--surface); }</style>
        <button class="btn btn-primary">Run</button>
        <article class="card">Panel</article>
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_DESIGN_SYSTEMS_DIR", root)
    system = module._load_design_systems()["fixture-only"]

    assert "components.manifest schema v1 for fixture-only" in system.components_manifest
    assert "Buttons and calls to action" in system.components_manifest
    assert "Cards and panels" in system.components_manifest
    assert "<button" not in system.components_manifest


def test_get_design_system_loads_only_requested_system(monkeypatch, tmp_path):
    module = _design_systems_module()
    root = tmp_path / "systems"
    selected_dir = root / "selected"
    other_dir = root / "other"
    selected_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    (selected_dir / "DESIGN.md").write_text("# Selected\n> Requested system", encoding="utf-8")
    (selected_dir / "tokens.css").write_text(_token_block(), encoding="utf-8")
    (other_dir / "DESIGN.md").write_text("# Other\n> Should stay cold", encoding="utf-8")
    (other_dir / "tokens.css").write_text(":root { --other: #654321; }", encoding="utf-8")

    monkeypatch.setattr(module, "_DESIGN_SYSTEMS_DIR", root)
    monkeypatch.setattr(module, "DESIGN_SYSTEMS", None)
    monkeypatch.setattr(module, "DESIGN_SYSTEM_CACHE", {})

    system = module.get_design_system("selected")

    assert system is not None
    assert system.id == "selected"
    assert system.tokens_css == _token_block()
    assert module.DESIGN_SYSTEMS is None
    assert list(module.DESIGN_SYSTEM_CACHE) == ["selected"]


def test_active_design_system_context_is_prompt_contract():
    design_system = DesignSystemDefinition(
        id="sample",
        title="Sample",
        description="Sample system",
        body="# Sample\nRules",
        usage_md="Usage rules",
        tokens_css=_token_block(),
        components_manifest="selectors: .btn",
        import_mode="normalized",
        asset_paths={
            "design": "design_system/sample/DESIGN.md",
            "usage": "design_system/sample/USAGE.md",
            "tokens": "design_system/sample/tokens.css",
            "components_manifest": "design_system/sample/components.manifest.json",
            "components": "design_system/sample/components.html",
        },
        source_digest="digest",
    )

    context = design_active_context.build_active_design_system_context(design_system)

    assert context["design_md"] == "# Sample\nRules"
    assert context["usage_md"] == "Usage rules"
    assert context["tokens_css"].startswith(":root")
    assert context["fixture_html"] is None
    assert context["pull_index"] is None
    assert "design_system/sample/components.html" not in context["loaded_paths"]


def test_prompt_runtime_injects_design_system_before_full_skill():
    long_skill = "Skill start\n" + ("x" * 26_000) + "\nTAIL_SENTINEL"
    runtime_contract = {
        "active_design_system_context": {
            "kind": "active_design_system_context",
            "design_system_id": "sample",
            "title": "Sample",
            "design_md": "# Sample Design\nDESIGN_SENTINEL",
            "usage_md": "USAGE_SENTINEL",
            "tokens_css": _token_block() + "\n/* TOKEN_SENTINEL */",
            "components_manifest": "selectors: .btn\nCOMPONENT_SENTINEL",
            "loaded_paths": ["design_system/sample/DESIGN.md"],
            "source_digest": "digest",
            "import_mode": "normalized",
        },
        "active_skill_context": {
            "kind": "selected_skill_active_context",
            "skill_id": "skill-a",
            "source_path": "SKILL.md",
            "runtime_body": long_skill,
            "truncation_mode": "full",
            "loaded_paths": ["skill/SKILL.md"],
        },
    }

    rendered = PromptRuntime().build_bundle(
        TurnSpec(
            mode=PromptMode.MAIN_TURN,
            phase="executing",
            language="en",
            skill_id="skill-a",
            runtime_contract=runtime_contract,
        )
    ).rendered_system

    assert "USAGE_SENTINEL" in rendered
    assert "DESIGN_SENTINEL" in rendered
    assert "TOKEN_SENTINEL" in rendered
    assert "COMPONENT_SENTINEL" in rendered
    assert "TAIL_SENTINEL" in rendered
    assert rendered.index("## Active design system - Sample") < rendered.index("Active selected skill body:")
    assert "Paste the unscoped :root { ... } block verbatim" in rendered
    assert "Do not redefine token values" in rendered
    assert "Do not write raw hex outside the root block" in rendered


def test_token_contract_flags_design_md_accent_conflict():
    health = evaluate_design_system_health(
        design_system_id="conflict",
        design_md="# Conflict\n\n- **Primary:** `#FECE14`",
        tokens_css=_token_block("#2563eb"),
        components_html="<style>.btn{color:var(--accent)}</style>",
        components_manifest="tokenReferences: --accent",
    )

    assert health.valid is False
    assert any("conflicts with tokens.css --accent #2563EB" in error for error in health.errors)


def test_token_contract_flags_unresolved_component_tokens():
    health = evaluate_design_system_health(
        design_system_id="bad-ref",
        design_md="# Bad Ref",
        tokens_css=_token_block(),
        components_html="<style>.btn{color:var(--missing)}</style>",
        components_manifest=None,
    )

    assert health.valid is False
    assert any("--missing" in error for error in health.errors)


def test_token_contract_rejects_non_schema_tokens():
    health = evaluate_design_system_health(
        design_system_id="bad-token",
        design_md="# Bad Token",
        tokens_css=_token_block()[:-1] + "\n  --brand-blue: #2563eb;\n}",
        components_html="<style>.btn{color:var(--accent)}</style>",
        components_manifest=None,
    )

    assert health.valid is False
    assert any("non-schema tokens: --brand-blue" in error for error in health.errors)


def test_token_contract_allows_reviewed_brand_extensions():
    health = evaluate_design_system_health(
        design_system_id="kami",
        design_md="# Kami",
        tokens_css=_token_block()[:-1] + "\n  --text-md: 15px;\n  --tag-bg-soft: #e8e6dc;\n}",
        components_html="<style>.lede{font-size:var(--text-md)}</style>",
        components_manifest=None,
    )

    assert health.valid is True
    assert health.token_report["non_schema_tokens"] == []


def test_design_system_loader_builds_pull_index_from_manifest(monkeypatch, tmp_path):
    module = _design_systems_module()
    root = tmp_path / "systems"
    system_dir = root / "pullable"
    system_dir.mkdir(parents=True)
    (system_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": "od-design-system-project/v1",
                "id": "pullable",
                "name": "Pullable",
                "category": "Imported",
                "source": {"type": "bundled"},
                "files": {
                    "design": "DESIGN.md",
                    "tokens": "tokens.css",
                    "components": "components.html",
                    "designTokens": "design-tokens.json",
                    "tailwind": "tailwind-v4.css",
                },
                "usage": "USAGE.md",
                "componentsManifest": "components.manifest.json",
                "assetsDir": "assets",
                "preview": {"dir": "preview", "pages": [{"path": "preview/index.html", "title": "Preview", "role": "audit"}]},
                "sourceFiles": {"report": "source/token-contract.report.json", "evidence": "source/evidence.md"},
            }
        ),
        encoding="utf-8",
    )
    (system_dir / "DESIGN.md").write_text("# Pullable\n> Pull index\n> Category: Imported", encoding="utf-8")
    (system_dir / "USAGE.md").write_text("Use the package.", encoding="utf-8")
    (system_dir / "tokens.css").write_text(_token_block(), encoding="utf-8")
    (system_dir / "components.html").write_text("<style>.btn{color:var(--accent)}</style><button class='btn'>Run</button>", encoding="utf-8")
    (system_dir / "components.manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "brandId": "pullable",
                "source": {"componentsHtml": "components.html", "tokensCss": "tokens.css"},
                "fixture": {"styleBlockCount": 1, "selectorCount": 1, "classCount": 1, "elementCount": 1},
                "tokens": {"declared": ["--accent"], "referenced": ["--accent"], "unusedDeclared": [], "undeclaredReferenced": []},
                "selectors": [".btn"],
                "classes": ["btn"],
                "elements": ["button"],
                "groups": [{"id": "buttons", "label": "Buttons and calls to action", "present": True, "selectors": [".btn"], "classes": ["btn"], "elements": ["button"], "tokenReferences": ["--accent"]}],
                "literals": {"colorExpressions": 0, "pixelValues": 0, "hardcodedFontFamilies": 0},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_DESIGN_SYSTEMS_DIR", root)
    system = module._load_design_systems()["pullable"]

    assert system.pull_index is not None
    assert "preview/index.html: Preview; audit" in system.pull_index
    assert "source/evidence.md: import evidence notes" in system.pull_index
    assert "design-tokens.json: derived Design Tokens JSON" in system.pull_index


def test_prompt_runtime_injects_pull_index_before_skill():
    runtime_contract = {
        "active_design_system_context": {
            "kind": "active_design_system_context",
            "design_system_id": "sample",
            "title": "Sample",
            "design_md": "# Sample Design",
            "tokens_css": _token_block(),
            "components_manifest": "components.manifest schema v1 for sample",
            "pull_index": "Additional design-system files declared by manifest.json:\n- source/evidence.md: import evidence notes",
            "source_digest": "digest",
        },
        "active_skill_context": {
            "kind": "selected_skill_active_context",
            "skill_id": "skill-a",
            "source_path": "SKILL.md",
            "runtime_body": "SKILL_SENTINEL",
        },
    }

    rendered = PromptRuntime().build_bundle(
        TurnSpec(
            mode=PromptMode.MAIN_TURN,
            phase="executing",
            language="en",
            skill_id="skill-a",
            runtime_contract=runtime_contract,
        )
    ).rendered_system

    assert "## Pull-layer files available on demand - Sample" in rendered
    assert "source/evidence.md: import evidence notes" in rendered
    assert rendered.index("## Pull-layer files available on demand - Sample") < rendered.index("Active selected skill body:")


def test_selected_skill_context_keeps_full_skill_md(tmp_path):
    body = "# Full Skill\n" + ("body\n" * 7_000) + "SKILL_TAIL_SENTINEL"
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    (skill_dir / "references").mkdir()

    skill = SimpleNamespace(id="full-skill", skill_dir=str(skill_dir), runtime_capabilities={})
    context = build_selected_skill_active_context(skill, language="en", runtime_skill_dir=skill_dir)

    assert context["runtime_body"].endswith("SKILL_TAIL_SENTINEL")
    assert context["truncation_mode"] == "full"
    assert context["omission_kinds"] == []
    assert "skill/references" in context["on_demand_paths"]
