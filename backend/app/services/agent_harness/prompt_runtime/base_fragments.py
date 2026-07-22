from __future__ import annotations

from app.services.agent_harness.authoring.prompt.harness_prompt import build_system_prompt

from .models import PromptBlock, PromptMode, TurnSpec


def build_base_instructions(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode == PromptMode.MAIN_TURN:
        runtime_profile = str((spec.conversation or {}).get("runtime_profile") or "home").strip().lower() or "home"
        content = spec.base_instructions_override or build_system_prompt(
            spec.language, runtime_profile=runtime_profile, artifact_mode=spec.artifact_mode or "web"
        )
        return PromptBlock(
            id="base.instructions",
            layer="system",
            content=content,
            rule_family="identity",
        )
    if spec.mode == PromptMode.PLANNING_SCHEMA_GENERATION:
        locale_line = "Respond in Chinese labels when locale starts with zh; otherwise use English."
        if str(spec.language).lower().startswith("zh"):
            locale_line = "输出中文字段标题、描述和占位文案。"
        selected = bool((spec.side_payload or {}).get("design_system_selected"))
        repeat_rule = (
            "Do not ask again about visual direction or design system because one is already selected."
            if selected
            else "If no design system is selected, you may ask about brand/reference context, but do not ask the user to choose a final design system here."
        )
        return PromptBlock(
            id="base.instructions",
            layer="system",
            content=(
                "You are a senior designer generating a fast, tasteful Quick brief form for the user's design request.\n"
                "This form is the first deliverable: the user should be able to finish it in ~30 seconds with mostly taps, not essays.\n"
                "Never use the platform or product name as the form title, brand/project name, or any default value. "
                "Infer the brand/project name from the user's request; if it is unknown, leave that field empty or use a short neutral placeholder.\n"
                "Call submit_quick_brief_schema exactly once when that tool is available; otherwise return JSON only. No markdown. No explanations.\n"
                f"{locale_line}\n"
                f"{repeat_rule}\n"
                "Use the provided runtime time context when the user mentions relative dates or time windows.\n"
                "Ask only for missing decisions that materially affect the design outcome.\n"
                "Keep it to at most 7 questions; prefer radio/select/checkbox for fast taps over open text.\n"
                "Tailor questions to the brief: drop anything the user already answered, add fields the brief uniquely needs (slide count, list of screens, page sections).\n"
                "Do not ask again about already-selected skill, artifact family, or known constraints.\n"
                "Schema contract:\n"
                "- title: short string\n"
                "- description: short string\n"
                "- submit_label: short string\n"
                "- fields: array of 2 to 12 field objects\n"
                "- allowed field types: text, textarea, select, radio, cards, checkbox\n"
                "- Do not use other field types such as dropdown, multiselect, number, date, switch, or boolean.\n"
                "- every field needs id, label, type, required\n"
                "- every required field must include a realistic default_value so the user can continue immediately\n"
                "- infer practical defaults from the user's request, skill, artifact family, locale, and known constraints\n"
                "- options are only allowed for select, radio, cards, checkbox\n"
                "- options must be objects like {\"label\":\"Option label\",\"value\":\"option_value\"}; do not use string arrays\n"
                "- select, radio, cards default_value must match one option value exactly\n"
                "- checkbox default_value must be an array of option values; required checkbox fields need at least one default value\n"
                "- field ids must be stable snake_case\n"
                "- keep labels concise and practical\n"
                "- prefer text/textarea for open responses and radio/select for constrained choices\n"
                "Minimal valid example:\n"
                "{\n"
                '  "title": "Quick brief",\n'
                '  "description": "Confirm the core constraints before planning.",\n'
                '  "submit_label": "Submit",\n'
                '  "fields": [\n'
                '    {"id": "output", "label": "Output", "type": "text", "required": true, "default_value": "Landing page"},\n'
                '    {"id": "tone", "label": "Tone", "type": "select", "required": true, "default_value": "professional", "options": [{"label":"Option label","value":"option_value"}, {"label": "Professional", "value": "professional"}]}\n'
                "  ]\n"
                "}\n"
            ),
        )
    if spec.mode == PromptMode.SKILL_SELECTION:
        return PromptBlock(
            id="base.instructions",
            layer="system",
            content=(
                "You are a fast selection resolver\n"
                "Decide whether the current request materially benefits from an explicit main skill.\n"
                "Use the provided runtime time context when the request contains relative dates or time windows.\n"
                "Rules:\n"
                "1. Only choose from the provided candidates.\n"
                "2. Returning null is correct when the task is simple, local, generic, or does not benefit from a dedicated template.\n"
                "3. Prefer stability: if the current auto-selected value still fits, avoid replacing it.\n"
                "4. Use short, concrete reasoning.\n"
                "5. Always call the resolve_selection function exactly once.\n"
            ),
        )
    if spec.mode == PromptMode.DESIGN_SYSTEM_SELECTION:
        return PromptBlock(
            id="base.instructions",
            layer="system",
            content=(
                "You are a fast visual-basis recommender\n"
                "Choose exactly six design systems from the provided candidates.\n"
                "Rules:\n"
                "1. Only choose from the provided candidates.\n"
                "2. Favor the best primary match first, then five strong alternatives.\n"
                "3. Prefer stability: if the current design system still fits, keep it near the top.\n"
                "4. Use short, concrete reasoning tied to the brief.\n"
                "5. Always call the recommend_design_systems function exactly once.\n"
            ),
        )
    if spec.mode == PromptMode.SIDE_CLASSIFIER:
        return PromptBlock(
            id="base.instructions",
            layer="system",
            content=(
                "You are a lightweight side classifier.\n"
                "Return JSON only with keys: label, confidence.\n"
                "Choose label only from the provided label_space.\n"
                "confidence must be a number from 0 to 1.\n"
            ),
        )
    return None
