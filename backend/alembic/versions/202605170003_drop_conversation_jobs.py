"""drop legacy conversation jobs

Revision ID: 202605170003
Revises: 202605170002
Create Date: 2026-05-17 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "202605170003"
down_revision: Union[str, None] = "202605170002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_conversation_jobs_lease", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_conversation_kind", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_status_next_run", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_dedupe", table_name="conversation_jobs")
    op.drop_table("conversation_jobs")


def downgrade() -> None:
    pass

