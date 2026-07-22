from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_model import TimestampMixin


class PhotoshopEditJob(TimestampMixin, Base):
    __tablename__ = "photoshop_edit_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_canvas_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    svg_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default="pending")
    claimed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_canvas_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

