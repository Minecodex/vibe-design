"""rename generation task poller claims to scheduler state

Revision ID: 202605180004
Revises: 202605180003
Create Date: 2026-05-18 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605180004"
down_revision: Union[str, None] = "202605180003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.alter_column(
            "poller_claim_token",
            new_column_name="scheduler_claim_token",
            existing_type=sa.String(length=64),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "poller_claimed_at",
            new_column_name="scheduler_claimed_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "poller_lease_expires_at",
            new_column_name="scheduler_lease_expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column("scheduler_next_run_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("scheduler_attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("terminalized_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("terminal_side_effects_finalized_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("workflow_stage", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("last_error_type", sa.String(length=120), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE generation_tasks
            SET terminal_side_effects_finalized_at = CURRENT_TIMESTAMP
            WHERE status IN ('completed', 'failed')
            """
        )
    )
    op.create_index(
        "ix_generation_tasks_scheduler_due",
        "generation_tasks",
        ["status", "scheduler_next_run_at", "scheduler_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_tasks_scheduler_due", table_name="generation_tasks")
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.drop_column("last_error_type")
        batch_op.drop_column("workflow_stage")
        batch_op.drop_column("terminal_side_effects_finalized_at")
        batch_op.drop_column("terminalized_at")
        batch_op.drop_column("last_polled_at")
        batch_op.drop_column("scheduler_attempt_count")
        batch_op.drop_column("scheduler_next_run_at")
        batch_op.alter_column(
            "scheduler_lease_expires_at",
            new_column_name="poller_lease_expires_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "scheduler_claimed_at",
            new_column_name="poller_claimed_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "scheduler_claim_token",
            new_column_name="poller_claim_token",
            existing_type=sa.String(length=64),
            existing_nullable=True,
        )
