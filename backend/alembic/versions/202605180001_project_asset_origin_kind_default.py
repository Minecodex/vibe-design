"""drop legacy default project asset origin kind

Revision ID: 202605180001
Revises: 202605170005
Create Date: 2026-05-18 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605180001"
down_revision: Union[str, None] = "202605170005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project_assets") as batch_op:
        batch_op.alter_column(
            "origin_kind",
            existing_type=sa.String(length=50),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("project_assets") as batch_op:
        batch_op.alter_column(
            "origin_kind",
            existing_type=sa.String(length=50),
            nullable=False,
            server_default="legacy",
        )
