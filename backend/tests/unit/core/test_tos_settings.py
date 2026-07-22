from app.core.config import Settings


def test_fixed_settings_ignore_env_and_dotenv_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILTIN_PROVIDER_API_KEY", "env-provider-key")
    monkeypatch.setenv("BUILTIN_PROVIDER_CODE", "lingyaai")
    monkeypatch.setenv("BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN", "123")
    monkeypatch.setenv("LICENSE_ENVELOPE_KEY", "env-envelope-key")
    monkeypatch.setenv("DEPLOY_TYPE", "saas")

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "BUILTIN_PROVIDER_API_KEY=dotenv-provider-key",
                "BUILTIN_PROVIDER_CODE=apimart",
                "BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN=456",
                "LICENSE_ENVELOPE_KEY=dotenv-envelope-key",
                "DEPLOY_TYPE=private",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.BUILTIN_PROVIDER_API_KEY == ""
    assert settings.BUILTIN_PROVIDER_CODE == "apimart"
    assert settings.BUILTIN_PROVIDER_BILLING_UNIT_PER_YUAN == 500000
    assert settings.LICENSE_ENVELOPE_KEY == "kakjzzw123!@#"
    assert settings.DEPLOY_TYPE == "private"


def test_tos_settings_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("TOS_AK", "env-ak")
    monkeypatch.setenv("TOS_SK", "env-sk")
    monkeypatch.setenv("TOS_ENDPOINT", "env-endpoint")
    monkeypatch.setenv("TOS_REGION", "env-region")
    monkeypatch.setenv("TOS_BUCKET_NAME", "env-bucket")
    monkeypatch.setenv("TOS_PUBLIC_BASE_URL", "https://cdn.example.test")
    monkeypatch.setenv("TOS_OBJECT_PREFIX", "refs/")

    settings = Settings()

    assert settings.TOS_AK == "env-ak"
    assert settings.TOS_SK == "env-sk"
    assert settings.TOS_ENDPOINT == "env-endpoint"
    assert settings.TOS_REGION == "env-region"
    assert settings.TOS_BUCKET_NAME == "env-bucket"
    assert settings.TOS_PUBLIC_BASE_URL == "https://cdn.example.test"
    assert settings.TOS_OBJECT_PREFIX == "refs/"


def test_tos_settings_can_be_overridden_by_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("TOS_AK", raising=False)
    monkeypatch.delenv("TOS_SK", raising=False)
    monkeypatch.delenv("TOS_ENDPOINT", raising=False)
    monkeypatch.delenv("TOS_REGION", raising=False)
    monkeypatch.delenv("TOS_BUCKET_NAME", raising=False)
    monkeypatch.delenv("TOS_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TOS_OBJECT_PREFIX", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TOS_AK=dotenv-ak",
                "TOS_SK=dotenv-sk",
                "TOS_ENDPOINT=dotenv-endpoint",
                "TOS_REGION=dotenv-region",
                "TOS_BUCKET_NAME=dotenv-bucket",
                "TOS_PUBLIC_BASE_URL=https://dotenv-cdn.example.test",
                "TOS_OBJECT_PREFIX=dotenv-refs/",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.TOS_AK == "dotenv-ak"
    assert settings.TOS_SK == "dotenv-sk"
    assert settings.TOS_ENDPOINT == "dotenv-endpoint"
    assert settings.TOS_REGION == "dotenv-region"
    assert settings.TOS_BUCKET_NAME == "dotenv-bucket"
    assert settings.TOS_PUBLIC_BASE_URL == "https://dotenv-cdn.example.test"
    assert settings.TOS_OBJECT_PREFIX == "dotenv-refs/"


def test_tos_settings_default_to_empty_credentials(monkeypatch):
    for key in [
        "TOS_AK",
        "TOS_SK",
        "TOS_ENDPOINT",
        "TOS_REGION",
        "TOS_BUCKET_NAME",
        "TOS_PUBLIC_BASE_URL",
        "TOS_OBJECT_PREFIX",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.TOS_AK == ""
    assert settings.TOS_SK == ""
    assert settings.TOS_ENDPOINT == ""
    assert settings.TOS_REGION == ""
    assert settings.TOS_BUCKET_NAME == ""
    assert settings.TOS_PUBLIC_BASE_URL == ""
    assert settings.TOS_OBJECT_PREFIX == "generation-refs/"
