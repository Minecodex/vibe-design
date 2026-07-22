from sqlalchemy import Integer, String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.base_model import TimestampMixin, SoftDeleteMixin


class Project(TimestampMixin, SoftDeleteMixin, Base):
    """User project — each project maps to a canvas."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    
    # Share settings
    share_token: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    share_permission: Mapped[str | None] = mapped_column(String(50), nullable=True) # e.g., 'view', 'edit' (or None if disabled)
    share_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    share_expiration: Mapped[int | None] = mapped_column(Integer, nullable=True) # Expiration timestamp or days or strict date
