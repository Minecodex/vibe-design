from datetime import datetime

from pydantic import BaseModel, Field


class PhotoshopEditJobCreate(BaseModel):
    source_canvas_item_id: str
    svg_url: str


class PhotoshopEditJobClaimResponse(BaseModel):
    id: int
    project_id: int
    request_user_id: int
    source_canvas_item_id: str
    source_asset_id: int | None = None
    svg_url: str
    status: str
    claimed_by_user_id: int | None = None
    result_asset_id: int | None = None
    result_canvas_item_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PhotoshopEditJobSaveRequest(BaseModel):
    result_url: str
    width: int = Field(default=1024, ge=1)
    height: int = Field(default=1024, ge=1)
    name: str | None = None
    target_project_id: int | None = None


class PhotoshopPluginSaveRequest(BaseModel):
    result_url: str
    width: int = Field(default=1024, ge=1)
    height: int = Field(default=1024, ge=1)


class PhotoshopPluginSaveResponse(BaseModel):
    project_id: int
    asset_id: int
    canvas_item_id: str
    url: str

