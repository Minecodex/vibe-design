from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.reference_gallery import ReferenceImage, ReferenceTaxonomy
from app.models.user import User
from app.repositories.reference_gallery_repository import (
    ReferenceImageRepository,
    ReferenceTaxonomyRepository,
)


@pytest.fixture(autouse=True)
def _saas_deploy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")


async def _create_user(db_session: AsyncSession, suffix: str, *, role: str = "admin") -> User:
    user = User(
        email=f"reference-gallery-{role}-{suffix}@example.com",
        username=f"rg_{role}_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth(client: AsyncClient, user: User) -> None:
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"


async def _seed_taxonomy(
    db_session: AsyncSession,
    user: User,
    *,
    kind: str = "category",
    name: str | None = None,
    prompt: str | None = None,
) -> ReferenceTaxonomy:
    taxonomy = await ReferenceTaxonomyRepository(db_session).create(
        ReferenceTaxonomy(
            created_by=user.id,
            kind=kind,
            name=name or f"{kind}-{user.id}",
            prompt=prompt,
        )
    )
    return taxonomy


async def test_reference_gallery_taxonomy_crud_and_prompt_rules(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_user(db_session, "crud")
    _auth(client, admin)

    category_response = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "category", "name": "服装-crud"},
    )
    assert category_response.status_code == 200, category_response.text
    category = category_response.json()
    assert category["kind"] == "category"
    assert category["prompt"] is None

    style_missing_prompt = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "style", "name": "平铺"},
    )
    assert style_missing_prompt.status_code == 400
    assert "提示词" in style_missing_prompt.json()["detail"]

    style_response = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "style", "name": "平铺", "prompt": "flat lay lighting"},
    )
    assert style_response.status_code == 200, style_response.text
    style = style_response.json()
    assert style["prompt"] == "flat lay lighting"

    same_name_other_kind = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "classification", "name": "平铺", "prompt": "classification prompt"},
    )
    assert same_name_other_kind.status_code == 200, same_name_other_kind.text

    duplicate_style = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "style", "name": "平铺", "prompt": "again"},
    )
    assert duplicate_style.status_code == 409

    rename_response = await client.patch(
        f"/api/v1/reference-gallery/taxonomies/{style['id']}",
        json={"name": "平铺风格", "prompt": "updated prompt"},
    )
    assert rename_response.status_code == 200, rename_response.text
    assert rename_response.json()["name"] == "平铺风格"
    assert rename_response.json()["prompt"] == "updated prompt"

    list_response = await client.get(
        "/api/v1/reference-gallery/taxonomies",
        params={"kind": "style"},
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["name"] for item in list_response.json()] == ["平铺风格"]

    delete_response = await client.delete(f"/api/v1/reference-gallery/taxonomies/{style['id']}")
    assert delete_response.status_code == 200, delete_response.text


async def test_reference_gallery_blocks_deleting_referenced_taxonomies(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_user(db_session, "delete-block")
    _auth(client, admin)
    category = await _seed_taxonomy(db_session, admin, kind="category", name="服装")
    style = await _seed_taxonomy(db_session, admin, kind="style", name="挂拍", prompt="style")
    classification = await _seed_taxonomy(
        db_session,
        admin,
        kind="classification",
        name="主图",
        prompt="class",
    )
    await ReferenceImageRepository(db_session).create(
        ReferenceImage(
            created_by=admin.id,
            category_id=category.id,
            style_id=style.id,
            classification_id=classification.id,
            url="/api/v1/uploads/reference-gallery/2026-06/sample.png",
            name="sample.png",
        )
    )

    for taxonomy in (category, style, classification):
        response = await client.delete(f"/api/v1/reference-gallery/taxonomies/{taxonomy.id}")
        assert response.status_code == 409
        assert "已有图片" in response.json()["detail"]


async def test_reference_gallery_images_filter_and_read_permission(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_user(db_session, "read-admin")
    reader = await _create_user(db_session, "read-user", role="user")
    category = await _seed_taxonomy(db_session, admin, kind="category", name="鞋履-read")
    other_category = await _seed_taxonomy(db_session, admin, kind="category", name="箱包-read")
    style = await _seed_taxonomy(db_session, admin, kind="style", name="平铺-read", prompt="style")
    classification = await _seed_taxonomy(
        db_session,
        admin,
        kind="classification",
        name="主图-read",
        prompt="class",
    )
    await ReferenceImageRepository(db_session).create(
        ReferenceImage(
            created_by=admin.id,
            category_id=category.id,
            style_id=style.id,
            classification_id=classification.id,
            url="/api/v1/uploads/reference-gallery/2026-06/shoe.png",
            name="shoe.png",
        )
    )
    await ReferenceImageRepository(db_session).create(
        ReferenceImage(
            created_by=admin.id,
            category_id=other_category.id,
            url="/api/v1/uploads/reference-gallery/2026-06/bag.png",
            name="bag.png",
        )
    )

    _auth(client, reader)
    read_response = await client.get(
        "/api/v1/reference-gallery/images",
        params={
            "category_id": category.id,
            "style_id": style.id,
            "classification_id": classification.id,
        },
    )
    assert read_response.status_code == 200, read_response.text
    items = read_response.json()
    assert [item["name"] for item in items] == ["shoe.png"]
    assert items[0]["category_name"] == "鞋履-read"
    assert items[0]["style_name"] == "平铺-read"
    assert items[0]["classification_name"] == "主图-read"

    write_response = await client.post(
        "/api/v1/reference-gallery/taxonomies",
        json={"kind": "category", "name": "无权限"},
    )
    assert write_response.status_code == 403


async def test_reference_gallery_admin_can_update_image_taxonomies(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_user(db_session, "move-image")
    source_category = await _seed_taxonomy(db_session, admin, kind="category", name="原类目")
    target_category = await _seed_taxonomy(db_session, admin, kind="category", name="目标类目")
    style = await _seed_taxonomy(db_session, admin, kind="style", name="风格", prompt="style")
    classification = await _seed_taxonomy(
        db_session,
        admin,
        kind="classification",
        name="分类",
        prompt="class",
    )
    image = await ReferenceImageRepository(db_session).create(
        ReferenceImage(
            created_by=admin.id,
            category_id=source_category.id,
            style_id=style.id,
            classification_id=classification.id,
            url="/api/v1/uploads/reference-gallery/2026-06/move.png",
            name="move.png",
        )
    )
    _auth(client, admin)

    update_response = await client.patch(
        f"/api/v1/reference-gallery/images/{image.id}",
        json={
            "category_id": target_category.id,
            "style_id": None,
            "classification_id": None,
        },
    )

    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["category_id"] == target_category.id
    assert updated["style_id"] is None
    assert updated["classification_id"] is None
    assert updated["category_name"] == "目标类目"

    source_response = await client.get(
        "/api/v1/reference-gallery/images",
        params={"category_id": source_category.id},
    )
    assert source_response.status_code == 200, source_response.text
    assert source_response.json() == []

    target_response = await client.get(
        "/api/v1/reference-gallery/images",
        params={"category_id": target_category.id},
    )
    assert target_response.status_code == 200, target_response.text
    assert [item["id"] for item in target_response.json()] == [image.id]


async def test_reference_gallery_upload_requires_category_with_optional_taxonomies(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    admin = await _create_user(db_session, "upload")
    category = await _seed_taxonomy(db_session, admin, kind="category", name="上传类目")
    style = await _seed_taxonomy(db_session, admin, kind="style", name="上传风格", prompt="style")
    classification = await _seed_taxonomy(
        db_session,
        admin,
        kind="classification",
        name="上传分类",
        prompt="class",
    )
    _auth(client, admin)

    monkeypatch.setattr(
        "app.api.v1.endpoints.reference_gallery.verify_image_file",
        lambda *_args, **_kwargs: None,
    )

    from app.services.reference_gallery_uploads import build_reference_gallery_upload

    monkeypatch.setattr(
        "app.api.v1.endpoints.reference_gallery.build_reference_gallery_upload",
        lambda filename: build_reference_gallery_upload(filename, root=tmp_path / "reference-gallery"),
    )

    missing = await client.post(
        "/api/v1/reference-gallery/uploads",
        files=[("files", ("missing.png", b"fake-image", "image/png"))],
    )
    assert missing.status_code == 422

    wrong_kind = await client.post(
        "/api/v1/reference-gallery/uploads",
        params={"category_id": style.id},
        files=[("files", ("wrong.png", b"fake-image", "image/png"))],
    )
    assert wrong_kind.status_code == 400
    assert "类型不匹配" in wrong_kind.json()["detail"]

    uploaded = await client.post(
        "/api/v1/reference-gallery/uploads",
        params={
            "category_id": category.id,
            "style_id": style.id,
            "classification_id": classification.id,
        },
        files=[("files", ("bound.png", b"fake-image", "image/png"))],
    )

    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()[0]
    assert item["name"] == "bound.png"
    assert item["category_id"] == category.id
    assert item["style_id"] == style.id
    assert item["classification_id"] == classification.id
