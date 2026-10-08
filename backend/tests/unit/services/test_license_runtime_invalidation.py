"""Compatibility invalidation hooks perform no external work."""
from unittest.mock import AsyncMock

import pytest

from app.services.license_runtime_invalidation import (
    publish_license_runtime_invalidation,
    start_license_runtime_invalidation_listener,
)


@pytest.mark.asyncio
async def test_retired_listener_does_not_subscribe_or_refresh():
    runtime = AsyncMock()
    result = await start_license_runtime_invalidation_listener(runtime_state=runtime)

    assert result is None
    assert runtime.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["license_activation", "compatibility_reset"])
async def test_retired_invalidation_returns_only_public_metadata(reason):
    result = await publish_license_runtime_invalidation(reason=reason)

    assert result == {"name": "license.runtime.invalidated", "reason": reason}
