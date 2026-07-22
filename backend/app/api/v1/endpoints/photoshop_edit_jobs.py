from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.photoshop_edit_job import (
    PhotoshopEditJobClaimResponse,
    PhotoshopEditJobCreate,
    PhotoshopEditJobSaveRequest,
    PhotoshopPluginSaveRequest,
    PhotoshopPluginSaveResponse,
)
from app.services.license_service import LicenseService
from app.services.photoshop_edit_job_service import PhotoshopEditJobService

router = APIRouter(tags=["photoshop-edit-jobs"])


@router.post("/projects/{project_id}/photoshop-edit-jobs", response_model=PhotoshopEditJobClaimResponse)
async def create_photoshop_edit_job(
    project_id: int,
    data: PhotoshopEditJobCreate,
    db: DbSession,
    user: CurrentUser,
):
    await LicenseService(db).ensure_capability("photoshop_edit")
    service = PhotoshopEditJobService(db)
    return await service.create_job(project_id=project_id, user=user, data=data)


@router.get("/photoshop-edit-jobs/pending", response_model=list[PhotoshopEditJobClaimResponse])
async def list_pending_photoshop_edit_jobs(
    db: DbSession,
    user: CurrentUser,
):
    service = PhotoshopEditJobService(db)
    return await service.list_pending_jobs(user)


@router.post("/photoshop-edit-jobs/{job_id}/claim", response_model=PhotoshopEditJobClaimResponse)
async def claim_photoshop_edit_job(
    job_id: int,
    db: DbSession,
    user: CurrentUser,
):
    service = PhotoshopEditJobService(db)
    return await service.claim_job(job_id=job_id, user=user)


@router.post("/photoshop-edit-jobs/{job_id}/cancel", response_model=PhotoshopEditJobClaimResponse)
async def cancel_photoshop_edit_job(
    job_id: int,
    db: DbSession,
    user: CurrentUser,
):
    service = PhotoshopEditJobService(db)
    return await service.cancel_job(job_id=job_id, user=user)


@router.post("/photoshop-edit-jobs/{job_id}/save", response_model=PhotoshopEditJobClaimResponse)
async def save_photoshop_edit_job(
    job_id: int,
    data: PhotoshopEditJobSaveRequest,
    db: DbSession,
    user: CurrentUser,
):
    await LicenseService(db).ensure_capability("photoshop_edit")
    service = PhotoshopEditJobService(db)
    return await service.save_job_result(job_id=job_id, user=user, data=data)


@router.post("/projects/{project_id}/photoshop-plugin/save", response_model=PhotoshopPluginSaveResponse)
async def save_photoshop_plugin_result(
    project_id: int,
    data: PhotoshopPluginSaveRequest,
    db: DbSession,
    user: CurrentUser,
):
    await LicenseService(db).ensure_capability("photoshop_plugin_save")
    service = PhotoshopEditJobService(db)
    asset, canvas_item_id = await service.save_plugin_result(project_id=project_id, user=user, data=data)
    return PhotoshopPluginSaveResponse(
        project_id=asset.project_id,
        asset_id=asset.id,
        canvas_item_id=canvas_item_id,
        url=asset.url,
    )
