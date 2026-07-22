from __future__ import annotations

import json
from typing import Any

from .models import PromptBlock, PromptMode, TurnSpec

_JSON_COMPACT_STRING_MAX_CHARS = 800
_JSON_COMPACT_LIST_MAX_ITEMS = 20
_PLAN_CONTEXT_MAX_CHARS = 10_000
_WORKSPACE_RUNTIME_MAX_CHARS = 4_000
_SUMMARY_MAX_CHARS = 4_000

_DEFAULT_DESIGN_SYSTEM_USAGE = (
    "DESIGN.md is prose and intent. tokens.css is the binding contract. "
    "Paste the unscoped :root { ... } block from tokens.css verbatim into the first <style>. "
    "Do not invent tokens, do not redefine token values, and do not write raw hex outside the root block. "
    "Match component shapes from the reference component manifest or fixture."
)


def _cap_text(value: Any, max_chars: int) -> tuple[str, str | None]:
    text = str(value or "")
    if len(text) <= max_chars:
        return text, None
    omitted = len(text) - max_chars
    return text[:max_chars].rstrip() + f"\n[truncated {omitted} chars]", "truncated"


def _compact_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return _cap_text(value, _JSON_COMPACT_STRING_MAX_CHARS)[0]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _cap_text(str(value), _JSON_COMPACT_STRING_MAX_CHARS)[0]


def _compact_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _compact_scalar(value)
    if isinstance(value, dict):
        items = list(value.items())
        omitted = max(0, len(items) - _JSON_COMPACT_LIST_MAX_ITEMS)
        out: dict[str, Any] = {"omitted_count": omitted} if omitted > 0 else {}
        for key, child in items[:_JSON_COMPACT_LIST_MAX_ITEMS]:
            out[str(key)] = _compact_json_value(child, depth=depth + 1)
        return out
    if isinstance(value, list):
        items = [_compact_json_value(item, depth=depth + 1) for item in value[:_JSON_COMPACT_LIST_MAX_ITEMS]]
        omitted = len(value) - len(items)
        if omitted > 0:
            return {"omitted_count": omitted, "items": items}
        return items
    return _compact_scalar(value)


def _compact_json_text(value: Any, *, max_chars: int) -> tuple[str, str | None]:
    compacted = _compact_json_value(value)
    text = json.dumps(compacted, ensure_ascii=False, separators=(",", ":"))
    return _cap_text(text, max_chars)


def build_phase_policy(spec: TurnSpec, decision) -> PromptBlock | None:
    if spec.mode in {
        PromptMode.PLANNING_SCHEMA_GENERATION,
        PromptMode.SKILL_SELECTION,
        PromptMode.DESIGN_SYSTEM_SELECTION,
        PromptMode.SIDE_CLASSIFIER,
    }:
        return None
    payload = {
        "phase": decision.phase,
        "blocked_capabilities": decision.blocked_capabilities,
        "required_outputs": decision.required_outputs,
        "require_plan_sync": decision.require_plan_sync,
        "plan_sync_mode": decision.plan_sync_mode,
        "require_publish_before_final": decision.require_publish_before_final,
        "recovery_action": decision.recovery_action,
        "notes": decision.notes,
    }
    if decision.allowed_tools:
        payload["allowed_tools"] = decision.allowed_tools
    text, truncation = _compact_json_text(payload, max_chars=3_200)
    return PromptBlock(
        id="phase.policy",
        layer="delta",
        content="Phase policy:\n" + text,
        rule_family="phase_behavior",
        metadata={"truncation_reason": truncation},
    )


def build_workspace_runtime_state(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    session = spec.workspace_runtime_session or {}
    runtime_contract = spec.runtime_contract or {}
    if not session and not runtime_contract:
        return None
    payload = {
        "selected_skill": session.get("selected_skill"),
        "internal_hidden_skills": session.get("internal_hidden_skills") or runtime_contract.get("internal_hidden_skills"),
        "artifact_work_root": session.get("artifact_work_root"),
        "agent_cwd": session.get("agent_cwd"),
        "active_entry": session.get("active_entry"),
        "selected_direction": session.get("selected_direction") or runtime_contract.get("direction_id"),
        "execution_strategy": runtime_contract.get("execution_strategy"),
        "discovered_inputs": session.get("discovered_inputs"),
        "plan_context": runtime_contract.get("plan_context"),
        "active_design_system": _active_design_system_id(runtime_contract),
    }
    text, truncation = _compact_json_text(payload, max_chars=_WORKSPACE_RUNTIME_MAX_CHARS)
    return PromptBlock(
        id="state.workspace_runtime",
        # delta layer keeps this most-volatile block at the tail of the rendered
        # system so the stable prefix stays cacheable across runs.
        layer="delta",
        content="Workspace runtime session:\n" + text,
        metadata={"truncation_reason": truncation},
    )


def build_active_craft_references(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    skill = spec.skill
    craft = getattr(skill, "craft", None) if skill is not None else None
    requires = getattr(craft, "requires", None)
    if not isinstance(requires, list) or not requires:
        return None
    from app.services.agent_harness.capabilities.craft_references import (
        load_craft_reference_block,
    )

    block, resolved = load_craft_reference_block(requires)
    if not block:
        return None
    return PromptBlock(
        id="state.active_craft_refs",
        layer="state",
        content=block,
        metadata={"craft_requires": resolved},
    )


def build_active_skill_body(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    runtime_contract = spec.runtime_contract or {}
    active_context = runtime_contract.get("active_skill_context") if isinstance(runtime_contract, dict) else None
    if not isinstance(active_context, dict):
        return None
    if str(active_context.get("skill_id") or "").strip() != str(spec.skill_id or "").strip():
        return None
    runtime_body = str(active_context.get("runtime_body") or "").strip()
    if not runtime_body:
        return None

    loaded_paths = _string_list(active_context.get("loaded_paths"))
    on_demand_paths = _string_list(active_context.get("on_demand_paths"))
    link_targets = _string_list(active_context.get("link_targets"))
    source_path = str(active_context.get("source_path") or "SKILL.md").strip() or "SKILL.md"
    truncation_mode = str(active_context.get("truncation_mode") or "unknown").strip()
    lines = [
        "Active selected skill body:",
        f"Status: selected skill `{source_path}` is already loaded into active context.",
        f"Body mode: {truncation_mode}.",
    ]
    if loaded_paths:
        lines.append("Loaded selected skill paths:")
        lines.extend(f"- {path}" for path in loaded_paths[:8])
    lines.extend(
        [
            "Selected skill side files are not preloaded by default.",
            'If omitted referenced details are needed, read linked files with `read_file(path="skill/<path>")`.',
            'For side folders, inspect a targeted folder first with `list_files(path="skill/<path>", recursive=false)`.',
        ]
    )
    if on_demand_paths or link_targets:
        lines.append("On-demand selected skill side files:")
        for path in _dedupe([*on_demand_paths, *link_targets])[:12]:
            lines.append(f"- {path} -> {_skill_path_instruction(path)}")
    lines.extend(["Selected skill runtime body:", runtime_body])
    return PromptBlock(
        id="state.active_skill_body",
        layer="state",
        content="\n".join(lines),
        metadata={
            "body_mode": truncation_mode,
            "builder_version": active_context.get("builder_version"),
        },
    )


def build_active_design_system_usage(spec: TurnSpec) -> PromptBlock | None:
    ctx = _active_design_system_context(spec)
    if ctx is None:
        return None
    title = _active_design_system_title(ctx)
    usage = str(ctx.get("usage_md") or "").strip() or _DEFAULT_DESIGN_SYSTEM_USAGE
    return PromptBlock(
        id="state.active_design_system_usage",
        layer="state",
        content=f"## How to use this design system - {title}\n\n{usage}",
        metadata=_active_design_system_metadata(ctx),
    )


def build_active_design_system_body(spec: TurnSpec) -> PromptBlock | None:
    ctx = _active_design_system_context(spec)
    if ctx is None:
        return None
    body = str(ctx.get("design_md") or "").strip()
    if not body:
        return None
    title = _active_design_system_title(ctx)
    content = (
        f"## Active design system - {title}\n\n"
        "DESIGN.md is prose and intent for visual tone, layout, density, and component behavior. "
        "It is not the binding source for token values. If DESIGN.md conflicts with tokens.css, "
        "the tokens.css contract wins.\n\n"
        f"{body}\n\n"
        "USAGE.md, DESIGN.md, tokens.css, and the component manifest are already "
        "injected above; do not call read_file on DESIGN.md again and do not rely "
        "on legacy design-system summaries."
    )
    return PromptBlock(
        id="state.active_design_system_body",
        layer="state",
        content=content,
        metadata=_active_design_system_metadata(ctx),
    )


def build_active_design_system_tokens(spec: TurnSpec) -> PromptBlock | None:
    ctx = _active_design_system_context(spec)
    if ctx is None:
        return None
    tokens = str(ctx.get("tokens_css") or "").strip()
    if not tokens:
        return None
    title = _active_design_system_title(ctx)
    content = (
        f"## Active design system tokens - {title}\n\n"
        "The block below is tokens.css and it is the binding runtime contract. "
        "Paste the unscoped :root { ... } block verbatim into the first <style> of the artifact. "
        "Do not invent new tokens. Do not redefine token values. Do not change --accent, --bg, "
        "--surface, --fg, --border, fonts, radii, focus, elevation, spacing, or container tokens. "
        "Do not write raw hex outside the root block; use var(--*) references for backgrounds, "
        "text, borders, CTAs, links, and focus states. If selected skill instructions conflict "
        "with token values, the token contract wins.\n\n"
        f"```css\n{tokens}\n```"
    )
    return PromptBlock(
        id="state.active_design_system_tokens",
        layer="state",
        content=content,
        metadata=_active_design_system_metadata(ctx),
    )


def build_active_design_system_components(spec: TurnSpec) -> PromptBlock | None:
    ctx = _active_design_system_context(spec)
    if ctx is None:
        return None
    manifest = str(ctx.get("components_manifest") or "").strip()
    if not manifest:
        return None
    title = _active_design_system_title(ctx)
    content = (
        f"## Reference component manifest - {title}\n\n"
        "Use this as the component inventory. Match selectors, groups, class structure, "
        "token references, component shapes, focus behavior, and spacing cadence from this "
        "manifest or fixture. Prefer these component patterns over inventing new shapes.\n\n"
        f"```text\n{manifest}\n```"
    )
    return PromptBlock(
        id="state.active_design_system_components",
        layer="state",
        content=content,
        metadata=_active_design_system_metadata(ctx),
    )


def build_active_design_system_pull_index(spec: TurnSpec) -> PromptBlock | None:
    ctx = _active_design_system_context(spec)
    if ctx is None:
        return None
    pull_index = str(ctx.get("pull_index") or "").strip()
    if not pull_index:
        return None
    title = _active_design_system_title(ctx)
    content = (
        f"## Pull-layer files available on demand - {title}\n\n"
        "This design-system package declares richer files for inspection, source evidence, "
        "preview, or derived token outputs. Keep the push prompt light: use this index only "
        "to decide whether a listed file should be read later by an available runtime tool. "
        "Do not assume unlisted paths are part of the design-system contract.\n\n"
        f"```text\n{pull_index}\n```"
    )
    return PromptBlock(
        id="state.active_design_system_pull_index",
        layer="state",
        content=content,
        metadata=_active_design_system_metadata(ctx),
    )


def build_plan_state(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN:
        return None
    plan_state = (spec.conversation or {}).get("plan_state")
    if not isinstance(plan_state, dict) and not isinstance(spec.current_outline, dict):
        return None
    payload = {
        "plan_state": plan_state if isinstance(plan_state, dict) else {},
        "current_outline": spec.current_outline if isinstance(spec.current_outline, dict) else {},
    }
    text, truncation = _compact_json_text(payload, max_chars=_PLAN_CONTEXT_MAX_CHARS)
    return PromptBlock(
        id="state.plan",
        layer="state",
        content="Plan state payload:\n" + text,
        metadata={"truncation_reason": truncation},
    )


def build_manifest_summary(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN or not spec.manifest_summary:
        return None
    text, truncation = _compact_json_text(spec.manifest_summary, max_chars=_SUMMARY_MAX_CHARS)
    return PromptBlock(
        id="state.manifest_summary",
        layer="state",
        content="Workspace manifest summary:\n" + text,
        metadata={"truncation_reason": truncation},
    )


def build_past_context_recall(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN or not str(spec.past_context_recall or "").strip():
        return None
    return PromptBlock(
        id="state.past_context_recall",
        layer="state",
        content=str(spec.past_context_recall).strip(),
    )


def _active_design_system_context(spec: TurnSpec) -> dict[str, Any] | None:
    runtime_contract = spec.runtime_contract or {}
    if not isinstance(runtime_contract, dict):
        return None
    ctx = runtime_contract.get("active_design_system_context")
    if not isinstance(ctx, dict):
        return None
    if str(ctx.get("kind") or "") != "active_design_system_context":
        return None
    return ctx


def _active_design_system_id(runtime_contract: dict[str, Any]) -> str | None:
    ctx = runtime_contract.get("active_design_system_context")
    if not isinstance(ctx, dict):
        return None
    return str(ctx.get("design_system_id") or "").strip() or None


def _active_design_system_title(ctx: dict[str, Any]) -> str:
    return str(ctx.get("title") or ctx.get("design_system_id") or "design system").strip()


def _active_design_system_metadata(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "design_system_id": ctx.get("design_system_id"),
        "source_digest": ctx.get("source_digest"),
        "loaded_paths": _string_list(ctx.get("loaded_paths")),
        "import_mode": ctx.get("import_mode"),
    }


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in list(value or []) if str(item).strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _skill_path_instruction(path: str) -> str:
    display_path = str(path or "").strip().removeprefix("skill/")
    if display_path in {"references", "scripts", "assets"}:
        return f'list_files(path="skill/{display_path}", recursive=false)'
    return f'read_file(path="skill/{display_path}")'
