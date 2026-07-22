from __future__ import annotations

import logging

from app.core.redis_coordination import get_redis_coordinator

logger = logging.getLogger(__name__)


def _wake_key() -> str:
    # Use the canonical key builder so that _domain_from_target() in
    # redis_coordination can extract a meaningful "domain" segment
    # (previously this was a flat string and showed up as domain=unknown
    # in every degraded-operation log line).
    coordinator = get_redis_coordinator()
    return coordinator.keys.build(domain="agent-run", purpose="requests")


async def wake_agent_run_worker() -> None:
    try:
        await get_redis_coordinator().wakeup(_wake_key())
    except Exception:
        logger.info("Agent run worker wakeup failed", exc_info=True)


async def wait_agent_run_wakeup(*, timeout_seconds: float) -> bool:
    try:
        result = await get_redis_coordinator().wait_wakeup(
            _wake_key(),
            timeout_seconds=max(float(timeout_seconds), 0.0),
        )
        return bool(result.get("woken"))
    except Exception:
        logger.info("Agent run worker wake wait failed", exc_info=True)
        return False
