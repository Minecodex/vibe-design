from copy import deepcopy
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.core.datetime_utils import get_app_timezone

from app.api.deps import CurrentUser, DbSession
from app.core.providers import PROVIDER_REGISTRY, build_provider_registry
from app.models.provider import ProviderCredential, ProviderModel, UserProvider
from app.repositories.provider_repository import (
    ProviderCredentialRepository,
    ProviderModelRepository,
    UserProviderRepository,
)
from app.schemas.provider import (
    CredentialCreate,
    CredentialRead,
    CredentialUpdate,
    ModelCreate,
    ModelRead,
    ModelUpdate,
    ProviderStatus,
)

router = APIRouter(prefix="/providers", tags=["providers"])


def _mask_key(key: str) -> str:
    """Return first 2 and last 2 chars, mask the rest."""
    if len(key) <= 4:
        return "****"
    return key[:2] + "***" + key[-2:]


# ---------------------------------------------------------------------------
# Provider overview
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ProviderStatus])
async def list_providers(db: DbSession, current_user: CurrentUser):
    """Return all providers with status for the current user."""
    up_repo = UserProviderRepository(db)
    cred_repo = ProviderCredentialRepository(db)
    model_repo = ProviderModelRepository(db)
    provider_registry = build_provider_registry()

    installed = await up_repo.get_by_user(current_user.id)
    installed_codes = {p.provider_code for p in installed}

    result: list[ProviderStatus] = []
    for code, info in provider_registry.items():
        is_builtin = info.get("is_builtin", False)

        if is_builtin:
            # Built-in provider is always authorized and has all registry models
            registry_models = info.get("models", {})
            total_model_count = sum(len(v) for v in registry_models.values())
            result.append(
                ProviderStatus(
                    code=info["code"],
                    name=info["name"],
                    author=info["author"],
                    description=info["description"],
                    logo_url=info["logo_url"],
                    tags=info["tags"],
                    status="authorized",
                    credential_count=1,
                    model_count=total_model_count,
                    is_builtin=True,
                )
            )
            continue

        cred_count = await cred_repo.count_by_user_and_provider(current_user.id, code)
        model_count = await model_repo.count_by_user_and_provider(current_user.id, code)

        if code not in installed_codes:
            st = "installable"
        elif cred_count == 0:
            st = "unauthorized"
        else:
            st = "authorized"

        result.append(
            ProviderStatus(
                code=info["code"],
                name=info["name"],
                author=info["author"],
                description=info["description"],
                logo_url=info["logo_url"],
                tags=info["tags"],
                status=st,
                credential_count=cred_count,
                model_count=model_count,
            )
        )
    return result


def _inject_pricing(models: dict[str, list]) -> dict[str, list]:
    """Return model configs without mutating the registry structure."""
    return {
        model_type: [
            {**model, "config": deepcopy(model.get("config", {}))}
            if "config" in model
            else deepcopy(model)
            for model in model_list
        ]
        for model_type, model_list in models.items()
    }


@router.get("/registry")
async def get_provider_registry():
    """Return the static model registry (available models per provider).

    Builtin provider configs already include pricing and capability metadata.
    """
    return {
        code: {
            "models": _inject_pricing(info["models"]) if info.get("is_builtin") else info["models"],
            "credential_types": info.get("credential_types", ["ak_sk"]),
            "requires_endpoint": info.get("requires_endpoint", False),
            "is_builtin": info.get("is_builtin", False),
        }
        for code, info in build_provider_registry().items()
    }


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

@router.post("/{code}/install", status_code=status.HTTP_201_CREATED)
async def install_provider(code: str, db: DbSession, current_user: CurrentUser):
    if code not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if PROVIDER_REGISTRY[code].get("is_builtin"):
        raise HTTPException(status_code=403, detail="内置供应商无需安装")

    repo = UserProviderRepository(db)
    existing = await repo.get_by_user_and_code(current_user.id, code)
    if existing:
        raise HTTPException(status_code=400, detail="供应商已安装")

    up = UserProvider(user_id=current_user.id, provider_code=code)
    await repo.create(up)
    return {"message": "安装成功"}


@router.delete("/{code}/uninstall")
async def uninstall_provider(code: str, db: DbSession, current_user: CurrentUser):
    if PROVIDER_REGISTRY.get(code, {}).get("is_builtin"):
        raise HTTPException(status_code=403, detail="内置供应商无法卸载")
    repo = UserProviderRepository(db)
    existing = await repo.get_by_user_and_code(current_user.id, code)
    if not existing:
        raise HTTPException(status_code=404, detail="供应商未安装")
    await repo.update(existing, {"deleted_at": datetime.now(get_app_timezone())})
    return {"message": "卸载成功"}


# ---------------------------------------------------------------------------
# Credentials CRUD
# ---------------------------------------------------------------------------

@router.get("/{code}/credentials", response_model=list[CredentialRead])
async def list_credentials(code: str, db: DbSession, current_user: CurrentUser):
    repo = ProviderCredentialRepository(db)
    creds = await repo.get_by_user_and_provider(current_user.id, code)
    return [
        CredentialRead(
            id=c.id,
            provider_code=c.provider_code,
            name=c.name,
            access_key_hint=_mask_key(c.access_key),
            auth_type=c.auth_type,
        )
        for c in creds
    ]


@router.post("/{code}/credentials", response_model=CredentialRead, status_code=201)
async def create_credential(
    code: str,
    data: CredentialCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    if code not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if PROVIDER_REGISTRY[code].get("is_builtin"):
        raise HTTPException(status_code=403, detail="内置供应商无法修改凭据")

    # Auto-install provider if not yet installed
    up_repo = UserProviderRepository(db)
    existing = await up_repo.get_by_user_and_code(current_user.id, code)
    if not existing:
        up = UserProvider(user_id=current_user.id, provider_code=code)
        await up_repo.create(up)

    repo = ProviderCredentialRepository(db)
    cred = ProviderCredential(
        user_id=current_user.id,
        provider_code=code,
        name=data.name,
        access_key=data.access_key,
        secret_key=data.secret_key,
        auth_type=data.auth_type,
    )
    cred = await repo.create(cred)
    return CredentialRead(
        id=cred.id,
        provider_code=cred.provider_code,
        name=cred.name,
        access_key_hint=_mask_key(cred.access_key),
        auth_type=cred.auth_type,
    )


@router.put("/{code}/credentials/{cred_id}", response_model=CredentialRead)
async def update_credential(
    code: str,
    cred_id: int,
    data: CredentialUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    repo = ProviderCredentialRepository(db)
    cred = await repo.get(cred_id)
    if not cred or cred.user_id != current_user.id or cred.provider_code != code:
        raise HTTPException(status_code=404, detail="凭据不存在")

    update_data = data.model_dump(exclude_unset=True)
    cred = await repo.update(cred, update_data)
    return CredentialRead(
        id=cred.id,
        provider_code=cred.provider_code,
        name=cred.name,
        access_key_hint=_mask_key(cred.access_key),
        auth_type=cred.auth_type,
    )


@router.delete("/{code}/credentials/{cred_id}")
async def delete_credential(
    code: str,
    cred_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    repo = ProviderCredentialRepository(db)
    cred = await repo.get(cred_id)
    if not cred or cred.user_id != current_user.id or cred.provider_code != code:
        raise HTTPException(status_code=404, detail="凭据不存在")
    await repo.update(cred, {"deleted_at": datetime.now(get_app_timezone())})
    return {"message": "删除成功"}


# ---------------------------------------------------------------------------
# Models CRUD
# ---------------------------------------------------------------------------

@router.get("/{code}/models", response_model=list[ModelRead])
async def list_models(code: str, db: DbSession, current_user: CurrentUser):
    repo = ProviderModelRepository(db)
    models = await repo.get_by_user_and_provider(current_user.id, code)
    return [
        ModelRead(
            id=m.id,
            provider_code=m.provider_code,
            model_name=m.model_name,
            model_type=m.model_type,
            is_enabled=m.is_enabled,
            credential_id=m.credential_id,
            endpoint=m.endpoint,
        )
        for m in models
    ]


@router.post("/{code}/models", response_model=ModelRead, status_code=201)
async def create_model(
    code: str,
    data: ModelCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    if code not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if PROVIDER_REGISTRY[code].get("is_builtin"):
        raise HTTPException(status_code=403, detail="内置供应商无法修改模型")

    repo = ProviderModelRepository(db)
    model = ProviderModel(
        user_id=current_user.id,
        provider_code=code,
        model_name=data.model_name,
        model_type=data.model_type,
        credential_id=data.credential_id,
        endpoint=data.endpoint,
        is_enabled=True,
    )
    model = await repo.create(model)
    return ModelRead(
        id=model.id,
        provider_code=model.provider_code,
        model_name=model.model_name,
        model_type=model.model_type,
        is_enabled=model.is_enabled,
        credential_id=model.credential_id,
        endpoint=model.endpoint,
    )


@router.put("/{code}/models/{model_id}", response_model=ModelRead)
async def update_model(
    code: str,
    model_id: int,
    data: ModelUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    repo = ProviderModelRepository(db)
    model = await repo.get(model_id)
    if not model or model.user_id != current_user.id or model.provider_code != code:
        raise HTTPException(status_code=404, detail="模型不存在")

    update_data = data.model_dump(exclude_unset=True)
    model = await repo.update(model, update_data)
    return ModelRead(
        id=model.id,
        provider_code=model.provider_code,
        model_name=model.model_name,
        model_type=model.model_type,
        is_enabled=model.is_enabled,
        credential_id=model.credential_id,
        endpoint=model.endpoint,
    )


@router.delete("/{code}/models/{model_id}")
async def delete_model(
    code: str,
    model_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    repo = ProviderModelRepository(db)
    model = await repo.get(model_id)
    if not model or model.user_id != current_user.id or model.provider_code != code:
        raise HTTPException(status_code=404, detail="模型不存在")
    await repo.update(model, {"deleted_at": datetime.now(get_app_timezone())})
    return {"message": "删除成功"}
