"""add artifact quality pipeline summary columns

Revision ID: 202605270001
Revises: 202605250002
Create Date: 2026-05-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605270001"
down_revision: Union[str, None] = "202605250002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("harness_conversations", sa.Column("artifact_pipeline_stage", sa.String(length=40), nullable=True))
    op.add_column("harness_conversations", sa.Column("artifact_pipeline_status", sa.String(length=40), nullable=True))
    op.add_column("harness_conversations", sa.Column("artifact_quality_status", sa.String(length=40), nullable=True))
    op.add_column(
        "harness_conversations",
        sa.Column("artifact_quality_p0_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("harness_conversations", sa.Column("artifact_quality_updated_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        "UPDATE harness_agent_run_requests "
        "SET status='failed', "
        "last_error_type='ArtifactPipelineMigration', "
        "last_error_summary='Interrupted by artifact pipeline migration; old runtime state is not resumable.', "
        "finished_at=CURRENT_TIMESTAMP "
        "WHERE status IN ('queued', 'running', 'claimed', 'resource_wait')"
    )
    op.execute(
        "UPDATE harness_conversations "
        "SET runtime_status='failed', run_state='failed', turn_status='failed', "
        "display_status='运行已中断', "
        "last_error_summary='旧运行态已被 artifact pipeline 重构中断，请重新执行。', "
        "finished_at=CURRENT_TIMESTAMP "
        "WHERE runtime_status='running'"
    )


def downgrade() -> None:
    op.drop_column("harness_conversations", "artifact_quality_updated_at")
    op.drop_column("harness_conversations", "artifact_quality_p0_count")
    op.drop_column("harness_conversations", "artifact_quality_status")
    op.drop_column("harness_conversations", "artifact_pipeline_status")
    op.drop_column("harness_conversations", "artifact_pipeline_stage")
