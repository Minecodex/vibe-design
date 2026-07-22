import logging

from app.core.config import settings
from app.core.logging import setup_logging


def test_setup_logging_disables_uvicorn_access_log_by_default(monkeypatch):
    access_logger = logging.getLogger("uvicorn.access")
    previous_disabled = access_logger.disabled
    previous_level = access_logger.level

    try:
        monkeypatch.setattr(settings, "UVICORN_ACCESS_LOG_ENABLED", False)
        access_logger.disabled = False
        access_logger.setLevel(logging.INFO)

        setup_logging()

        assert access_logger.disabled is True
        assert access_logger.level == logging.WARNING
    finally:
        access_logger.disabled = previous_disabled
        access_logger.setLevel(previous_level)


def test_setup_logging_can_keep_uvicorn_access_log_enabled(monkeypatch):
    access_logger = logging.getLogger("uvicorn.access")
    previous_disabled = access_logger.disabled
    previous_level = access_logger.level

    try:
        monkeypatch.setattr(settings, "UVICORN_ACCESS_LOG_ENABLED", True)
        access_logger.disabled = True
        access_logger.setLevel(logging.INFO)

        setup_logging()

        assert access_logger.disabled is False
        assert access_logger.level == logging.INFO
    finally:
        access_logger.disabled = previous_disabled
        access_logger.setLevel(previous_level)


def test_setup_logging_suppresses_asyncio_selector_debug_logs():
    asyncio_logger = logging.getLogger("asyncio")
    previous_level = asyncio_logger.level

    try:
        asyncio_logger.setLevel(logging.DEBUG)

        setup_logging()

        assert asyncio_logger.level == logging.WARNING
    finally:
        asyncio_logger.setLevel(previous_level)


def test_setup_logging_keeps_workflow_diagnostics_at_warning():
    diagnostics_logger = logging.getLogger("app.services.agent_harness.workflow.diagnostics")
    previous_level = diagnostics_logger.level

    try:
        diagnostics_logger.setLevel(logging.INFO)

        setup_logging()

        assert diagnostics_logger.level == logging.WARNING
    finally:
        diagnostics_logger.setLevel(previous_level)


def test_setup_logging_suppresses_noisy_third_party_debug_logs():
    logger_names = (
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
    )
    previous_levels = {name: logging.getLogger(name).level for name in logger_names}

    try:
        for name in logger_names:
            logging.getLogger(name).setLevel(logging.DEBUG)

        setup_logging()

        for name in logger_names:
            assert logging.getLogger(name).level == logging.WARNING
    finally:
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)
