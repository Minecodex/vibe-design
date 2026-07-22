from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LicenseActivateRequest(BaseModel):
    code: str


class LicenseActivateResponse(BaseModel):
    expires_at: datetime
    expired: bool


class HealthStatusResponse(BaseModel):
    status: str
    env: str
    app: str
    deploy_type: str
    license_status: str
    license_edition: str | None
    license_expired: bool
    license_expires_at: str | None
    provider_balance_sync_enabled: bool = False
    redis: dict[str, Any] | None = None
    agent_catalog: dict[str, Any] | None = None
    background: dict[str, Any] | None = None
