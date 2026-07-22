from sqlalchemy import Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_model import TimestampMixin


class ProjectUserCanvas(TimestampMixin, Base):
    """Stores a single user's private canvas within a shared project."""

    __tablename__ = "project_user_canvases"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_user_canvases_project_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    canvas_data: Mapped[list | None] = mapped_column(JSON, nullable=True)
    canvas_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    canvas_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
