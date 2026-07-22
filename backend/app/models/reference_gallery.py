from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base_model import TimestampMixin


REFERENCE_TAXONOMY_KINDS = ("category", "style", "classification")


class ReferenceTaxonomy(TimestampMixin, Base):
    __tablename__ = "reference_taxonomies"
    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_reference_taxonomies_kind_name"),
        CheckConstraint(
            "kind IN ('category', 'style', 'classification')",
            name="ck_reference_taxonomies_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_images: Mapped[list["ReferenceImage"]] = relationship(
        back_populates="category",
        foreign_keys="ReferenceImage.category_id",
    )
    style_images: Mapped[list["ReferenceImage"]] = relationship(
        back_populates="style",
        foreign_keys="ReferenceImage.style_id",
    )
    classification_images: Mapped[list["ReferenceImage"]] = relationship(
        back_populates="classification",
        foreign_keys="ReferenceImage.classification_id",
    )


class ReferenceImage(TimestampMixin, Base):
    __tablename__ = "reference_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reference_taxonomies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    style_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reference_taxonomies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    classification_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reference_taxonomies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    category: Mapped[ReferenceTaxonomy] = relationship(
        back_populates="category_images",
        foreign_keys=[category_id],
    )
    style: Mapped[ReferenceTaxonomy | None] = relationship(
        back_populates="style_images",
        foreign_keys=[style_id],
    )
    classification: Mapped[ReferenceTaxonomy | None] = relationship(
        back_populates="classification_images",
        foreign_keys=[classification_id],
    )
