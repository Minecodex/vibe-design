from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ArtifactFamily(StrEnum):
    WEB = "web"
    SLIDE = "slide"
    SHEET = "sheet"
    DOCUMENT = "document"
    MEDIA = "media"
    FILE = "file"


class PublishPolicy(StrEnum):
    FILE = "file"
    HTML_BUNDLE = "html_bundle"
    SHEET = "sheet"


class PreviewPolicy(StrEnum):
    FILE = "file"
    WEB_BUNDLE = "web_bundle"
    NONE = "none"


class StructuredSheet(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class StructuredArtifactDraft(BaseModel):
    artifact_id: str
    family: ArtifactFamily = ArtifactFamily.SHEET
    title: str | None = None
    sheets: list[StructuredSheet | dict[str, Any]] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    pages: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_notes: list[str] = Field(default_factory=list)


def normalize_rel(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("project/"):
        normalized = normalized[8:]
    return normalized.strip("/")


def project_path(value: Any) -> str:
    normalized = normalize_rel(value)
    return f"project/{normalized}" if normalized else "project"


def is_inside(path: str, root: str | None) -> bool:
    normalized = normalize_rel(path)
    normalized_root = normalize_rel(root)
    if not normalized_root:
        return True
    return normalized == normalized_root or normalized.startswith(f"{normalized_root}/")
