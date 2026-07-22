from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.license import HealthStatusResponse
from app.services.license_service import LicenseService

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthStatusResponse)
async def health_check(db: DbSession) -> HealthStatusResponse:
    payload = await LicenseService(db).build_health_payload(
        app_name=settings.APP_NAME,
        app_env=settings.APP_ENV,
        deploy_type=settings.DEPLOY_TYPE,
    )
    return HealthStatusResponse(**payload)
