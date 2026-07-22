from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from app.core.config import API_V1_STR


def read_local_image_dimensions(
    media_ref: str | None,
    *,
    workspace_root: Path | None = None,
    uploads_root: Path | None = None,
) -> tuple[int, int] | None:
    media_path = resolve_local_media_path(
        media_ref,
        workspace_root=workspace_root,
        uploads_root=uploads_root,
    )
    if media_path is None:
        return None

    try:
        from PIL import Image

        with Image.open(media_path) as image:
            width = int(image.width)
            height = int(image.height)
    except Exception:
        return None

    if width <= 0 or height <= 0:
        return None
    return width, height


def resolve_local_media_path(
    media_ref: str | None,
    *,
    workspace_root: Path | None = None,
    uploads_root: Path | None = None,
) -> Path | None:
    text = str(media_ref or "").strip()
    if not text:
        return None

    upload_relative = _upload_relative_path(text)
    if upload_relative is not None:
        for root in _uploads_root_candidates(uploads_root):
            resolved = _resolve_under_root(upload_relative, root)
            if resolved is not None:
                return resolved
        return None

    raw_path = Path(text)
    if raw_path.is_absolute():
        if workspace_root is not None:
            resolved = _safe_existing_path(raw_path, workspace_root)
            if resolved is not None:
                return resolved
        for root in _uploads_root_candidates(uploads_root):
            resolved = _safe_existing_path(raw_path, root)
            if resolved is not None:
                return resolved
        return None

    if workspace_root is None:
        return None

    parsed_path = unquote(urlsplit(text).path or text).replace("\\", "/").strip()
    relative = PurePosixPath(parsed_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        return None
    return _safe_existing_path(workspace_root / Path(*relative.parts), workspace_root)


def _upload_relative_path(value: str) -> PurePosixPath | None:
    parsed_path = unquote(urlsplit(str(value or "").strip()).path or value).replace("\\", "/").strip()
    if parsed_path.startswith(f"{API_V1_STR}/"):
        parsed_path = parsed_path.removeprefix(f"{API_V1_STR}/")
    elif parsed_path.startswith(API_V1_STR.lstrip("/") + "/"):
        parsed_path = parsed_path.removeprefix(API_V1_STR.lstrip("/") + "/")
    elif parsed_path.startswith("/"):
        parsed_path = parsed_path[1:]

    if not parsed_path.startswith("uploads/"):
        return None

    relative = PurePosixPath(parsed_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        return None
    return relative


def _resolve_under_root(relative: PurePosixPath, root: Path) -> Path | None:
    parts = relative.parts[1:] if relative.parts and relative.parts[0] == root.name else relative.parts
    if not parts:
        return None
    return _safe_existing_path(root / Path(*parts), root)


def _uploads_root_candidates(uploads_root: Path | None) -> list[Path]:
    roots = [uploads_root] if uploads_root is not None else [
        Path("uploads"),
        Path(__file__).resolve().parents[2] / "uploads",
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if root is None:
            continue
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resolved)
    return deduped


def _safe_existing_path(path: Path, root: Path) -> Path | None:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        return None

    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved
