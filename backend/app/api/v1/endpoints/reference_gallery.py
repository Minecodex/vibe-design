import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.schemas.reference_gallery import (
    ReferenceImageRead,
    ReferenceImageUpdateRequest,
    ReferenceTaxonomyCreateRequest,
    ReferenceTaxonomyRead,
    ReferenceTaxonomyUpdateRequest,
    ReferenceUploadResultItem,
)
from app.services.reference_gallery_service import (
    ReferenceGalleryConflictError,
    ReferenceGalleryError,
    ReferenceGalleryNotFoundError,
    ReferenceGalleryService,
)
from app.services.reference_gallery_uploads import build_reference_gallery_upload
from app.services.upload_writer import (
    IMAGE_FILE_EXTENSIONS,
    verify_image_file,
    write_upload_with_limit,
)

router = APIRouter(prefix="/reference-gallery", tags=["reference-gallery"])

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _ensure_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


def _raise_service_error(error: ReferenceGalleryError) -> None:
    if isinstance(error, ReferenceGalleryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, ReferenceGalleryConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/taxonomies", response_model=list[ReferenceTaxonomyRead])
async def list_taxonomies(
    db: DbSession,
    user: CurrentUser,
    kind: str = Query(...),
):
    try:
        return await ReferenceGalleryService(db).list_taxonomies(kind=kind)
    except ReferenceGalleryError as error:
        _raise_service_error(error)


@router.post("/taxonomies", response_model=ReferenceTaxonomyRead)
async def create_taxonomy(
    body: ReferenceTaxonomyCreateRequest,
    db: DbSession,
    user: CurrentUser,
):
    _ensure_admin(user)
    svc = ReferenceGalleryService(db)
    try:
        taxonomy = await svc.create_taxonomy(
            user_id=user.id,
            kind=body.kind,
            name=body.name,
            prompt=body.prompt,
        )
    except ReferenceGalleryError as error:
        _raise_service_error(error)
    return next(item for item in await svc.list_taxonomies(kind=taxonomy.kind) if item["id"] == taxonomy.id)


@router.patch("/taxonomies/{taxonomy_id}", response_model=ReferenceTaxonomyRead)
async def update_taxonomy(
    taxonomy_id: int,
    body: ReferenceTaxonomyUpdateRequest,
    db: DbSession,
    user: CurrentUser,
):
    _ensure_admin(user)
    svc = ReferenceGalleryService(db)
    data = body.model_dump(exclude_unset=True)
    try:
        taxonomy = await svc.update_taxonomy(taxonomy_id, **data)
    except ReferenceGalleryError as error:
        _raise_service_error(error)
    return next(item for item in await svc.list_taxonomies(kind=taxonomy.kind) if item["id"] == taxonomy.id)


@router.delete("/taxonomies/{taxonomy_id}")
async def delete_taxonomy(taxonomy_id: int, db: DbSession, user: CurrentUser):
    _ensure_admin(user)
    try:
        await ReferenceGalleryService(db).delete_taxonomy(taxonomy_id)
    except ReferenceGalleryError as error:
        _raise_service_error(error)
    return {"ok": True}


@router.get("/images", response_model=list[ReferenceImageRead])
async def list_images(
    db: DbSession,
    user: CurrentUser,
    category_id: int | None = None,
    style_id: int | None = None,
    classification_id: int | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return await ReferenceGalleryService(db).list_images(
        category_id=category_id,
        style_id=style_id,
        classification_id=classification_id,
        skip=skip,
        limit=limit,
    )


@router.patch("/images/{image_id}", response_model=ReferenceImageRead)
async def update_image(
    image_id: int,
    body: ReferenceImageUpdateRequest,
    db: DbSession,
    user: CurrentUser,
):
    _ensure_admin(user)
    data = body.model_dump(exclude_unset=True)
    try:
        return await ReferenceGalleryService(db).update_image(image_id, **data)
    except ReferenceGalleryError as error:
        _raise_service_error(error)


@router.delete("/images/{image_id}")
async def delete_image(image_id: int, db: DbSession, user: CurrentUser):
    _ensure_admin(user)
    try:
        await ReferenceGalleryService(db).delete_image(image_id)
    except ReferenceGalleryError as error:
        _raise_service_error(error)
    return {"ok": True}


@router.post("/uploads", response_model=list[ReferenceUploadResultItem])
async def upload_images(
    db: DbSession,
    user: CurrentUser,
    category_id: int = Query(..., ge=1),
    style_id: int | None = Query(default=None, ge=1),
    classification_id: int | None = Query(default=None, ge=1),
    files: list[UploadFile] = File(...),
):
    _ensure_admin(user)
    svc = ReferenceGalleryService(db)
    results: list[dict] = []
    for file in files:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的图片格式: {file.content_type}",
            )
        ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
        upload = build_reference_gallery_upload(f"rg_{uuid.uuid4().hex}.{ext}")
        destination = Path(upload.path)
        await write_upload_with_limit(
            file,
            destination,
            max_bytes=settings.CANVAS_IMAGE_UPLOAD_MAX_BYTES,
        )
        try:
            verify_image_file(
                destination,
                allowed_extensions=IMAGE_FILE_EXTENSIONS,
                content_type=file.content_type,
            )
            result = await svc.create_image(
                user_id=user.id,
                url=upload.url,
                name=file.filename or upload.url,
                category_id=category_id,
                style_id=style_id,
                classification_id=classification_id,
            )
        except ReferenceGalleryError as error:
            destination.unlink(missing_ok=True)
            _raise_service_error(error)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        results.append(result)
    return results
