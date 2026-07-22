"""Replace harness visual_basis with design_system_id.

Revision ID: 202606060001
Revises: 202606040001
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606060001"
down_revision = "202606040001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("harness_conversations", sa.Column("design_system_id", sa.String(length=120), nullable=True))
    op.drop_column("harness_conversations", "visual_basis")


def downgrade() -> None:
    op.add_column("harness_conversations", sa.Column("visual_basis", sa.JSON(), nullable=True))
    op.drop_column("harness_conversations", "design_system_id")
