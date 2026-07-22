from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_model import TimestampMixin


class ProviderOperation(TimestampMixin, Base):
    """Durable queue item for one external provider operation."""

    __tablename__ = "provider_operations"
    __table_args__ = (
        UniqueConstraint(
            "generation_task_id",
            "operation",
            "operation_key",
            name="uq_provider_operations_task_operation_key",
        ),
        Index(
            "ix_provider_operations_due",
            "status",
            "due_at",
            "lease_expires_at",
        ),
        Index(
            "ix_provider_operations_task_status",
            "generation_task_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    generation_task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="background")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    due_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limited_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
