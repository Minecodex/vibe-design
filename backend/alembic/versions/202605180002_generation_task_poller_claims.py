"""add generation task poller claim columns

Revision ID: 202605180002
Revises: 202605180001
Create Date: 2026-05-18 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605180002"
down_revision: Union[str, None] = "202605180001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.add_column(sa.Column("poller_claim_token", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("poller_claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("poller_lease_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.drop_column("poller_lease_expires_at")
        batch_op.drop_column("poller_claimed_at")
        batch_op.drop_column("poller_claim_token")
