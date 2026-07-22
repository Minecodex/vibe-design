from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    title: str = "Untitled"
    status: str | None = "pending"


class ProjectUpdate(BaseModel):
    title: str | None = None
    canvas_data: dict | list | None = None
    canvas_base_revision: int | None = None
    status: str | None = None


class ProjectPreviewItemRead(BaseModel):
    asset_type: str
    url: str
    list_preview_url: str | None = None
    list_preview_status: str | None = None


class ProjectListItemRead(BaseModel):
    id: int
    user_id: int
    title: str
    status: str
    thumbnail_url: str | None = None
    project_preview_items: list[ProjectPreviewItemRead] | None = None

    # Share settings
    share_token: str | None = None
    share_permission: str | None = None
    share_password: str | None = None
    share_expiration: int | None = None

    created_at: datetime
    updated_at: datetime
    users: list[dict] | None = None

    model_config = {"from_attributes": True}


class ProjectRead(ProjectListItemRead):
    canvas_data: dict | list | None = None
    canvas_revision: int = 0
