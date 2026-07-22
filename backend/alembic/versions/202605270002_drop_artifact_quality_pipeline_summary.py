"""drop artifact quality pipeline summary columns

Revision ID: 202605270002
Revises: 202605270001
Create Date: 2026-05-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605270002"
down_revision: Union[str, None] = "202605270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("harness_conversations", "artifact_quality_updated_at")
    op.drop_column("harness_conversations", "artifact_quality_p0_count")
    op.drop_column("harness_conversations", "artifact_quality_status")
    op.drop_column("harness_conversations", "artifact_pipeline_status")
    op.drop_column("harness_conversations", "artifact_pipeline_stage")


def downgrade() -> None:
    op.add_column("harness_conversations", sa.Column("artifact_pipeline_stage", sa.String(length=40), nullable=True))
    op.add_column("harness_conversations", sa.Column("artifact_pipeline_status", sa.String(length=40), nullable=True))
    op.add_column("harness_conversations", sa.Column("artifact_quality_status", sa.String(length=40), nullable=True))
    op.add_column(
        "harness_conversations",
        sa.Column("artifact_quality_p0_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("harness_conversations", sa.Column("artifact_quality_updated_at", sa.DateTime(timezone=True), nullable=True))
