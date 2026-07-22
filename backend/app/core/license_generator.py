from datetime import datetime

from app.core.license import (
    DEFAULT_BILLING_UNIT_PER_YUAN,
    DEFAULT_BUILTIN_PROVIDER_CODE,
    LicenseEdition,
    build_license_code,
)


def generate_license_code(
    *,
    private_key,
    expires_at: datetime,
    builtin_provider_api_key: str,
    edition: LicenseEdition,
    builtin_provider_code: str = DEFAULT_BUILTIN_PROVIDER_CODE,
    billing_unit_per_yuan: int = DEFAULT_BILLING_UNIT_PER_YUAN,
) -> str:
    return build_license_code(
        private_key=private_key,
        expires_at=expires_at,
        builtin_provider_api_key=builtin_provider_api_key,
        edition=edition,
        builtin_provider_code=builtin_provider_code,
        billing_unit_per_yuan=billing_unit_per_yuan,
    )
