"""add harness run owner protocol fields

Revision ID: 202605170001
Revises: 202605160003
Create Date: 2026-05-17 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605170001"
down_revision: Union[str, None] = "202605160003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("harness_runtime", sa.Column("owner_worker_id", sa.String(length=120), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_token", sa.String(length=120), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_last_renewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_checkpoint", sa.Integer(), nullable=True))
    op.create_index(
        "ix_harness_runtime_owner_lease",
        "harness_runtime",
        ["owner_lease_expires_at", "owner_worker_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_harness_runtime_owner_lease", table_name="harness_runtime")
    op.drop_column("harness_runtime", "owner_checkpoint")
    op.drop_column("harness_runtime", "owner_lease_expires_at")
    op.drop_column("harness_runtime", "owner_last_renewed_at")
    op.drop_column("harness_runtime", "owner_claimed_at")
    op.drop_column("harness_runtime", "owner_token")
    op.drop_column("harness_runtime", "owner_worker_id")
