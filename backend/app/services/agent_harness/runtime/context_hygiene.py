from __future__ import annotations

_LOW_SIGNAL_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    ".cache",
    "node_modules",
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "dist",
    "build",
}


def is_low_signal_dir_name(value: str | None) -> bool:
    return str(value or "").strip().lower() in _LOW_SIGNAL_DIR_NAMES
