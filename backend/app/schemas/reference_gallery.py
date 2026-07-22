from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReferenceTaxonomyKind = Literal["category", "style", "classification"]


class ReferenceTaxonomyCreateRequest(BaseModel):
    kind: ReferenceTaxonomyKind
    name: str = Field(min_length=1, max_length=128)
    prompt: str | None = None


class ReferenceTaxonomyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    prompt: str | None = None


class ReferenceImageUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=512)
    category_id: int | None = None
    style_id: int | None = None
    classification_id: int | None = None


class ReferenceTaxonomyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ReferenceTaxonomyKind
    name: str
    prompt: str | None = None
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class ReferenceImageRead(BaseModel):
    id: int
    url: str
    name: str
    category_id: int
    category_name: str
    style_id: int | None = None
    style_name: str | None = None
    style_prompt: str | None = None
    classification_id: int | None = None
    classification_name: str | None = None
    classification_prompt: str | None = None
    list_preview_url: str | None = None
    list_preview_status: str | None = None
    created_at: datetime
    updated_at: datetime


class ReferenceUploadResultItem(ReferenceImageRead):
    pass
