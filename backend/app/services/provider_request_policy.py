from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.redis_coordination import get_redis_coordinator


@dataclass(frozen=True)
class ProviderRequestDecision:
    allowed: bool
    retry_after_seconds: float = 0.0
    reason: str | None = None


class ProviderRequestPolicy:
    def __init__(self, *, namespace: str = "default") -> None:
        self.namespace = str(namespace or "default").strip() or "default"

    async def allow(
        self,
        *,
        provider: str,
        operation: str,
        priority: str = "normal",
        limit: int,
        window_seconds: float,
    ) -> ProviderRequestDecision:
        coordinator = get_redis_coordinator()
        bucket = coordinator.keys.build(
            domain="provider-request",
            purpose="rate-limit",
            resource_parts=[
                self.namespace,
                str(provider or "unknown").strip().lower() or "unknown",
                str(operation or "unknown").strip().lower() or "unknown",
                str(priority or "normal").strip().lower() or "normal",
            ],
        )
        result = await coordinator.rate_limit(
            bucket,
            limit=max(int(limit), 0),
            window_seconds=max(float(window_seconds), 0.001),
        )
        allowed = bool(result.get("allowed"))
        return ProviderRequestDecision(
            allowed=allowed,
            retry_after_seconds=float(result.get("retry_after_seconds") or 0.0),
            reason=None if allowed else "rate_limited",
        )


def classify_provider_error(error: BaseException | str) -> str:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "retryable_timeout"
    if isinstance(error, (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.NetworkError)):
        return "retryable_network"
    name = type(error).__name__ if isinstance(error, BaseException) else ""
    if name in {"ConnectionError", "TimeoutError"}:
        return "retryable_network"
    text = str(error).strip().lower()
    if "rate" in text and "limit" in text:
        return "retryable_rate_limit"
    if "unauthorized" in text or "forbidden" in text:
        return "terminal_auth"
    return "unknown_provider_error"
