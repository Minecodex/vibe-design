from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_harness.capabilities.skills.active_manifest import build_active_skill_manifest


def test_active_skill_manifest_builds_selected_skill_and_hidden_helper(tmp_path):
    source_dir = tmp_path / "skills" / "landing"
    (source_dir / "references").mkdir(parents=True)
    (source_dir / "scripts").mkdir()
    (source_dir / "SKILL.md").write_text(
        "---\nname: landing\n---\nBuild a premium landing page.\n",
        encoding="utf-8",
    )
    (source_dir / "references" / "authoring-guide.md").write_text("guide", encoding="utf-8")
    (source_dir / "scripts" / "build.py").write_text("print('ok')", encoding="utf-8")

    manifest = build_active_skill_manifest(
        language="en",
        skill=SimpleNamespace(
            id="landing",
            name="Landing",
            name_en="Landing",
            description="Use this skill for landing page work.",
            skill_dir=source_dir,
        ),
        skill_id="landing",
        prompt_body="Fallback prompt",
        runtime_skill_dir=None,
        runtime_contract={"internal_hidden_skills": [{"id": "critique"}]},
    )

    assert manifest is not None
    assert manifest["selected_skill_id"] == "landing"
    assert "discovery_contract" not in manifest
    assert "recommended_reads" not in manifest["skills"][0]
    assert "skill/SKILL.md" not in manifest["skills"][0]["available_side_files"]
    assert "skill/references/authoring-guide.md" in manifest["skills"][0]["available_side_files"]
    assert "skill/scripts/build.py" in manifest["skills"][0]["available_side_files"]
    assert any(item["activation_role"] == "internal_helper" for item in manifest["skills"])
    assert ".skill_runtime" not in str(manifest)
