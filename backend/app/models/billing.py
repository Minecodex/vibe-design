from datetime import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_usage_logs_task_id"),
        UniqueConstraint("billing_key", name="uq_usage_logs_billing_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("usage_logs.id"), index=True, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("generation_tasks.id"), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_label: Mapped[str] = mapped_column(String(100), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    billing_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_cents_original: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billing_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    provider_code: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    provider_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_mode: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    billing_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billing_next_run_at: Mapped[dt | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    billing_locked_until: Mapped[dt | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_lock_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    billing_finalized_at: Mapped[dt | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
