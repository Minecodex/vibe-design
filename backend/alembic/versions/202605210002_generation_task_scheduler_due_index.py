"""cover generation task scheduler due scan order

Revision ID: 202605210002
Revises: 202605210001
Create Date: 2026-05-21 16:20:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "202605210002"
down_revision: str | None = "202605210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_generation_tasks_scheduler_due", table_name="generation_tasks")
    op.create_index(
        "ix_generation_tasks_scheduler_due",
        "generation_tasks",
        [
            "status",
            "scheduler_next_run_at",
            "created_at",
            "id",
            "scheduler_lease_expires_at",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_tasks_scheduler_due", table_name="generation_tasks")
    op.create_index(
        "ix_generation_tasks_scheduler_due",
        "generation_tasks",
        ["status", "scheduler_next_run_at", "scheduler_lease_expires_at"],
    )
