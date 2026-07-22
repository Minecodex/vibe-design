from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.extension_prompt_extractor import PromptExtractorAnalyzeResponse
from app.services.license_service import LicenseService
from app.services.prompt_extractor import PromptExtractorService

router = APIRouter(prefix="/extension", tags=["extension"])


@router.post(
    "/prompt-extractor/analyze",
    response_model=PromptExtractorAnalyzeResponse,
)
async def analyze_prompt_extractor_image(
    locale: Annotated[str, Form(...)],
    image: Annotated[UploadFile, File(...)],
    db: DbSession,
    user: CurrentUser,
):
    await LicenseService(db).ensure_capability("prompt_extractor")
    service = PromptExtractorService(db)
    try:
        result = await service.analyze(user_id=user.id, locale=locale, image=image)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return PromptExtractorAnalyzeResponse(
        prompt=result.prompt,
        prompts=result.prompts,
        language=result.language,
        model=result.model,
        amount_cents=result.amount_cents,
    )
