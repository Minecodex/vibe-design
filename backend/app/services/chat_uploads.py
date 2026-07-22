from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ChatUpload:
    path: Path
    url: str


def build_chat_upload(filename: str, *, now: datetime | None = None) -> ChatUpload:
    """Build the dated storage path and public URL for a chat upload."""
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain path separators")

    current = now or datetime.now()
    month = current.strftime("%Y-%m")
    path = Path("uploads") / "chat" / month / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    return ChatUpload(
        path=path.resolve(),
        url=f"/api/v1/uploads/chat/{month}/{filename}",
    )
