from __future__ import annotations

from pathlib import Path


def test_legacy_runtime_module_has_been_removed():
    app_root = Path(__file__).resolve().parents[4] / "app"
    assert not (app_root / "services" / "agent_harness" / "runtime" / "engine" / "runtime.py").exists()


