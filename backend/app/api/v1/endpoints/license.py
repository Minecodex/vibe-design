from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.license import LicenseActivateRequest, LicenseActivateResponse
from app.services.license_service import LicenseService

router = APIRouter(prefix="/license", tags=["license"])


@router.post("/activate", response_model=LicenseActivateResponse)
async def activate_license(body: LicenseActivateRequest, db: DbSession) -> LicenseActivateResponse:
    service = LicenseService(db)
    data = await service.activate(body.code)
    return LicenseActivateResponse(
        expires_at=data["expires_at"],
        expired=data["expired"],
    )
