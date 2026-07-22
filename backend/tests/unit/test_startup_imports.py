from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_app_startup_does_not_eagerly_import_agent_tool_heavy_dependencies() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    probe = """
import json
import sys

import app.main  # noqa: F401

heavy_roots = {
    "crawl4ai",
    "docx",
    "markitdown",
    "numpy",
    "openpyxl",
    "pandas",
    "patchright",
    "playwright",
    "pptx",
}
loaded = sorted(heavy_roots & {name.split(".", 1)[0] for name in sys.modules})
print(json.dumps(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == []
