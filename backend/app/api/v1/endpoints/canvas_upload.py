import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, File, UploadFile
from app.api.deps import DbSession, CurrentUser
from app.core.config import API_V1_STR, settings
from app.services.upload_writer import (
    IMAGE_FILE_EXTENSIONS,
    IMAGE_VECTOR_EXTENSIONS,
    VIDEO_FILE_EXTENSIONS,
    sanitize_svg_file,
    verify_image_file,
    verify_video_file,
    write_upload_with_limit,
)

router = APIRouter(prefix="/projects", tags=["canvas-upload"])

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"}


@router.post("/{project_id}/upload/image")
async def upload_canvas_image(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    """上传图片到画布"""
    from app.services.project_service import ProjectService
    proj_svc = ProjectService(db)
    # is_admin=False enforces membership/ownership
    await proj_svc.get(project_id, user.id, is_admin=False)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图片格式: {file.content_type}",
        )

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
    filename = f"{uuid.uuid4()}.{ext}"
    upload_dir = f"uploads/canvas/{project_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = f"{upload_dir}/{filename}"

    destination = Path(file_path)
    await write_upload_with_limit(
        file,
        destination,
        max_bytes=settings.CANVAS_IMAGE_UPLOAD_MAX_BYTES,
    )
    try:
        if destination.suffix.lower() in IMAGE_VECTOR_EXTENSIONS:
            sanitize_svg_file(destination)
        else:
            verify_image_file(
                destination,
                allowed_extensions=IMAGE_FILE_EXTENSIONS,
                content_type=file.content_type,
            )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    file_url = f"{API_V1_STR}/uploads/canvas/{project_id}/{filename}"
    return {"url": file_url, "type": "image", "filename": filename}


@router.post("/{project_id}/upload/video")
async def upload_canvas_video(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    """上传视频到画布"""
    from app.services.project_service import ProjectService
    proj_svc = ProjectService(db)
    # is_admin=False enforces membership/ownership
    await proj_svc.get(project_id, user.id, is_admin=False)

    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的视频格式: {file.content_type}",
        )

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "mp4"
    filename = f"{uuid.uuid4()}.{ext}"
    upload_dir = f"uploads/canvas/{project_id}"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = f"{upload_dir}/{filename}"

    destination = Path(file_path)
    await write_upload_with_limit(
        file,
        destination,
        max_bytes=settings.CANVAS_VIDEO_UPLOAD_MAX_BYTES,
    )
    try:
        verify_video_file(
            destination,
            allowed_extensions=VIDEO_FILE_EXTENSIONS,
            content_type=file.content_type,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    file_url = f"{API_V1_STR}/uploads/canvas/{project_id}/{filename}"
    return {"url": file_url, "type": "video", "filename": filename}
