import logging
import sys
import warnings

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if not settings.is_production else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = not settings.UVICORN_ACCESS_LOG_ENABLED
    if not settings.UVICORN_ACCESS_LOG_ENABLED:
        access_logger.setLevel(logging.WARNING)
    for name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger("app.services.agent_harness.workflow.diagnostics").setLevel(logging.WARNING)
    # Silence noisy library loggers. asyncio emits "Using selector" every time
    # a short-lived loop is created when the root logger is DEBUG.
    for name in (
        "asyncio",
        "httpx",
        "httpcore",
        "pyvips",
        "pyvips.vobject",
        "pyvips.voperation",
        "aiomysql",
        "passlib",
        "passlib.registry",
        "passlib.utils",
        "PIL",
        "PIL.Image",
        "PIL.TiffImagePlugin",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Suppress Pydantic protected namespace warnings (model_ prefix fields)
    warnings.filterwarnings("ignore", message="Field .* has conflict with protected namespace")
