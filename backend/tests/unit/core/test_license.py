import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import app.core.license as license_core


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _encrypt_signed_payload(private_key, payload: dict, *, envelope_key: str, version: int = 2) -> str:
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
    aesgcm = AESGCM(hashlib.sha256(envelope_key.encode()).digest())
    nonce = os.urandom(12)
    return _b64url_encode(nonce + aesgcm.encrypt(nonce, envelope_bytes, None))


@pytest.fixture
def rsa_keypair(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(
        license_core.settings,
        "REDEMPTION_PUBLIC_KEY",
        public_pem.decode().replace("\n", "\\n"),
    )
    monkeypatch.setattr(
        license_core.settings,
        "LICENSE_ENVELOPE_KEY",
        "unit-test-license-envelope-key",
    )
    return private_key


def test_verify_license_code_returns_expiration_and_builtin_provider_api_key(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    builtin_provider_api_key = "sk-runtime-test-key"
    edition = "flagship"
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": builtin_provider_api_key,
            "edition": edition,
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    data = license_core.verify_license_code(code)

    assert data["expires_at"] == expires_at
    assert data["builtin_provider_api_key"] == builtin_provider_api_key
    assert data["edition"] == edition
    assert data["builtin_provider_code"] == "apimart"
    assert data["billing_unit_per_yuan"] == 500000


def test_verify_license_code_returns_builtin_provider_code_and_billing_unit(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-lingyaai",
            "builtin_provider_code": "lingyaai",
            "billing_unit_per_yuan": 250000,
            "edition": "flagship",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    data = license_core.verify_license_code(code)

    assert data["builtin_provider_code"] == "lingyaai"
    assert data["billing_unit_per_yuan"] == 250000


def test_verify_license_code_rejects_tampered_outer_ciphertext(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-outer-tamper",
            "edition": "flagship",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    raw = bytearray(_b64url_decode(code))
    raw[-1] ^= 0x01

    with pytest.raises(ValueError, match="license code decryption failed"):
        license_core.verify_license_code(_b64url_encode(bytes(raw)))


def test_verify_license_code_rejects_invalid_signature(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-inner-tamper",
            "edition": "flagship",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )
    raw = _b64url_decode(code)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(hashlib.sha256(license_core.settings.LICENSE_ENVELOPE_KEY.encode()).digest())
    envelope = json.loads(aesgcm.decrypt(nonce, ciphertext, None).decode())
    envelope["signature"] = _b64url_encode(b"bad-signature")
    tampered_code = _b64url_encode(
        nonce + aesgcm.encrypt(nonce, json.dumps(envelope, separators=(",", ":")).encode(), None)
    )

    with pytest.raises(ValueError, match="license code is invalid"):
        license_core.verify_license_code(tampered_code)


def test_verify_license_code_rejects_invalid_expiration_format(rsa_keypair):
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": "not-a-datetime",
            "builtin_provider_api_key": "sk-invalid-expiration",
            "edition": "flagship",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    with pytest.raises(ValueError, match="expiration is invalid"):
        license_core.verify_license_code(code)


def test_verify_license_code_rejects_legacy_v1_license(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-legacy",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
        version=1,
    )

    with pytest.raises(ValueError, match="legacy license versions are no longer supported"):
        license_core.verify_license_code(code)


def test_verify_license_code_rejects_missing_edition(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-missing-edition",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    with pytest.raises(ValueError, match="license code is invalid"):
        license_core.verify_license_code(code)


def test_verify_license_code_rejects_unknown_edition(rsa_keypair):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    code = _encrypt_signed_payload(
        rsa_keypair,
        {
            "expires_at": expires_at.isoformat(),
            "builtin_provider_api_key": "sk-unknown-edition",
            "edition": "enterprise",
        },
        envelope_key=license_core.settings.LICENSE_ENVELOPE_KEY,
    )

    with pytest.raises(ValueError, match="license code is invalid"):
        license_core.verify_license_code(code)
