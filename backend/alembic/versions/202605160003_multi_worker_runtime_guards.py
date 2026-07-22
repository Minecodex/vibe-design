"""add multi-worker runtime guards

Revision ID: 202605160003
Revises: 202605160002
Create Date: 2026-05-16 12:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605160003"
down_revision: Union[str, None] = "202605160002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversation_jobs", sa.Column("active_dedupe_key", sa.String(length=160), nullable=True))
    op.execute(
        """
        UPDATE conversation_jobs
        SET active_dedupe_key = dedupe_key
        WHERE status IN ('pending', 'running')
        """
    )
    op.execute(
        """
        UPDATE conversation_jobs
        SET active_dedupe_key = NULL
        WHERE active_dedupe_key IS NOT NULL
          AND id NOT IN (
            SELECT chosen_id
            FROM (
              SELECT MAX(id) AS chosen_id
              FROM conversation_jobs
              WHERE active_dedupe_key IS NOT NULL
              GROUP BY conversation_id, kind, active_dedupe_key
            ) AS dedupe_winners
          )
        """
    )
    op.create_index(
        "uq_conversation_jobs_active_dedupe",
        "conversation_jobs",
        ["conversation_id", "kind", "active_dedupe_key"],
        unique=True,
    )

    op.execute(
        """
        UPDATE usage_logs
        SET task_id = NULL
        WHERE task_id IS NOT NULL
          AND id NOT IN (
            SELECT chosen_id
            FROM (
              SELECT MAX(id) AS chosen_id
              FROM usage_logs
              WHERE task_id IS NOT NULL
              GROUP BY task_id
            ) AS usage_log_winners
          )
        """
    )
    op.create_index("uq_usage_logs_task_id", "usage_logs", ["task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_usage_logs_task_id", table_name="usage_logs")
    op.drop_index("uq_conversation_jobs_active_dedupe", table_name="conversation_jobs")
    op.drop_column("conversation_jobs", "active_dedupe_key")
