from fastapi import APIRouter

from app.core.config import settings
from app.schemas.public_config import PublicConfigResponse

router = APIRouter(tags=["public-config"])


@router.get("/public-config", response_model=PublicConfigResponse)
async def get_public_config() -> PublicConfigResponse:
    return PublicConfigResponse(
        app_name=settings.APP_NAME,
        app_name_en=settings.APP_NAME_EN,
        upload_limits={
            "avatar_max_bytes": settings.AVATAR_UPLOAD_MAX_BYTES,
            "canvas_image_max_bytes": settings.CANVAS_IMAGE_UPLOAD_MAX_BYTES,
            "canvas_video_max_bytes": settings.CANVAS_VIDEO_UPLOAD_MAX_BYTES,
            "harness_attachment_max_bytes": settings.HARNESS_ATTACHMENT_UPLOAD_MAX_BYTES,
        },
    )
