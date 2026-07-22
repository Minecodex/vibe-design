"""Deprecated license runtime compatibility shim.

License records no longer gate requests. This module intentionally does not
read or mutate provider credentials.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(slots=True)
class LicenseStatus:
    expired: bool = False
    expires_at: datetime | None = None
    status: Literal["active"] = "active"
    edition: Literal["flagship"] = "flagship"
    builtin_provider_code: str = "apimart"
    billing_unit_per_yuan: int = 500000


class LicenseRuntimeState:
    def invalidate(self) -> None:
        return None

    def reset(self) -> None:
        return None

    async def force_refresh(self, _db) -> LicenseStatus:
        return LicenseStatus()

    async def get_status(self, _db) -> LicenseStatus:
        return LicenseStatus()


license_runtime_state = LicenseRuntimeState()
