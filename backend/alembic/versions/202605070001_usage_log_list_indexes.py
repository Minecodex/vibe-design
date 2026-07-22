"""add usage log list indexes

Revision ID: 202605070001
Revises: 202603250001
Create Date: 2026-05-07 17:55:00.000000
"""

from alembic import op


revision = "202605070001"
down_revision = "202603250001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_usage_logs_user_parent_created_at",
        "usage_logs",
        ["user_id", "parent_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_logs_parent_created_at",
        "usage_logs",
        ["parent_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_logs_parent_created_at", table_name="usage_logs")
    op.drop_index("ix_usage_logs_user_parent_created_at", table_name="usage_logs")
