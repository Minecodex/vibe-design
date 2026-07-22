from __future__ import annotations

from pathlib import Path

import app.services.agent_harness.capabilities.design_systems as design_systems_module
from app.services.agent_harness.capabilities.design_systems import _load_design_system_from_dir


def test_all_bundled_design_systems_have_open_design_asset_shape_and_valid_health() -> None:
    root = Path(design_systems_module.__file__).resolve().parent
    checked = 0
    invalid: list[str] = []
    missing: list[str] = []

    for system_dir in sorted(root.iterdir()):
        if not system_dir.is_dir() or system_dir.name.startswith("_") or system_dir.name == "__pycache__":
            continue
        if not (system_dir / "DESIGN.md").is_file():
            continue
        checked += 1
        for filename in ("manifest.json", "USAGE.md", "DESIGN.md", "tokens.css", "components.html", "components.manifest.json"):
            if not (system_dir / filename).is_file():
                missing.append(f"{system_dir.name}/{filename}")
        if not (system_dir / "source" / "token-contract.report.json").is_file():
            missing.append(f"{system_dir.name}/source/token-contract.report.json")

        design_system = _load_design_system_from_dir(system_dir)
        if design_system is None or design_system.health is None or not design_system.health.valid:
            errors = design_system.health.errors if design_system and design_system.health else ["not loaded"]
            invalid.append(f"{system_dir.name}: {'; '.join(errors)}")

    assert checked >= 100
    assert missing == []
    assert invalid == []
