"""Deprecated no-op license invalidation hooks."""

from typing import Any


async def publish_license_runtime_invalidation(*, reason: str) -> dict[str, Any]:
    return {"name": "license.runtime.invalidated", "reason": reason}


async def start_license_runtime_invalidation_listener(*_args, **_kwargs) -> None:
    return None
