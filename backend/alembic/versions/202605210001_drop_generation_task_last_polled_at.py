"""drop unused generation task last_polled_at

Revision ID: 202605210001
Revises: 202605180004
Create Date: 2026-05-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202605210001"
down_revision: str | None = "202605180004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.drop_column("last_polled_at")


def downgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.add_column(sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True))
