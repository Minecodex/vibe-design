"""add usage log billing key

Revision ID: 202605170004
Revises: 202605170003
Create Date: 2026-05-17 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605170004"
down_revision: Union[str, None] = "202605170003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usage_logs") as batch_op:
        batch_op.add_column(sa.Column("billing_key", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_usage_logs_billing_key", ["billing_key"])


def downgrade() -> None:
    with op.batch_alter_table("usage_logs") as batch_op:
        batch_op.drop_constraint("uq_usage_logs_billing_key", type_="unique")
        batch_op.drop_column("billing_key")
