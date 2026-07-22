"""Default harness conversations to runtime v2.

Revision ID: 202606080001
Revises: 202606070001
Create Date: 2026-06-08 19:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606080001"
down_revision = "202606070001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("harness_conversations") as batch_op:
        batch_op.alter_column(
            "runtime_version",
            existing_type=sa.String(length=20),
            nullable=False,
            server_default="v2",
        )


def downgrade() -> None:
    with op.batch_alter_table("harness_conversations") as batch_op:
        batch_op.alter_column(
            "runtime_version",
            existing_type=sa.String(length=20),
            nullable=False,
            server_default="v1",
        )
