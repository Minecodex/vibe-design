"""Drop harness_conversations.runtime_version (v1 compat removed).

All harness conversations now run the presentation_v2 protocol; the
``runtime_version`` discriminator and its v1 read-only/degradation paths have
been removed from the codebase, so the column is no longer read or written.

Revision ID: 202606090001
Revises: 202606080001
Create Date: 2026-06-09 06:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606090001"
down_revision = "202606080001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("harness_conversations") as batch_op:
        batch_op.drop_column("runtime_version")


def downgrade() -> None:
    with op.batch_alter_table("harness_conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "runtime_version",
                sa.String(length=20),
                nullable=False,
                server_default="v2",
            )
        )
