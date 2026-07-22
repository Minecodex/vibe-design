from __future__ import annotations

from app.core.config import settings

from .labels import (
    RESOURCE_BROWSER,
    RESOURCE_CPU_TOOL,
    RESOURCE_FILE_IO,
    RESOURCE_LLM,
    RESOURCE_NETWORK,
    RESOURCE_OFFICE,
    RESOURCE_SUBPROCESS,
)


def resource_budgets() -> dict[str, int]:
    return {
        RESOURCE_LLM: max(int(getattr(settings, "HARNESS_RESOURCE_LLM_CONCURRENCY", 16) or 16), 1),
        RESOURCE_FILE_IO: max(int(getattr(settings, "HARNESS_RESOURCE_FILE_IO_CONCURRENCY", 10) or 10), 1),
        RESOURCE_CPU_TOOL: max(int(getattr(settings, "HARNESS_RESOURCE_CPU_TOOL_CONCURRENCY", 4) or 4), 1),
        RESOURCE_SUBPROCESS: max(int(getattr(settings, "HARNESS_RESOURCE_SUBPROCESS_CONCURRENCY", 8) or 8), 1),
        RESOURCE_BROWSER: max(int(getattr(settings, "HARNESS_RESOURCE_BROWSER_CONCURRENCY", 2) or 2), 1),
        RESOURCE_OFFICE: max(int(getattr(settings, "HARNESS_RESOURCE_OFFICE_CONCURRENCY", 1) or 1), 1),
        RESOURCE_NETWORK: max(int(getattr(settings, "HARNESS_RESOURCE_NETWORK_CONCURRENCY", 16) or 16), 1),
    }
