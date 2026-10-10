from pathlib import Path

import pytest

from runtime.secure_build import (
    SOURCE_PRESERVED_PREFIXES,
    prune_python_sources,
    protected_module_source_paths,
    should_preserve_source_file,
    validate_protected_artifacts,
)


def test_protected_module_source_paths_returns_targeted_core_modules():
    paths = protected_module_source_paths()

    assert paths == [
        Path("app/core/config.py"),
        Path("app/core/license.py"),
        Path("app/core/license_runtime.py"),
        Path("app/core/security.py"),
    ]


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("app/main.py", True),
        ("app/api/v1/endpoints/license.py", True),
        ("app/core/config.py", False),
        ("app/core/license.py", False),
        ("app/core/license_runtime.py", False),
        ("app/core/security.py", False),
    ],
)
def test_should_preserve_source_file_respects_protected_module_list(relative_path, expected):
    assert should_preserve_source_file(Path(relative_path)) is expected


def test_validate_protected_artifacts_rejects_missing_compiled_extension(tmp_path):
    app_root = tmp_path / "app"
    core_root = app_root / "core"
    core_root.mkdir(parents=True)
    (core_root / "__init__.py").write_text("", encoding="utf-8")
    (core_root / "license.pyc").write_bytes(b"placeholder")

    with pytest.raises(RuntimeError, match="Missing compiled extension"):
        validate_protected_artifacts(app_root)


def test_prune_python_sources_keeps_bootstrap_python_and_removes_other_sources(tmp_path):
    app_root = tmp_path / "app"
    (app_root / "core").mkdir(parents=True)
    (app_root / "api").mkdir()
    (app_root / "__init__.py").write_text("", encoding="utf-8")
    (app_root / "main.py").write_text("app = object()\n", encoding="utf-8")
    (app_root / "api" / "router.py").write_text("router = object()\n", encoding="utf-8")
    (app_root / "core" / "license.py").write_text("SECRET = 'x'\n", encoding="utf-8")

    prune_python_sources(app_root)

    assert (app_root / "main.py").exists()
    assert not (app_root / "api" / "router.py").exists()
    assert not (app_root / "core" / "license.py").exists()


def test_source_preserved_prefixes_covers_agent_harness_skills():
    # Guard: the agent_harness skills tree ships runnable helper scripts that
    # the `bash` tool invokes by path (e.g. `$SKILL_DIR/scripts/render_slides.py`).
    # If this prefix is removed or narrowed, those invocations break in
    # production because the .py sources are stripped.
    assert "app/services/agent_harness/capabilities/skills/" in SOURCE_PRESERVED_PREFIXES


def test_prune_python_sources_preserves_any_future_skill_under_skills_dir(tmp_path):
    app_root = tmp_path / "app"
    # Simulate an existing skill and a brand-new skill added later.
    for skill_name in ("pptx", "future_new_skill"):
        scripts_dir = app_root / "services" / "agent_harness" / "capabilities" / "skills" / skill_name / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "helper.py").write_text("def run(): pass\n", encoding="utf-8")
        (scripts_dir / "__init__.py").write_text("", encoding="utf-8")

    # Unrelated app module should still be pruned.
    (app_root / "services" / "other").mkdir(parents=True)
    (app_root / "services" / "other" / "module.py").write_text("x = 1\n", encoding="utf-8")

    prune_python_sources(app_root)

    for skill_name in ("pptx", "future_new_skill"):
        base = app_root / "services" / "agent_harness" / "capabilities" / "skills" / skill_name / "scripts"
        assert (base / "helper.py").exists(), f"skill '{skill_name}' helper.py was pruned"
        assert (base / "__init__.py").exists()
    assert not (app_root / "services" / "other" / "module.py").exists()


def test_real_repo_skills_tree_contains_py_scripts_protected_by_prefix():
    # Sanity check against the actual repo: if someone moves/renames the
    # skills dir, this test flags the drift so SOURCE_PRESERVED_PREFIXES
    # is updated in the same commit.
    repo_root = Path(__file__).resolve().parents[4]
    skills_root = repo_root / "backend" / "app" / "services" / "agent_harness" / "capabilities" / "skills"
    assert skills_root.is_dir(), (
        f"expected skills tree at {skills_root}; "
        "if it moved, update SOURCE_PRESERVED_PREFIXES accordingly"
    )
    py_files = list(skills_root.rglob("*.py"))
    assert py_files, "skills tree has no .py helpers — is this still the right path?"


@pytest.mark.parametrize(
    "dockerfile_name",
    [
        "Dockerfile.gpu.app",
        "Dockerfile.cpu.app",
        "Dockerfile.arm64.app",
    ],
)
def test_backend_dockerfiles_support_secure_mode(dockerfile_name):
    repo_root = Path(__file__).resolve().parents[4]
    dockerfile = repo_root / "docker" / "backend" / dockerfile_name
    contents = dockerfile.read_text(encoding="utf-8")

    assert "ARG PROTECT_MODE=plain" in contents
    assert "python setup.py build_ext --inplace" in contents
    assert "python -m runtime.secure_build validate /src/app" in contents
    assert "python -m runtime.secure_build prune /src/app" in contents
