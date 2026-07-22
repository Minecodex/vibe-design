import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.license import compute_license_token_hash
from app.core.license_runtime import LicenseRuntimeState
from app.models.license import LicenseRecord
from app.repositories.license_repository import LicenseRepository
from sqlalchemy import delete


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _build_license_code(
    private_key,
    *,
    expires_at: datetime,
    builtin_provider_api_key: str,
    edition: str = "flagship",
    version: int = 2,
    builtin_provider_code: str = "apimart",
    billing_unit_per_yuan: int = 500000,
) -> str:
    payload = {
        "expires_at": expires_at.isoformat(),
        "builtin_provider_api_key": builtin_provider_api_key,
        "edition": edition,
        "builtin_provider_code": builtin_provider_code,
        "billing_unit_per_yuan": billing_unit_per_yuan,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    envelope_bytes = json.dumps(
        {
            "version": version,
            "payload": _b64url_encode(payload_bytes),
            "signature": _b64url_encode(signature),
        },
        separators=(",", ":"),
    ).encode()
    aesgcm = AESGCM(hashlib.sha256(settings.LICENSE_ENVELOPE_KEY.encode()).digest())
    nonce = os.urandom(12)
    return _b64url_encode(nonce + aesgcm.encrypt(nonce, envelope_bytes, None))


@pytest.fixture
def license_keypair(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(
        settings,
        "REDEMPTION_PUBLIC_KEY",
        public_pem.decode().replace("\n", "\\n"),
    )
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "runtime-test-envelope-key")
    return private_key


@pytest.mark.asyncio
async def test_runtime_cache_avoids_reloading_within_ttl(db_session, monkeypatch, license_keypair):
    import app.core.license_runtime as license_runtime

    settings.BUILTIN_PROVIDER_API_KEY = ""
    code = _build_license_code(
        license_keypair,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        builtin_provider_api_key="sk-runtime-cache",
    )
    db_session.add(
        LicenseRecord(
            token_hash=compute_license_token_hash(code),
            license_token=code,
        )
    )
    await db_session.commit()

    call_count = 0
    original_get_latest = LicenseRepository.get_latest

    async def counted_get_latest(self):
        nonlocal call_count
        call_count += 1
        return await original_get_latest(self)

    current_time = {"value": 100.0}
    monkeypatch.setattr(LicenseRepository, "get_latest", counted_get_latest)
    monkeypatch.setattr(license_runtime.time, "monotonic", lambda: current_time["value"])

    state = LicenseRuntimeState(ttl_seconds=3600)

    first = await state.get_status(db_session)
    second = await state.get_status(db_session)
    current_time["value"] += 3601
    third = await state.get_status(db_session)

    assert first.expired is False
    assert second.expired is False
    assert third.expired is False
    assert first.expires_at == third.expires_at
    assert first.status == "active"
    assert first.edition == "flagship"
    assert call_count == 2
    assert settings.BUILTIN_PROVIDER_API_KEY == "sk-runtime-cache"
    assert settings.BUILTIN_PROVIDER_CODE == "apimart"
    assert settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN == 500000


@pytest.mark.asyncio
async def test_runtime_cache_applies_builtin_provider_code_and_billing_unit(db_session, monkeypatch, license_keypair):
    import app.core.license_runtime as license_runtime

    code = _build_license_code(
        license_keypair,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        builtin_provider_api_key="sk-lingyaai-runtime",
        builtin_provider_code="lingyaai",
        billing_unit_per_yuan=250000,
    )
    db_session.add(
        LicenseRecord(
            token_hash=compute_license_token_hash(code),
            license_token=code,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(license_runtime.time, "monotonic", lambda: 100.0)

    state = LicenseRuntimeState(ttl_seconds=3600)
    status = await state.get_status(db_session)

    assert status.status == "active"
    assert settings.BUILTIN_PROVIDER_API_KEY == "sk-lingyaai-runtime"
    assert settings.BUILTIN_PROVIDER_CODE == "lingyaai"
    assert settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN == 250000


@pytest.mark.asyncio
async def test_runtime_cache_clears_builtin_api_key_on_bad_latest_record(db_session, monkeypatch, license_keypair):
    import app.core.license_runtime as license_runtime

    valid_code = _build_license_code(
        license_keypair,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        builtin_provider_api_key="sk-last-good",
    )
    db_session.add(
        LicenseRecord(
            token_hash=compute_license_token_hash(valid_code),
            license_token=valid_code,
        )
    )
    await db_session.commit()

    current_time = {"value": 100.0}
    monkeypatch.setattr(license_runtime.time, "monotonic", lambda: current_time["value"])

    state = LicenseRuntimeState(ttl_seconds=3600)
    initial_status = await state.get_status(db_session)

    db_session.add(
        LicenseRecord(
            token_hash=compute_license_token_hash("not-a-valid-license"),
            license_token="not-a-valid-license",
        )
    )
    await db_session.commit()
    current_time["value"] += 3601

    refreshed_status = await state.get_status(db_session)

    assert initial_status.expired is False
    assert refreshed_status.expired is True
    assert refreshed_status.status == "invalid"
    assert refreshed_status.edition is None
    assert settings.BUILTIN_PROVIDER_API_KEY == ""


@pytest.mark.asyncio
async def test_runtime_cache_rechecks_db_immediately_when_cached_status_is_expired(db_session, monkeypatch, license_keypair):
    import app.core.license_runtime as license_runtime

    await db_session.execute(delete(LicenseRecord))
    await db_session.commit()

    current_time = {"value": 100.0}
    monkeypatch.setattr(license_runtime.time, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(
        license_runtime,
        "verify_license_code",
        lambda token: {
            "expires_at": datetime.now(UTC) + timedelta(days=7),
            "builtin_provider_api_key": "sk-activated-after-expired-cache",
            "edition": "premium",
        },
    )

    state = LicenseRuntimeState(ttl_seconds=3600)

    initial_status = await state.get_status(db_session)
    code = "fresh-license-token"
    db_session.add(
        LicenseRecord(
            token_hash=compute_license_token_hash(code),
            license_token=code,
        )
    )
    await db_session.commit()

    refreshed_status = await state.get_status(db_session)

    assert initial_status.expired is True
    assert refreshed_status.expired is False
    assert refreshed_status.status == "active"
    assert refreshed_status.edition == "premium"
    assert settings.BUILTIN_PROVIDER_API_KEY == "sk-activated-after-expired-cache"
