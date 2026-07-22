"""replace credits with billing amount cents

Revision ID: 202605120001
Revises: 202605070001
Create Date: 2026-05-12 14:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605120001"
down_revision: Union[str, None] = "202605070001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _reset_billing_tables() -> None:
    op.execute("UPDATE usage_logs SET parent_id = NULL WHERE parent_id IS NOT NULL")
    op.execute("DELETE FROM usage_logs")
    op.execute("DELETE FROM redemption_logs")


def _get_column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _plan_column_changes(existing_columns: set[str], *, add: Sequence[str], drop: Sequence[str]) -> tuple[list[str], list[str]]:
    return (
        [column_name for column_name in add if column_name not in existing_columns],
        [column_name for column_name in drop if column_name in existing_columns],
    )


def upgrade() -> None:
    bind = op.get_bind()
    _reset_billing_tables()

    user_add, user_drop = _plan_column_changes(
        _get_column_names(bind, "users"),
        add=("balance_cents",),
        drop=("credits",),
    )
    redemption_add, redemption_drop = _plan_column_changes(
        _get_column_names(bind, "redemption_logs"),
        add=("amount_cents",),
        drop=("credits_amount",),
    )
    usage_add, usage_drop = _plan_column_changes(
        _get_column_names(bind, "usage_logs"),
        add=("amount_cents", "amount_cents_original"),
        drop=("credits_cost", "credits_original"),
    )

    if bind.dialect.name == "sqlite":
        if user_add or user_drop:
            with op.batch_alter_table("users", recreate="always") as batch_op:
                if "balance_cents" in user_add:
                    batch_op.add_column(sa.Column("balance_cents", sa.Integer(), server_default="0", nullable=False))
                if "credits" in user_drop:
                    batch_op.drop_column("credits")

        if redemption_add or redemption_drop:
            with op.batch_alter_table("redemption_logs", recreate="always") as batch_op:
                if "amount_cents" in redemption_add:
                    batch_op.add_column(sa.Column("amount_cents", sa.Integer(), nullable=False))
                if "credits_amount" in redemption_drop:
                    batch_op.drop_column("credits_amount")

        if usage_add or usage_drop:
            with op.batch_alter_table("usage_logs", recreate="always") as batch_op:
                if "amount_cents" in usage_add:
                    batch_op.add_column(sa.Column("amount_cents", sa.Integer(), server_default="0", nullable=False))
                if "amount_cents_original" in usage_add:
                    batch_op.add_column(sa.Column("amount_cents_original", sa.Integer(), server_default="0", nullable=False))
                if "credits_cost" in usage_drop:
                    batch_op.drop_column("credits_cost")
                if "credits_original" in usage_drop:
                    batch_op.drop_column("credits_original")
    else:
        if "balance_cents" in user_add:
            op.add_column("users", sa.Column("balance_cents", sa.Integer(), server_default="0", nullable=False))
        if "credits" in user_drop:
            op.drop_column("users", "credits")

        if "amount_cents" in redemption_add:
            op.add_column("redemption_logs", sa.Column("amount_cents", sa.Integer(), nullable=False))
        if "credits_amount" in redemption_drop:
            op.drop_column("redemption_logs", "credits_amount")

        if "amount_cents" in usage_add:
            op.add_column("usage_logs", sa.Column("amount_cents", sa.Integer(), server_default="0", nullable=False))
        if "amount_cents_original" in usage_add:
            op.add_column("usage_logs", sa.Column("amount_cents_original", sa.Integer(), server_default="0", nullable=False))
        if "credits_cost" in usage_drop:
            op.drop_column("usage_logs", "credits_cost")
        if "credits_original" in usage_drop:
            op.drop_column("usage_logs", "credits_original")

    if "balance_cents" in _get_column_names(bind, "users"):
        op.execute("UPDATE users SET balance_cents = 0")


def downgrade() -> None:
    bind = op.get_bind()

    user_add, user_drop = _plan_column_changes(
        _get_column_names(bind, "users"),
        add=("credits",),
        drop=("balance_cents",),
    )
    redemption_add, redemption_drop = _plan_column_changes(
        _get_column_names(bind, "redemption_logs"),
        add=("credits_amount",),
        drop=("amount_cents",),
    )
    usage_add, usage_drop = _plan_column_changes(
        _get_column_names(bind, "usage_logs"),
        add=("credits_cost", "credits_original"),
        drop=("amount_cents", "amount_cents_original"),
    )

    if bind.dialect.name == "sqlite":
        if user_add or user_drop:
            with op.batch_alter_table("users", recreate="always") as batch_op:
                if "credits" in user_add:
                    batch_op.add_column(sa.Column("credits", sa.Integer(), server_default="0", nullable=False))
                if "balance_cents" in user_drop:
                    batch_op.drop_column("balance_cents")

        if redemption_add or redemption_drop:
            with op.batch_alter_table("redemption_logs", recreate="always") as batch_op:
                if "credits_amount" in redemption_add:
                    batch_op.add_column(sa.Column("credits_amount", sa.Integer(), nullable=False))
                if "amount_cents" in redemption_drop:
                    batch_op.drop_column("amount_cents")

        if usage_add or usage_drop:
            with op.batch_alter_table("usage_logs", recreate="always") as batch_op:
                if "credits_cost" in usage_add:
                    batch_op.add_column(sa.Column("credits_cost", sa.Integer(), server_default="0", nullable=False))
                if "credits_original" in usage_add:
                    batch_op.add_column(sa.Column("credits_original", sa.Integer(), server_default="0", nullable=False))
                if "amount_cents" in usage_drop:
                    batch_op.drop_column("amount_cents")
                if "amount_cents_original" in usage_drop:
                    batch_op.drop_column("amount_cents_original")
    else:
        if "credits" in user_add:
            op.add_column("users", sa.Column("credits", sa.Integer(), server_default="0", nullable=False))
        if "balance_cents" in user_drop:
            op.drop_column("users", "balance_cents")

        if "credits_amount" in redemption_add:
            op.add_column("redemption_logs", sa.Column("credits_amount", sa.Integer(), nullable=False))
        if "amount_cents" in redemption_drop:
            op.drop_column("redemption_logs", "amount_cents")

        if "credits_cost" in usage_add:
            op.add_column("usage_logs", sa.Column("credits_cost", sa.Integer(), server_default="0", nullable=False))
        if "credits_original" in usage_add:
            op.add_column("usage_logs", sa.Column("credits_original", sa.Integer(), server_default="0", nullable=False))
        if "amount_cents" in usage_drop:
            op.drop_column("usage_logs", "amount_cents")
        if "amount_cents_original" in usage_drop:
            op.drop_column("usage_logs", "amount_cents_original")
