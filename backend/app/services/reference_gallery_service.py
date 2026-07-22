from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference_gallery import REFERENCE_TAXONOMY_KINDS, ReferenceImage, ReferenceTaxonomy
from app.repositories.reference_gallery_repository import (
    ReferenceImageRepository,
    ReferenceTaxonomyRepository,
)
from app.services.asset_preview_service import asset_preview_service

_UNSET = object()


class ReferenceGalleryError(ValueError):
    pass


class ReferenceGalleryConflictError(ReferenceGalleryError):
    pass


class ReferenceGalleryNotFoundError(ReferenceGalleryError):
    pass


def _clean_name(name: str, *, field: str = "名称", max_length: int = 128) -> str:
    value = str(name or "").strip()
    if not value:
        raise ReferenceGalleryError(f"{field}不能为空")
    if len(value) > max_length:
        raise ReferenceGalleryError(f"{field}不能超过 {max_length} 个字符")
    return value


def _clean_prompt(prompt: str | None, *, required: bool) -> str | None:
    value = str(prompt or "").strip()
    if required and not value:
        raise ReferenceGalleryError("提示词不能为空")
    return value or None


def _validate_kind(kind: str) -> str:
    value = str(kind or "").strip()
    if value not in REFERENCE_TAXONOMY_KINDS:
        raise ReferenceGalleryError("无效的分类类型")
    return value


class ReferenceGalleryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.taxonomies = ReferenceTaxonomyRepository(db)
        self.images = ReferenceImageRepository(db)

    async def list_taxonomies(self, *, kind: str) -> list[dict]:
        clean_kind = _validate_kind(kind)
        taxonomies = await self.taxonomies.list_by_kind(clean_kind)
        counts = await self.taxonomies.count_images_by_kind(clean_kind)
        return [
            {
                "id": taxonomy.id,
                "kind": taxonomy.kind,
                "name": taxonomy.name,
                "prompt": taxonomy.prompt,
                "image_count": int(counts.get(taxonomy.id, 0)),
                "created_at": taxonomy.created_at,
                "updated_at": taxonomy.updated_at,
            }
            for taxonomy in taxonomies
        ]

    async def create_taxonomy(
        self,
        *,
        user_id: int,
        kind: str,
        name: str,
        prompt: str | None = None,
    ) -> ReferenceTaxonomy:
        clean_kind = _validate_kind(kind)
        clean_name = _clean_name(name, field=self._kind_label(clean_kind))
        clean_prompt = _clean_prompt(prompt, required=clean_kind != "category")
        if await self.taxonomies.get_by_name(kind=clean_kind, name=clean_name):
            raise ReferenceGalleryConflictError(f"{self._kind_label(clean_kind)}已存在")
        return await self.taxonomies.create(
            ReferenceTaxonomy(
                created_by=user_id,
                kind=clean_kind,
                name=clean_name,
                prompt=clean_prompt,
            )
        )

    async def update_taxonomy(
        self,
        taxonomy_id: int,
        *,
        name: str | None = None,
        prompt: str | None = None,
    ) -> ReferenceTaxonomy:
        taxonomy = await self.taxonomies.get(taxonomy_id)
        if taxonomy is None:
            raise ReferenceGalleryNotFoundError("分类不存在")
        data: dict = {}
        if name is not None:
            clean_name = _clean_name(name, field=self._kind_label(taxonomy.kind))
            if await self.taxonomies.get_by_name(
                kind=taxonomy.kind,
                name=clean_name,
                exclude_id=taxonomy.id,
            ):
                raise ReferenceGalleryConflictError(f"{self._kind_label(taxonomy.kind)}已存在")
            data["name"] = clean_name
        if prompt is not None:
            data["prompt"] = _clean_prompt(prompt, required=taxonomy.kind != "category")
        elif taxonomy.kind != "category" and not taxonomy.prompt:
            raise ReferenceGalleryError("提示词不能为空")
        if data:
            return await self.taxonomies.update(taxonomy, data)
        return taxonomy

    async def delete_taxonomy(self, taxonomy_id: int) -> None:
        taxonomy = await self.taxonomies.get(taxonomy_id)
        if taxonomy is None:
            raise ReferenceGalleryNotFoundError("分类不存在")
        if await self.taxonomies.count_images(taxonomy.id) > 0:
            raise ReferenceGalleryConflictError(f"当前{self._kind_label(taxonomy.kind)}下已有图片，不能删除")
        await self.taxonomies.delete(taxonomy)

    async def list_images(
        self,
        *,
        category_id: int | None = None,
        style_id: int | None = None,
        classification_id: int | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        images = await self.images.list_filtered(
            category_id=category_id,
            style_id=style_id,
            classification_id=classification_id,
            skip=skip,
            limit=limit,
        )
        return [await self.serialize_image(image) for image in images]

    async def create_image(
        self,
        *,
        user_id: int,
        url: str,
        name: str,
        category_id: int,
        style_id: int | None = None,
        classification_id: int | None = None,
    ) -> dict:
        category = await self._get_taxonomy_for_kind(category_id, "category")
        style = await self._get_optional_taxonomy_for_kind(style_id, "style")
        classification = await self._get_optional_taxonomy_for_kind(
            classification_id,
            "classification",
        )
        clean_name = str(name or "").strip()[:512]
        image = await self.images.create(
            ReferenceImage(
                created_by=user_id,
                url=str(url or "").strip(),
                name=clean_name,
                category_id=category.id,
                style_id=style.id if style else None,
                classification_id=classification.id if classification else None,
            )
        )
        image = await self.images.get_with_taxonomies(image.id)
        if image is None:
            raise ReferenceGalleryNotFoundError("图片不存在")
        return await self.serialize_image(image)

    async def update_image(
        self,
        image_id: int,
        *,
        name: str | None | object = _UNSET,
        category_id: int | None | object = _UNSET,
        style_id: int | None | object = _UNSET,
        classification_id: int | None | object = _UNSET,
    ) -> dict:
        image = await self.images.get(image_id)
        if image is None:
            raise ReferenceGalleryNotFoundError("图片不存在")
        data: dict = {}
        if name is not _UNSET:
            data["name"] = str(name or "").strip()[:512]
        if category_id is not _UNSET:
            if category_id is None:
                raise ReferenceGalleryError("类目不能为空")
            category = await self._get_taxonomy_for_kind(category_id, "category")
            data["category_id"] = category.id
        if style_id is not _UNSET:
            style = await self._get_optional_taxonomy_for_kind(style_id, "style")
            data["style_id"] = style.id if style else None
        if classification_id is not _UNSET:
            classification = await self._get_optional_taxonomy_for_kind(
                classification_id,
                "classification",
            )
            data["classification_id"] = classification.id if classification else None
        if data:
            await self.images.update(image, data)
        refreshed = await self.images.get_with_taxonomies(image.id)
        if refreshed is None:
            raise ReferenceGalleryNotFoundError("图片不存在")
        return await self.serialize_image(refreshed)

    async def delete_image(self, image_id: int) -> None:
        image = await self.images.get(image_id)
        if image is None:
            raise ReferenceGalleryNotFoundError("图片不存在")
        await self.images.delete(image)

    async def serialize_image(self, image: ReferenceImage) -> dict:
        preview = await asset_preview_service.get_list_preview(
            asset_id=f"reference-gallery:{image.id}",
            user_id=image.created_by,
            asset_type="image",
            asset_url=image.url,
        )
        return {
            "id": image.id,
            "url": image.url,
            "name": image.name,
            "category_id": image.category.id if image.category else image.category_id,
            "category_name": image.category.name if image.category else "",
            "style_id": image.style.id if image.style else None,
            "style_name": image.style.name if image.style else None,
            "style_prompt": image.style.prompt if image.style else None,
            "classification_id": image.classification.id if image.classification else None,
            "classification_name": image.classification.name if image.classification else None,
            "classification_prompt": image.classification.prompt if image.classification else None,
            "list_preview_url": preview.url,
            "list_preview_status": preview.status,
            "created_at": image.created_at,
            "updated_at": image.updated_at,
        }

    async def _get_taxonomy_for_kind(self, taxonomy_id: int, kind: str) -> ReferenceTaxonomy:
        taxonomy = await self.taxonomies.get(taxonomy_id)
        if taxonomy is None:
            raise ReferenceGalleryNotFoundError(f"{self._kind_label(kind)}不存在")
        if taxonomy.kind != kind:
            raise ReferenceGalleryError(f"所选{self._kind_label(kind)}类型不匹配")
        return taxonomy

    async def _get_optional_taxonomy_for_kind(
        self,
        taxonomy_id: int | None,
        kind: str,
    ) -> ReferenceTaxonomy | None:
        if taxonomy_id is None:
            return None
        return await self._get_taxonomy_for_kind(taxonomy_id, kind)

    @staticmethod
    def _kind_label(kind: str) -> str:
        return {
            "category": "类目名称",
            "style": "图片风格",
            "classification": "图片分类",
        }.get(kind, "分类")
