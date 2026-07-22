"""add versioned per-user APIMart credentials

Revision ID: 202607210002
Revises: 202607210001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607210002"
down_revision: str | Sequence[str] | None = "202607210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_apimart_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_apimart_credentials_user_id", "user_apimart_credentials", ["user_id"])
    op.create_index(
        "ix_user_apimart_credentials_is_current", "user_apimart_credentials", ["is_current"]
    )
    op.add_column(
        "generation_tasks", sa.Column("apimart_credential_id", sa.Integer(), nullable=True)
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("generation_tasks") as batch_op:
            batch_op.create_foreign_key(
                "fk_generation_tasks_apimart_credential_id",
                "user_apimart_credentials",
                ["apimart_credential_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "fk_generation_tasks_apimart_credential_id",
            "generation_tasks",
            "user_apimart_credentials",
            ["apimart_credential_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_generation_tasks_apimart_credential_id", "generation_tasks", ["apimart_credential_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_generation_tasks_apimart_credential_id", table_name="generation_tasks")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("generation_tasks") as batch_op:
            batch_op.drop_constraint(
                "fk_generation_tasks_apimart_credential_id",
                type_="foreignkey",
            )
            batch_op.drop_column("apimart_credential_id")
    else:
        op.drop_constraint(
            "fk_generation_tasks_apimart_credential_id",
            "generation_tasks",
            type_="foreignkey",
        )
        op.drop_column("generation_tasks", "apimart_credential_id")
    op.drop_index("ix_user_apimart_credentials_is_current", table_name="user_apimart_credentials")
    op.drop_index("ix_user_apimart_credentials_user_id", table_name="user_apimart_credentials")
    op.drop_table("user_apimart_credentials")
