from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.services.provider_request_policy import ProviderRequestPolicy


@dataclass(frozen=True)
class ProviderGateDecision:
    allowed: bool
    retry_after_seconds: float = 0.0
    deferred_until: datetime | None = None


class ProviderRequestGate:
    def __init__(self, *, namespace: str = "provider-operations") -> None:
        self.namespace = str(namespace or "provider-operations").strip() or "provider-operations"

    async def allow(
        self,
        *,
        provider: str,
        operation: str,
        priority: str = "background",
    ) -> ProviderGateDecision:
        limit, window_seconds = provider_rate_limit_for_operation(operation)
        decision = await ProviderRequestPolicy(namespace=self.namespace).allow(
            provider=provider,
            operation=operation,
            priority=priority,
            limit=limit,
            window_seconds=window_seconds,
        )
        if decision.allowed:
            return ProviderGateDecision(allowed=True)
        retry_after = max(float(decision.retry_after_seconds or 0.0), 1.0)
        return ProviderGateDecision(
            allowed=False,
            retry_after_seconds=retry_after,
            deferred_until=datetime.now(UTC) + timedelta(seconds=retry_after),
        )


def provider_rate_limit_for_operation(operation: str) -> tuple[int, float]:
    normalized = str(operation or "").strip().lower()
    if normalized == "generation_query":
        return (
            max(int(settings.PROVIDER_RATE_LIMIT_GENERATION_QUERY_LIMIT), 0),
            max(float(settings.PROVIDER_RATE_LIMIT_GENERATION_QUERY_WINDOW_SECONDS), 0.001),
        )
    if normalized == "result_download":
        return (
            max(int(settings.PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_LIMIT), 0),
            max(float(settings.PROVIDER_RATE_LIMIT_RESULT_DOWNLOAD_WINDOW_SECONDS), 0.001),
        )
    if normalized == "balance_fetch":
        return (
            max(int(settings.PROVIDER_RATE_LIMIT_BALANCE_FETCH_LIMIT), 0),
            max(float(settings.PROVIDER_RATE_LIMIT_BALANCE_FETCH_WINDOW_SECONDS), 0.001),
        )
    if normalized == "billing_fetch":
        return (
            max(int(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT), 0),
            max(float(settings.PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS), 0.001),
        )
    return (
        max(int(settings.PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_LIMIT), 0),
        max(float(settings.PROVIDER_RATE_LIMIT_GENERATION_SUBMIT_WINDOW_SECONDS), 0.001),
    )
