from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import API_V1_STR

REFERENCE_GALLERY_UPLOAD_ROOT = Path("uploads") / "reference-gallery"


@dataclass(frozen=True)
class ReferenceGalleryUpload:
    path: Path
    url: str
    relative_path: str


def build_reference_gallery_upload(
    filename: str,
    *,
    now: datetime | None = None,
    root: Path = REFERENCE_GALLERY_UPLOAD_ROOT,
) -> ReferenceGalleryUpload:
    if Path(filename).name != filename:
        raise ValueError("Reference gallery upload filename must not include path separators")

    partition = (now or datetime.now()).strftime("%Y-%m")
    target_dir = root / partition
    target_dir.mkdir(parents=True, exist_ok=True)

    relative_path = f"{partition}/{filename}"
    path = (target_dir / filename).resolve()
    return ReferenceGalleryUpload(
        path=path,
        url=f"{API_V1_STR}/uploads/reference-gallery/{relative_path}",
        relative_path=relative_path,
    )
