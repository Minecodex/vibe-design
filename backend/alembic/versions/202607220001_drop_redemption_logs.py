"""drop the retired redemption log table

Revision ID: 202607220001
Revises: 202607210002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607220001"
down_revision: str | Sequence[str] | None = "202607210002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("redemption_logs"):
        op.drop_table("redemption_logs")


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("redemption_logs"):
        return

    op.create_table(
        "redemption_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_id", sa.String(length=100), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_redemption_logs_code_id",
        "redemption_logs",
        ["code_id"],
        unique=True,
    )
    op.create_index(
        "ix_redemption_logs_user_id",
        "redemption_logs",
        ["user_id"],
        unique=False,
    )
