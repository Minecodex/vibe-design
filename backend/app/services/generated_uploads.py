from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from app.core.config import API_V1_STR

GENERATED_UPLOAD_ROOT = Path("uploads") / "generated"


@dataclass(frozen=True)
class GeneratedUpload:
    path: Path
    url: str
    relative_path: str


def build_generated_upload(
    filename: str,
    *,
    now: datetime | None = None,
    root: Path = GENERATED_UPLOAD_ROOT,
) -> GeneratedUpload:
    """Create a generated upload path partitioned by year-month."""
    if Path(filename).name != filename:
        raise ValueError("Generated upload filename must not include path separators")

    partition = (now or datetime.now()).strftime("%Y-%m")
    target_dir = root / partition
    target_dir.mkdir(parents=True, exist_ok=True)

    relative_path = f"{partition}/{filename}"
    path = (target_dir / filename).resolve()
    return GeneratedUpload(
        path=path,
        url=f"{API_V1_STR}/uploads/generated/{relative_path}",
        relative_path=relative_path,
    )


def resolve_generated_upload_path(
    url: str,
    *,
    root: Path = GENERATED_UPLOAD_ROOT,
    must_exist: bool = True,
) -> Path | None:
    """Resolve generated upload URLs, including legacy flat paths."""
    prefix = f"{API_V1_STR}/uploads/generated/"
    if not url.startswith(prefix):
        return None

    raw_relative = url.removeprefix(prefix)
    relative = PurePosixPath(raw_relative)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.name
    ):
        return None

    root_path = root.resolve()
    candidate = (root_path / Path(*relative.parts)).resolve()
    if root_path != candidate and root_path not in candidate.parents:
        return None
    if must_exist and not candidate.exists():
        return None
    return candidate
