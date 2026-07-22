from pydantic import BaseModel


class UploadLimits(BaseModel):
    avatar_max_bytes: int
    canvas_image_max_bytes: int
    canvas_video_max_bytes: int
    harness_attachment_max_bytes: int


class PublicConfigResponse(BaseModel):
    app_name: str
    app_name_en: str
    upload_limits: UploadLimits
