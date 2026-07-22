"""create provider operations queue

Revision ID: 202605220001
Revises: 202605210002
Create Date: 2026-05-22 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202605220001"
down_revision: str | None = "202605210002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generation_task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("operation_key", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("rate_limited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generation_task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generation_task_id",
            "operation",
            "operation_key",
            name="uq_provider_operations_task_operation_key",
        ),
    )
    op.create_index(
        "ix_provider_operations_due",
        "provider_operations",
        ["status", "due_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_provider_operations_task_status",
        "provider_operations",
        ["generation_task_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_operations_task_status", table_name="provider_operations")
    op.drop_index("ix_provider_operations_due", table_name="provider_operations")
    op.drop_table("provider_operations")
