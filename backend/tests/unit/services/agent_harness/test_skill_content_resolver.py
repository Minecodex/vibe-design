from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.agent_harness.capabilities.skills.content_resolver import resolve_skill_content


def _skill(root: Path):
    return SimpleNamespace(id="landing", skill_dir=root)


def test_resolve_skill_content_reads_default_skill_markdown(tmp_path: Path) -> None:
    skill_dir = tmp_path / "landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: landing\ndescription: Build landing pages\n---\nDefault body line\n",
        encoding="utf-8",
    )

    resolved = resolve_skill_content(_skill(skill_dir), language="zh")

    assert resolved.body == "Default body line\n"
    assert resolved.resolved_language == "zh"
    assert resolved.source_root == skill_dir.resolve()
    assert resolved.frontmatter_status == "ok"
    assert resolved.used_runtime_root is False


def test_resolve_skill_content_prefers_english_variant_when_present(tmp_path: Path) -> None:
    skill_dir = tmp_path / "landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: landing\n---\n默认正文\n", encoding="utf-8")
    (skill_dir / "SKILL.en.md").write_text("---\nname: landing\n---\nEnglish body\n", encoding="utf-8")

    resolved = resolve_skill_content(_skill(skill_dir), language="en")

    assert resolved.body == "English body\n"
    assert resolved.resolved_language == "en"


def test_resolve_skill_content_falls_back_to_default_when_english_missing(tmp_path: Path) -> None:
    skill_dir = tmp_path / "landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: landing\n---\n默认正文\n", encoding="utf-8")

    resolved = resolve_skill_content(_skill(skill_dir), language="en")

    assert resolved.body == "默认正文\n"
    assert resolved.resolved_language == "zh"


def test_resolve_skill_content_prefers_runtime_root_and_collects_helper_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: landing\n---\nSource rule\n", encoding="utf-8")

    runtime_dir = tmp_path / "work" / ".skill_runtime" / "landing"
    (runtime_dir / "assets").mkdir(parents=True)
    (runtime_dir / "references").mkdir()
    (runtime_dir / "scripts").mkdir()
    (runtime_dir / "SKILL.md").write_text("---\nname: landing\n---\nRuntime rule\n", encoding="utf-8")
    (runtime_dir / "example.html").write_text("<html></html>", encoding="utf-8")
    (runtime_dir / "inputs.example.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "schema.ts").write_text("export {};\n", encoding="utf-8")

    resolved = resolve_skill_content(_skill(skill_dir), language="zh", runtime_skill_dir=runtime_dir)

    assert resolved.body == "Runtime rule\n"
    assert resolved.source_root == runtime_dir.resolve()
    assert resolved.used_runtime_root is True
    assert resolved.helper_files == [
        "assets",
        "references",
        "scripts",
        "example.html",
        "inputs.example.json",
        "schema.ts",
    ]


def test_resolve_skill_content_preserves_body_when_frontmatter_fails(tmp_path: Path) -> None:
    skill_dir = tmp_path / "landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: [broken\n---\nBody survives\n",
        encoding="utf-8",
    )

    resolved = resolve_skill_content(_skill(skill_dir), language="zh")

    assert resolved.frontmatter_status == "failed"
    assert resolved.body == "Body survives\n"
