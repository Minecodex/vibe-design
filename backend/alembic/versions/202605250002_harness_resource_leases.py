"""add harness resource leases

Revision ID: 202605250002
Revises: 202605250001
Create Date: 2026-05-25 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605250002"
down_revision: Union[str, None] = "202605250001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _big_id():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "harness_resource_leases",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("holder_id", sa.String(length=120), nullable=False),
        sa.Column("owner_domain", sa.String(length=40), nullable=False),
        sa.Column("owner_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_type",
            "slot_index",
            name="uq_harness_resource_leases_resource_slot",
        ),
    )
    op.create_index(
        "ix_harness_resource_leases_resource_expires",
        "harness_resource_leases",
        ["resource_type", "expires_at"],
    )
    op.create_index(
        "ix_harness_resource_leases_holder",
        "harness_resource_leases",
        ["holder_id", "owner_domain"],
    )


def downgrade() -> None:
    op.drop_index("ix_harness_resource_leases_holder", table_name="harness_resource_leases")
    op.drop_index("ix_harness_resource_leases_resource_expires", table_name="harness_resource_leases")
    op.drop_constraint("uq_harness_resource_leases_resource_slot", "harness_resource_leases", type_="unique")
    op.drop_table("harness_resource_leases")
