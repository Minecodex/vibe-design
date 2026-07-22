from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference_gallery import ReferenceImage, ReferenceTaxonomy
from app.repositories.base_repository import BaseRepository


class ReferenceTaxonomyRepository(BaseRepository[ReferenceTaxonomy]):
    def __init__(self, db: AsyncSession):
        super().__init__(ReferenceTaxonomy, db)

    async def get_by_name(
        self,
        *,
        kind: str,
        name: str,
        exclude_id: int | None = None,
    ) -> ReferenceTaxonomy | None:
        stmt = select(ReferenceTaxonomy).where(
            ReferenceTaxonomy.kind == kind,
            func.lower(ReferenceTaxonomy.name) == name.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(ReferenceTaxonomy.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_kind(self, kind: str) -> list[ReferenceTaxonomy]:
        result = await self.db.execute(
            select(ReferenceTaxonomy)
            .where(ReferenceTaxonomy.kind == kind)
            .order_by(ReferenceTaxonomy.created_at.desc(), ReferenceTaxonomy.id.desc())
        )
        return list(result.scalars().all())

    async def count_images(self, taxonomy_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ReferenceImage.id)).where(
                or_(
                    ReferenceImage.category_id == taxonomy_id,
                    ReferenceImage.style_id == taxonomy_id,
                    ReferenceImage.classification_id == taxonomy_id,
                )
            )
        )
        return int(result.scalar_one() or 0)

    async def count_images_by_kind(self, kind: str) -> dict[int, int]:
        column = {
            "category": ReferenceImage.category_id,
            "style": ReferenceImage.style_id,
            "classification": ReferenceImage.classification_id,
        }.get(kind)
        if column is None:
            return {}
        result = await self.db.execute(
            select(column, func.count(ReferenceImage.id))
            .where(column.is_not(None))
            .group_by(column)
        )
        return {int(taxonomy_id): int(count) for taxonomy_id, count in result.all()}


class ReferenceImageRepository(BaseRepository[ReferenceImage]):
    def __init__(self, db: AsyncSession):
        super().__init__(ReferenceImage, db)

    async def get_with_taxonomies(self, image_id: int) -> ReferenceImage | None:
        result = await self.db.execute(
            select(ReferenceImage)
            .where(ReferenceImage.id == image_id)
            .options(
                selectinload(ReferenceImage.category),
                selectinload(ReferenceImage.style),
                selectinload(ReferenceImage.classification),
            )
        )
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        category_id: int | None = None,
        style_id: int | None = None,
        classification_id: int | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ReferenceImage]:
        stmt = (
            select(ReferenceImage)
            .options(
                selectinload(ReferenceImage.category),
                selectinload(ReferenceImage.style),
                selectinload(ReferenceImage.classification),
            )
            .order_by(ReferenceImage.created_at.desc(), ReferenceImage.id.desc())
            .offset(max(int(skip or 0), 0))
            .limit(max(int(limit or 1), 1))
        )
        if category_id:
            stmt = stmt.where(ReferenceImage.category_id == int(category_id))
        if style_id:
            stmt = stmt.where(ReferenceImage.style_id == int(style_id))
        if classification_id:
            stmt = stmt.where(ReferenceImage.classification_id == int(classification_id))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
