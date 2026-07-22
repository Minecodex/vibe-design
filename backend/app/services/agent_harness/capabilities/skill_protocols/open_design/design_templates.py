from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skills.markdown_parser import parse_skill_markdown

RELATION_KINDS = {"standalone", "wrapper", "sibling", "reference-only"}
STANDALONE_FIRST_WAVE_TEMPLATE_IDS = frozenset(
    {
        "dashboard",
        "docs-page",
        "gamified-app",
        "kami-landing",
        "mobile-app",
        "mobile-onboarding",
        "pricing-page",
        "saas-landing",
        "waitlist-page",
        "web",
        "web-prototype",
        "web-prototype-taste-brutalist",
        "web-prototype-taste-editorial",
        "web-prototype-taste-soft",
    }
)
HTML_PPT_FIRST_WAVE_WRAPPER_IDS = frozenset(
    {
        "html-ppt-course-module",
        "html-ppt-dir-key-nav-minimal",
        "html-ppt-graphify-dark-graph",
        "html-ppt-hermes-cyber-terminal",
        "html-ppt-knowledge-arch-blueprint",
        "html-ppt-obsidian-claude-gradient",
        "html-ppt-pitch-deck",
        "html-ppt-presenter-mode-reveal",
        "html-ppt-product-launch",
        "html-ppt-taste-brutalist",
        "html-ppt-taste-editorial",
        "html-ppt-tech-sharing",
        "html-ppt-testing-safety-alert",
        "html-ppt-weekly-report",
        "html-ppt-xhs-pastel-card",
        "html-ppt-xhs-post",
        "html-ppt-xhs-white-editorial",
    }
)
MODEL_VISIBLE_CONTRACT = (
    "\n\nLocal workspace contract:\n"
    "- Template files under `skill/` are read-only guidance and source material.\n"
    "- Always write final deliverables under `project/`.\n"
    "- `published/` is system-managed derived output, not a manual editing root.\n"
)


@dataclass(slots=True)
class TemplateRelation:
    kind: str = "standalone"
    primary_master_id: str | None = None
    references: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind if self.kind in RELATION_KINDS else "standalone",
            "primary_master_id": self.primary_master_id,
            "references": list(self.references),
        }


@dataclass(slots=True)
class TemplatePreflight:
    runtime_entry_strategy: str = "free-generate"
    context_sources: list[str] = field(default_factory=list)
    available_side_files: list[str] = field(default_factory=list)
    seed_template_files: list[str] = field(default_factory=list)
    shared_asset_files: list[str] = field(default_factory=list)
    reusable_scripts: list[str] = field(default_factory=list)
    execution_constraints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runtime_entry_strategy": self.runtime_entry_strategy,
            "context_sources": list(self.context_sources),
            "available_side_files": list(self.available_side_files),
            "seed_template_files": list(self.seed_template_files),
            "shared_asset_files": list(self.shared_asset_files),
            "reusable_scripts": list(self.reusable_scripts),
            "execution_constraints": list(self.execution_constraints),
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class ImportedDesignTemplate:
    template_id: str
    display_name: str
    source_dir: Path
    skill_path: Path
    normalized_body: str
    relation: TemplateRelation = field(default_factory=TemplateRelation)
    preflight: TemplatePreflight = field(default_factory=TemplatePreflight)
    support_state: str = "supported"
    deferred_reason: str | None = None
    reentry_criteria: str | None = None
    rollout_wave: str | None = None
    runtime_entry_strategy: str = "free-generate"

    def to_runtime_capabilities(self) -> dict[str, Any]:
        return {
            "imported_design_template": True,
            "template_id": self.template_id,
            "template_source_dir": str(self.source_dir),
            "template_relation": self.relation.to_payload(),
            "template_preflight": self.preflight.to_payload(),
            "template_support_state": self.support_state,
            "template_deferred_reason": self.deferred_reason,
            "template_reentry_criteria": self.reentry_criteria,
            "template_rollout_wave": self.rollout_wave,
            "runtime_entry_strategy": self.runtime_entry_strategy,
        }


def build_design_template_catalog(root: Path) -> dict[str, ImportedDesignTemplate]:
    source_root = Path(root)
    templates: dict[str, ImportedDesignTemplate] = {}
    if not source_root.is_dir():
        return templates
    for child in sorted(source_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_path = child / "SKILL.md"
        if not skill_path.is_file():
            continue
        templates[child.name] = build_imported_template_metadata(child.name, child)
    return templates


def build_imported_template_metadata(
    template_id: str,
    template_dir: Path,
    *,
    body: str | None = None,
) -> ImportedDesignTemplate:
    source_dir = Path(template_dir).resolve()
    skill_path = source_dir / "SKILL.md"
    raw_body = str(body if body is not None else _read_skill_body(skill_path))
    normalized_body = normalize_template_body_for_workspace(raw_body)
    relation = resolve_template_relation(template_id=template_id, body=raw_body)
    preflight = generate_template_preflight(template_id=template_id, template_dir=source_dir, body=raw_body, relation=relation)
    support_state = "supported"
    rollout_wave = _rollout_wave(template_id, relation)
    return ImportedDesignTemplate(
        template_id=template_id,
        display_name=template_id.replace("-", " "),
        source_dir=source_dir,
        skill_path=skill_path,
        normalized_body=normalized_body,
        relation=relation,
        preflight=preflight,
        support_state=support_state,
        deferred_reason=None,
        reentry_criteria=None,
        rollout_wave=rollout_wave,
        runtime_entry_strategy=preflight.runtime_entry_strategy,
    )


def resolve_template_relation(*, template_id: str, body: str | None) -> TemplateRelation:
    text = str(body or "")
    references = _linked_template_ids(text)
    if template_id.startswith("html-ppt-"):
        return TemplateRelation(kind="wrapper", primary_master_id="html-ppt", references=_dedupe(["html-ppt", *references]))
    master = _explicit_master_id(text)
    if master:
        return TemplateRelation(kind="wrapper", primary_master_id=master, references=_dedupe([master, *references]))
    lowered = text.lower()
    if any(token in lowered for token in ("sibling", "companion", "variant of")) and references:
        return TemplateRelation(kind="sibling", references=references)
    if references:
        return TemplateRelation(kind="reference-only", references=references)
    return TemplateRelation()


def generate_template_preflight(
    *,
    template_id: str,
    template_dir: Path,
    body: str | None,
    relation: TemplateRelation,
) -> TemplatePreflight:
    root = Path(template_dir)
    context_sources: list[str] = []
    available_side_files: list[str] = []
    seed_files: list[str] = []
    shared_assets: list[str] = []
    scripts: list[str] = []
    warnings: list[str] = []

    if relation.kind == "wrapper" and relation.primary_master_id:
        context_sources.append(f"skill/_linked/{relation.primary_master_id}/SKILL.md")
    for design_system_id in _design_system_references(body):
        context_sources.append(f"design_system:{design_system_id}")

    for rel_path in _candidate_files(root):
        model_path = f"skill/{rel_path}"
        if rel_path in {"template.json", "example.html", "assets/template.html"}:
            seed_files.append(model_path)
        elif rel_path.startswith("references/"):
            available_side_files.append(model_path)
        elif rel_path.startswith("assets/"):
            shared_assets.append(model_path)
        elif rel_path.startswith("scripts/"):
            scripts.append(model_path)
        elif rel_path.startswith("templates/full-decks/") and rel_path.endswith("index.html"):
            available_side_files.append(model_path)
            seed_files.append(model_path)

    for referenced in _body_file_references(body):
        model_path = _model_visible_path(referenced)
        if model_path and model_path not in context_sources and model_path not in available_side_files:
            if _exists_model_visible(root, model_path):
                available_side_files.append(model_path)
            else:
                warnings.append(f"Referenced file is not present in staged template: {model_path}")

    runtime_entry_strategy = _runtime_entry_strategy(root, relation)
    constraints = [
        "Treat listed skill files as optional read-only side files unless the loaded skill body requires a specific one.",
        "Use `skill/` files as read-only source material.",
        "Keep final deliverables under `project/`.",
    ]
    if relation.kind == "wrapper" and relation.primary_master_id:
        constraints.append(f"Apply wrapper guidance with master template `{relation.primary_master_id}`.")
    return TemplatePreflight(
        runtime_entry_strategy=runtime_entry_strategy,
        context_sources=_dedupe(context_sources),
        available_side_files=_dedupe(available_side_files)[:24],
        seed_template_files=_dedupe(seed_files)[:24],
        shared_asset_files=_dedupe(shared_assets)[:24],
        reusable_scripts=_dedupe(scripts)[:24],
        execution_constraints=constraints,
        warnings=_dedupe(warnings)[:12],
    )


def normalize_template_body_for_workspace(body: str | None) -> str:
    text = str(body or "").strip()

    def replace_od_skill(match: re.Match[str]) -> str:
        template_id = match.group(1)
        rest = match.group(2) or "SKILL.md"
        return f"skill/_linked/{template_id}/{rest.strip('/')}"

    def replace_skill_root(match: re.Match[str]) -> str:
        template_id = match.group(1)
        rest = match.group(2) or "SKILL.md"
        return f"skill/_linked/{template_id}/{rest.strip('/')}"

    text = re.sub(r"\.od-skills[/\\]([A-Za-z0-9_-]+)(?:[/\\]([^\s),.]+))?", replace_od_skill, text)
    text = re.sub(r"(?<![\w/.-])skills[/\\]([A-Za-z0-9_-]+)(?:[/\\]([^\s),.]+))?", replace_skill_root, text)
    text = re.sub(r"(?:\.\./)+design-systems[/\\]([A-Za-z0-9_-]+)[/\\]DESIGN\.md", r"design_system:\1", text)
    if "Template files under `skill/` are read-only" not in text:
        text = text.rstrip() + MODEL_VISIBLE_CONTRACT
    return text


def _read_skill_body(skill_path: Path) -> str:
    try:
        parsed = parse_skill_markdown(skill_path.read_text(encoding="utf-8"))
        return parsed.body
    except Exception:
        return ""


def _candidate_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".git/", "__pycache__/")):
            continue
        if path.suffix.lower() in {".html", ".json", ".md", ".css", ".js", ".py", ".sh", ".ts"}:
            files.append(rel)
    return files


def _runtime_entry_strategy(root: Path, relation: TemplateRelation) -> str:
    if relation.kind == "wrapper":
        return "edit-example"
    if (root / "assets" / "template.html").is_file():
        return "copy-seed"
    if (root / "template.json").is_file() or (root / "example.html").is_file() or (root / "templates").is_dir():
        return "edit-example"
    return "free-generate"


def _rollout_wave(template_id: str, relation: TemplateRelation) -> str:
    if relation.kind == "wrapper" and template_id in HTML_PPT_FIRST_WAVE_WRAPPER_IDS:
        return "html_ppt_first_wave"
    if relation.kind == "standalone" and template_id in STANDALONE_FIRST_WAVE_TEMPLATE_IDS:
        return "standalone_first_wave"
    return "supported_unassigned"


def _linked_template_ids(text: str) -> list[str]:
    refs = re.findall(r"(?:\.\./|\.od-skills/|skills/)([A-Za-z0-9_-]+)/SKILL\.md", str(text or ""))
    return _dedupe(ref for ref in refs if ref)


def _explicit_master_id(text: str) -> str | None:
    lowered = str(text or "").lower()
    if "master skill" not in lowered and "master template" not in lowered:
        return None
    refs = _linked_template_ids(text)
    return refs[0] if refs else None


def _body_file_references(body: str | None) -> list[str]:
    text = str(body or "")
    refs = re.findall(r"(?<![\w/])((?:assets|references|scripts|templates)/[A-Za-z0-9_./-]+)", text)
    return [ref.rstrip(").,`'\"") for ref in refs]


def _design_system_references(body: str | None) -> list[str]:
    text = str(body or "")
    refs = re.findall(r"(?:\.\./)+design-systems[/\\]([A-Za-z0-9_-]+)[/\\]DESIGN\.md", text)
    return _dedupe(refs)


def _model_visible_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return ""
    if normalized.startswith("skill/"):
        return normalized
    if normalized.startswith(("assets/", "references/", "scripts/", "templates/", "template.json", "example.html")):
        return f"skill/{normalized}"
    return normalized


def _exists_model_visible(root: Path, model_path: str) -> bool:
    rel = str(model_path or "").removeprefix("skill/").strip("/")
    if rel.startswith("_linked/") or rel.startswith("design_system:"):
        return True
    return bool(rel and (root / rel).exists())


def _dedupe(values: list[str] | Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
