from __future__ import annotations

from pathlib import Path


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_cwd(cwd: Path, allowed_roots: tuple[Path, ...]) -> str | None:
    resolved = cwd.resolve()
    for root in allowed_roots:
        if is_relative_to(resolved, root):
            return None
    allowed = ", ".join(str(root.resolve()) for root in allowed_roots)
    return f"cwd must stay inside an allowed sandbox root: {allowed}"
