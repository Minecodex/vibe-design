"""project user canvas revision

Revision ID: 202606220001
Revises: 202606210001
Create Date: 2026-06-22 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606220001"
down_revision: Union[str, Sequence[str], None] = "202606210001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_user_canvases",
        sa.Column(
            "canvas_revision",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_user_canvases", "canvas_revision")
