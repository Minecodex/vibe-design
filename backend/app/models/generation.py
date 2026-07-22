from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_model import TimestampMixin


class GenerationTask(TimestampMixin, Base):
    """Tracks an async AI generation task (image or video)."""

    __tablename__ = "generation_tasks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "task_type",
            "client_request_id",
            name="uq_generation_tasks_client_request",
        ),
        Index(
            "ix_generation_tasks_project_client_request_id",
            "project_id",
            "client_request_id",
        ),
        Index(
            "ix_generation_tasks_scheduler_due",
            "status",
            "scheduler_next_run_at",
            "created_at",
            "id",
            "scheduler_lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # text2image | text2video | image2video
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    apimart_credential_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_apimart_credentials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending | processing | completed | failed
    client_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    builtin_provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scheduler_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scheduler_claimed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduler_lease_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduler_next_run_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduler_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    terminalized_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_side_effects_finalized_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_urls: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 0-100
