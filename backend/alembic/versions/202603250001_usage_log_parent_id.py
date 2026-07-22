"""add parent_id to usage_logs

Revision ID: 202603250001
Revises: 202603240001
Create Date: 2026-03-25 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202603250001"
down_revision = "202603240001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("usage_logs", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
            batch_op.create_index(op.f("ix_usage_logs_parent_id"), ["parent_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_usage_logs_parent_id_usage_logs",
                "usage_logs",
                ["parent_id"],
                ["id"],
            )
        return

    op.add_column("usage_logs", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_usage_logs_parent_id"), "usage_logs", ["parent_id"], unique=False)
    op.create_foreign_key(
        "fk_usage_logs_parent_id_usage_logs",
        "usage_logs",
        "usage_logs",
        ["parent_id"],
        ["id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("usage_logs", recreate="always") as batch_op:
            batch_op.drop_constraint("fk_usage_logs_parent_id_usage_logs", type_="foreignkey")
            batch_op.drop_index(op.f("ix_usage_logs_parent_id"))
            batch_op.drop_column("parent_id")
        return

    op.drop_constraint("fk_usage_logs_parent_id_usage_logs", "usage_logs", type_="foreignkey")
    op.drop_index(op.f("ix_usage_logs_parent_id"), table_name="usage_logs")
    op.drop_column("usage_logs", "parent_id")
