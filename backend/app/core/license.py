import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

LICENSE_ENVELOPE_VERSION = 2
LICENSE_EDITIONS = {"premium", "flagship"}
BUILTIN_PROVIDER_CODES = {"apimart", "lingyaai"}
DEFAULT_BUILTIN_PROVIDER_CODE = "apimart"
DEFAULT_BILLING_UNIT_PER_YUAN = 500000
LicenseEdition = Literal["premium", "flagship"]
LicenseRuntimeStatus = Literal["active", "expired", "invalid", "missing"]


@dataclass(slots=True)
class LicenseStatus:
    expired: bool
    expires_at: datetime | None
    status: LicenseRuntimeStatus = "missing"
    edition: LicenseEdition | None = None
    builtin_provider_code: str = DEFAULT_BUILTIN_PROVIDER_CODE
    billing_unit_per_yuan: int = DEFAULT_BILLING_UNIT_PER_YUAN


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding_needed = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding_needed))


def _load_public_key():
    pem = settings.REDEMPTION_PUBLIC_KEY
    if not pem:
        return None
    pem = pem.replace("\\n", "\n")
    return serialization.load_pem_public_key(pem.encode())


def _derive_envelope_key() -> bytes:
    return hashlib.sha256(settings.LICENSE_ENVELOPE_KEY.encode()).digest()


def _serialize_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def compute_license_token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


def build_license_code(
    *,
    private_key,
    expires_at: datetime,
    builtin_provider_api_key: str,
    edition: LicenseEdition,
    builtin_provider_code: str = DEFAULT_BUILTIN_PROVIDER_CODE,
    billing_unit_per_yuan: int = DEFAULT_BILLING_UNIT_PER_YUAN,
) -> str:
    if builtin_provider_code not in BUILTIN_PROVIDER_CODES:
        raise ValueError("builtin provider code is invalid")
    if not isinstance(billing_unit_per_yuan, int) or billing_unit_per_yuan <= 0:
        raise ValueError("billing unit per yuan is invalid")
    payload = {
        "expires_at": expires_at.isoformat(),
        "builtin_provider_api_key": builtin_provider_api_key,
        "edition": edition,
        "builtin_provider_code": builtin_provider_code,
        "billing_unit_per_yuan": billing_unit_per_yuan,
    }
    payload_bytes = _serialize_payload(payload)
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    envelope_bytes = _serialize_payload(
        {
            "version": LICENSE_ENVELOPE_VERSION,
            "payload": _b64url_encode(payload_bytes),
            "signature": _b64url_encode(signature),
        }
    )
    aesgcm = AESGCM(_derive_envelope_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, envelope_bytes, None)
    return _b64url_encode(nonce + ciphertext)


def verify_license_code(code_str: str) -> dict:
    public_key = _load_public_key()
    if not public_key:
        raise ValueError("license feature is not configured")

    try:
        raw = _b64url_decode(code_str.strip())
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("license code format is invalid") from exc

    if len(raw) <= 12:
        raise ValueError("license code format is invalid")

    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(_derive_envelope_key())
    try:
        envelope_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("license code decryption failed") from exc

    try:
        envelope = json.loads(envelope_bytes.decode())
        version = envelope.get("version")
        if version != LICENSE_ENVELOPE_VERSION:
            if version == 1:
                raise ValueError("legacy license versions are no longer supported")
            raise ValueError("license code is invalid")
        payload_bytes = _b64url_decode(envelope["payload"])
        signature_bytes = _b64url_decode(envelope["signature"])
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("license code format is invalid") from exc

    try:
        public_key.verify(
            signature_bytes,
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise ValueError("license code is invalid") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("License code verification failed: %s", exc)
        raise ValueError("license code verification failed") from exc

    try:
        data = json.loads(payload_bytes.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("license code data is invalid") from exc

    if "expires_at" not in data or "builtin_provider_api_key" not in data or "edition" not in data:
        raise ValueError("license code is invalid")

    builtin_provider_api_key = data["builtin_provider_api_key"]
    if not isinstance(builtin_provider_api_key, str) or not builtin_provider_api_key.strip():
        raise ValueError("license code is invalid")

    edition = data["edition"]
    if edition not in LICENSE_EDITIONS:
        raise ValueError("license code is invalid")

    builtin_provider_code = data.get("builtin_provider_code", DEFAULT_BUILTIN_PROVIDER_CODE)
    if builtin_provider_code not in BUILTIN_PROVIDER_CODES:
        raise ValueError("license code is invalid")

    billing_unit_per_yuan = data.get("billing_unit_per_yuan", DEFAULT_BILLING_UNIT_PER_YUAN)
    if not isinstance(billing_unit_per_yuan, int) or billing_unit_per_yuan <= 0:
        raise ValueError("license code is invalid")

    try:
        expires_at = datetime.fromisoformat(data["expires_at"])
    except ValueError as exc:
        raise ValueError("expiration is invalid") from exc

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    return {
        "expires_at": expires_at,
        "builtin_provider_api_key": builtin_provider_api_key,
        "edition": edition,
        "builtin_provider_code": builtin_provider_code,
        "billing_unit_per_yuan": billing_unit_per_yuan,
    }
