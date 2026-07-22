import logging
import os
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_v1_router
from app.core.config import API_V1_STR, settings
from app.core.i18n import get_lang, translate_msg
from app.core.logging import setup_logging
from app.core.uploads_static import UploadsStaticFiles
from app.db.session import AsyncSessionLocal
from app.services.license_service import LicenseService

warnings.filterwarnings("ignore", message="Field .* has conflict with protected namespace")

logger = logging.getLogger(__name__)

os.makedirs("uploads/avatars", exist_ok=True)
os.makedirs("uploads/canvas", exist_ok=True)
os.makedirs("uploads/generated", exist_ok=True)
os.makedirs("uploads/reference-gallery", exist_ok=True)
os.makedirs("workspace", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from app.core.asyncio_diagnostics import enable_asyncio_diagnostics

    enable_asyncio_diagnostics(component="api")
    from app.services.agent_harness.catalog import warmup_agent_catalog

    await warmup_agent_catalog()
    from app.services.realtime_listener_manager import RealtimeListenerManager
    realtime_listener_manager = RealtimeListenerManager()
    await realtime_listener_manager.start()
    yield
    await realtime_listener_manager.stop()
    from app.services.agent_harness.runtime.eventing import notification_coalescer
    for coalescer in notification_coalescer.all_coalescers():
        try:
            await coalescer.aclose()
        except Exception:  # noqa: BLE001
            logger.info("Conversation event coalescer shutdown failed", exc_info=True)
    from app.services.agent_harness.runtime.eventing import presentation_delta_queue
    try:
        await presentation_delta_queue.aclose(flush=True, timeout=5.0)
    except Exception:  # noqa: BLE001
        logger.info("Presentation delta queue shutdown failed", exc_info=True)
    from app.core.redis_coordination import get_redis_coordinator
    await get_redis_coordinator().shutdown_wakeup_subscribers()
    from app.db.harness_session import shutdown_harness_db_executor
    shutdown_harness_db_executor()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    openapi_url=f"{API_V1_STR}/openapi.json",
    docs_url=f"{API_V1_STR}/docs",
    redoc_url=f"{API_V1_STR}/redoc",
    lifespan=lifespan,
)
app.state.db_session_factory = AsyncSessionLocal

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=API_V1_STR)

app.mount(f"{API_V1_STR}/uploads", UploadsStaticFiles(directory="uploads"), name="uploads")

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    lang = get_lang(request)
    detail = translate_msg(exc.detail, lang) if isinstance(exc.detail, str) else exc.detail
    headers = getattr(exc, "headers", None)
    if headers:
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=headers)
    return JSONResponse({"detail": detail}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    lang = get_lang(request)
    errors = exc.errors()
    for error in errors:
        error["msg"] = translate_msg(error["msg"], lang)
        if "ctx" in error:
            error.pop("ctx")
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )

@app.get("/health")
async def health_check():
    async with app.state.db_session_factory() as session:
        return await LicenseService(session).build_health_payload(
            app_name=settings.APP_NAME,
            app_env=settings.APP_ENV,
            deploy_type=settings.DEPLOY_TYPE,
        )
