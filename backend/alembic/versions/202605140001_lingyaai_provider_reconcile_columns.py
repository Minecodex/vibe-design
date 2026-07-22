"""lingyaai provider reconcile columns

Revision ID: 202605140001
Revises: 202605130001
Create Date: 2026-05-14 00:01:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202605140001"
down_revision = "202605130001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_logs", sa.Column("provider_code", sa.String(length=50), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_request_id", sa.String(length=128), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_trace_id", sa.String(length=128), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_task_id", sa.String(length=255), nullable=True))
    op.add_column("usage_logs", sa.Column("billing_mode", sa.String(length=50), nullable=True))
    op.add_column("usage_logs", sa.Column("billing_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usage_logs", sa.Column("billing_next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usage_logs", sa.Column("billing_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usage_logs", sa.Column("billing_lock_token", sa.String(length=64), nullable=True))
    op.add_column("usage_logs", sa.Column("billing_finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_quota", sa.Integer(), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("usage_logs", sa.Column("provider_completion_tokens", sa.Integer(), nullable=True))

    op.create_index(
        "ix_usage_logs_provider_reconcile_due",
        "usage_logs",
        ["provider_code", "billing_mode", "status", "billing_next_run_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_logs_provider_request",
        "usage_logs",
        ["provider_code", "provider_request_id"],
        unique=False,
    )
    op.create_index("ix_usage_logs_billing_lock_token", "usage_logs", ["billing_lock_token"], unique=False)

    op.add_column("generation_tasks", sa.Column("builtin_provider_code", sa.String(length=50), nullable=True))
    op.add_column("generation_tasks", sa.Column("provider_request_id", sa.String(length=128), nullable=True))
    op.add_column("generation_tasks", sa.Column("provider_trace_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_tasks", "provider_trace_id")
    op.drop_column("generation_tasks", "provider_request_id")
    op.drop_column("generation_tasks", "builtin_provider_code")

    op.drop_index("ix_usage_logs_billing_lock_token", table_name="usage_logs")
    op.drop_index("ix_usage_logs_provider_request", table_name="usage_logs")
    op.drop_index("ix_usage_logs_provider_reconcile_due", table_name="usage_logs")
    op.drop_column("usage_logs", "provider_completion_tokens")
    op.drop_column("usage_logs", "provider_prompt_tokens")
    op.drop_column("usage_logs", "provider_quota")
    op.drop_column("usage_logs", "billing_finalized_at")
    op.drop_column("usage_logs", "billing_lock_token")
    op.drop_column("usage_logs", "billing_locked_until")
    op.drop_column("usage_logs", "billing_next_run_at")
    op.drop_column("usage_logs", "billing_attempt_count")
    op.drop_column("usage_logs", "billing_mode")
    op.drop_column("usage_logs", "provider_task_id")
    op.drop_column("usage_logs", "provider_trace_id")
    op.drop_column("usage_logs", "provider_request_id")
    op.drop_column("usage_logs", "provider_code")
