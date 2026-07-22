from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings


def get_apimart_key_fingerprint(api_key: str) -> str:
    """Return the stable, non-reversible identifier used for APIMart balance data."""
    value = str(api_key or "").strip()
    if not value:
        raise ValueError("APIMart API key is required")
    return hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
