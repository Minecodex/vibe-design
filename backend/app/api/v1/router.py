from fastapi import APIRouter

from app.api.v1.endpoints import (
    assets,
    apimart_keys,
    auth,
    billing,
    canvas_upload,
    extension_prompt_extractor,
    generation,
    harness,
    health,
    photoshop_edit_jobs,
    project_members,
    projects,
    reference_gallery,
    providers,
    public_config,
    realtime,
    share,
    users,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(health.router)
api_v1_router.include_router(public_config.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(apimart_keys.router)
api_v1_router.include_router(providers.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(generation.router)
api_v1_router.include_router(canvas_upload.router)
api_v1_router.include_router(project_members.router)
api_v1_router.include_router(share.router)
api_v1_router.include_router(assets.router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(harness.router)
api_v1_router.include_router(realtime.router)
api_v1_router.include_router(extension_prompt_extractor.router)
api_v1_router.include_router(photoshop_edit_jobs.router)
api_v1_router.include_router(reference_gallery.router)
