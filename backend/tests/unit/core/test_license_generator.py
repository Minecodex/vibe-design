from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings
from app.core.license import compute_license_token_hash, verify_license_code
from app.core.license_generator import generate_license_code


def test_generate_license_code_produces_verifiable_token(monkeypatch):
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
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "unit-test-license-envelope-key")

    expires_at = datetime.now(UTC) + timedelta(days=14)
    builtin_provider_api_key = "sk-generated-license"

    code = generate_license_code(
        private_key=private_key,
        expires_at=expires_at,
        builtin_provider_api_key=builtin_provider_api_key,
        edition="flagship",
    )
    data = verify_license_code(code)

    assert data["expires_at"] == expires_at
    assert data["builtin_provider_api_key"] == builtin_provider_api_key
    assert data["edition"] == "flagship"


def test_compute_license_token_hash_is_stable():
    token = "sample-license-token"

    assert compute_license_token_hash(token) == compute_license_token_hash(token)
