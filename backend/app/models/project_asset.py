from sqlalchemy import Integer, String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.base_model import TimestampMixin
from app.models.user import User


class ProjectAsset(TimestampMixin, Base):
    """Assets synced from canvas media items into the Asset Library."""

    __tablename__ = "project_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "canvas_item_id", name="uq_project_assets_project_user_canvas_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # image | video
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canvas_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship("User", foreign_keys=[user_id])


class UserAssetFavorite(TimestampMixin, Base):
    """Tracks which user has favorited which asset in the Asset Library."""

    __tablename__ = "user_asset_favorites"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_assets.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
