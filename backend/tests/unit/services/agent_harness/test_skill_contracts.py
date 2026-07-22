from __future__ import annotations

from pathlib import Path

from app.services.agent_harness.capabilities import skills as skills_module
from app.services.agent_harness.capabilities.skills import get_skill, list_skills
from app.services.agent_harness.capabilities.skills.lint import lint_all_skills


SKILLS_DIR = Path(skills_module.__file__).parent
SKILL_IDS_WITH_MARKDOWN = {"docx", "pptx", "xlsx", "web"}
FORBIDDEN_RUNTIME_DETAILS = (
    "Workspace Paths",
    "Runtime Preflight",
    "runtime capability profile",
    "Runtime capability profile",
    "workspace_file(action=",
    "validate_output",
    "$SCRATCH_DIR",
    "$GENERATED_DIR",
    "$CONVERSATION_DIR",
    "HARNESS_AUTHOR_NAME",
    "default author",
    "Default author",
    "sandbox cwd",
    "before publishing",
    "pip install",
    "npm install -g",
)
REMOVED_ECOMMERCE_TERMS = [
    "_".join(parts)
    for parts in [
        ["analyze", "ecommerce", "realshots"],
        ["ecommerce", "analysis", "review"],
        ["ecommerce", "generation", "review"],
        ["confirmed", "ecommerce", "generation"],
    ]
]


def test_skill_tools_are_deduplicated():
    for skill in list_skills():
        assert len(skill.tools) == len(set(skill.tools)), skill.id


def test_menswear_ecommerce_skill_uses_generation_review_without_analysis_tools():
    skill = get_skill("menswear-ecommerce-hero")

    assert skill is not None
    assert skill.tools == ["analyze_image", "generate_image", "prepare_ecommerce_generation"]
    assert skill.disabled_tools == ["ask_user"]
    for removed_term in REMOVED_ECOMMERCE_TERMS:
        assert removed_term not in skill.system_prompt
    assert "generate_image" in skill.system_prompt
    assert "prepare_ecommerce_generation" in skill.system_prompt
    assert "无参" in skill.system_prompt
    assert "不要用交互卡片承载该确认" in skill.system_prompt


def test_skills_pass_workspace_contract_lint():
    assert lint_all_skills(SKILLS_DIR) == {}


def test_skill_prompts_do_not_duplicate_runtime_contracts():
    for skill in list_skills():
        if skill.id not in SKILL_IDS_WITH_MARKDOWN:
            continue
        text = skill.system_prompt
        for phrase in FORBIDDEN_RUNTIME_DETAILS:
            assert phrase not in text, f"{skill.id} duplicates runtime detail {phrase!r}"


def test_skill_prompts_reference_workspace_contract_briefly():
    for skill in list_skills():
        if skill.id not in SKILL_IDS_WITH_MARKDOWN:
            continue
        assert text_count(skill.system_prompt.lower(), "workspace contract") == 1, skill.id


def test_harness_file_skills_reference_active_bindings_and_system_dirs():
    for skill_id in ("docx", "pptx", "xlsx", "web"):
        skill = next(skill for skill in list_skills() if skill.id == skill_id)
        assert "artifact_session" not in skill.system_prompt
        assert ".meta/" not in skill.system_prompt


def test_office_default_author_is_harness_not_claude():
    office_files = [
        path
        for path in SKILLS_DIR.glob("*/scripts/**/*.py")
        if "__pycache__" not in path.parts
    ]
    assert office_files
    for path in office_files:
        text = path.read_text(encoding="utf-8")
        assert '"Claude"' not in text
        assert "default: Claude" not in text


def text_count(text: str, needle: str) -> int:
    return text.count(needle)
