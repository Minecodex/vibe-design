from pydantic import BaseModel


# ---------- Provider overview ----------

class ProviderInfo(BaseModel):
    """Static provider metadata (not from DB)."""
    code: str
    name: str
    author: str
    description: str
    logo_url: str
    tags: list[str]


class ProviderStatus(ProviderInfo):
    """Provider metadata + dynamic status for the current user."""
    status: str  # installable | unauthorized | authorized
    credential_count: int = 0
    model_count: int = 0
    is_builtin: bool = False


# ---------- Credentials ----------

class CredentialCreate(BaseModel):
    name: str
    access_key: str
    secret_key: str = ""
    auth_type: str = "ak_sk"  # "ak_sk" or "api_key"


class CredentialUpdate(BaseModel):
    name: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    auth_type: str | None = None


class CredentialRead(BaseModel):
    id: int
    provider_code: str
    name: str
    access_key_hint: str  # masked, e.g. "ak***89"
    auth_type: str = "ak_sk"

    model_config = {"from_attributes": True}


# ---------- Models ----------

class ModelCreate(BaseModel):
    model_name: str
    model_type: str  # text2image | text2video
    credential_id: int | None = None
    endpoint: str | None = None


class ModelUpdate(BaseModel):
    is_enabled: bool | None = None
    credential_id: int | None = None


class ModelRead(BaseModel):
    id: int
    provider_code: str
    model_name: str
    model_type: str
    is_enabled: bool
    credential_id: int | None = None
    endpoint: str | None = None

    model_config = {"from_attributes": True}
