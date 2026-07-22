from __future__ import annotations

import argparse
from pathlib import Path


PROTECTED_MODULES = (
    "app/core/config.py",
    "app/core/license.py",
    "app/core/license_runtime.py",
    "app/core/security.py",
)

BOOTSTRAP_PYTHON_SOURCES = {
    "app/main.py",
}

# Directories whose .py files must survive the production "prune" step.
#
# These paths are referenced at runtime by the agent's own `bash` tool (e.g.
# `python "$SKILL_DIR"/scripts/office/unpack.py ...`). If we compile them to
# .pyc and delete the .py sources, the paths printed in SKILL.md stop
# resolving inside the container and the agent wastes turns "discovering"
# that scripts are missing.
#
# Prefix match is intentional: any NEW skill folder added under
# `app/services/agent_harness/skills/` is covered automatically — no code
# change required when introducing a new skill.
SOURCE_PRESERVED_PREFIXES = (
    "app/services/agent_harness/skills/",
)


def protected_module_source_paths() -> list[Path]:
    return [Path(path) for path in PROTECTED_MODULES]


def should_preserve_source_file(relative_path: Path) -> bool:
    path_str = relative_path.as_posix()
    return path_str in BOOTSTRAP_PYTHON_SOURCES or path_str not in PROTECTED_MODULES


def _compiled_extension_patterns(relative_path: Path) -> tuple[str, ...]:
    stem = relative_path.stem
    return (f"{stem}.*.so", f"{stem}.so", f"{stem}.*.pyd", f"{stem}.pyd")


def validate_protected_artifacts(app_root: Path) -> None:
    for relative_path in protected_module_source_paths():
        module_dir = app_root / relative_path.parent.relative_to("app")
        matches: list[Path] = []
        for pattern in _compiled_extension_patterns(relative_path):
            matches.extend(module_dir.glob(pattern))
        if not matches:
            raise RuntimeError(f"Missing compiled extension for {relative_path.as_posix()}")


def prune_python_sources(app_root: Path) -> None:
    for source_path in app_root.rglob("*.py"):
        relative_path = Path("app") / source_path.relative_to(app_root)
        rel_str = relative_path.as_posix()
        if rel_str in BOOTSTRAP_PYTHON_SOURCES:
            continue
        if any(rel_str.startswith(prefix) for prefix in SOURCE_PRESERVED_PREFIXES):
            continue
        source_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate secure build artifacts.")
    parser.add_argument("command", choices=["prune", "validate"])
    parser.add_argument("app_root", type=Path)
    args = parser.parse_args()

    if args.command == "prune":
        prune_python_sources(args.app_root)
        return

    if args.command == "validate":
        validate_protected_artifacts(args.app_root)


if __name__ == "__main__":
    main()
