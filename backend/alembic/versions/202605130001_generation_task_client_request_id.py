"""generation task client request id

Revision ID: 202605130001
Revises: 202605120002
Create Date: 2026-05-13 00:01:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202605130001"
down_revision = "202605120002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("client_request_id", sa.String(length=128), nullable=True),
        )
        batch_op.create_index(
            "ix_generation_tasks_project_client_request_id",
            ["project_id", "client_request_id"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_generation_tasks_client_request",
            ["user_id", "project_id", "task_type", "client_request_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.drop_constraint("uq_generation_tasks_client_request", type_="unique")
        batch_op.drop_index("ix_generation_tasks_project_client_request_id")
        batch_op.drop_column("client_request_id")
