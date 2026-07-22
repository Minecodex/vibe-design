"""add context projection state

Revision ID: 202605170002
Revises: 202605170001
Create Date: 2026-05-17 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605170002"
down_revision: Union[str, None] = "202605170001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _big_id():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "context_projection_state",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("latest_observed_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_processed_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dirty_mask", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("last_dirty_reason", sa.String(length=120), nullable=True),
        sa.Column("next_project_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_token", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("last_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index("ix_context_projection_state_user_conversation", "context_projection_state", ["user_id", "conversation_id"])
    op.create_index("ix_context_projection_state_schedule", "context_projection_state", ["next_project_at", "lease_expires_at"])
    op.create_index("ix_context_projection_state_lease", "context_projection_state", ["lease_expires_at", "lease_owner"])

    op.create_table(
        "context_projection_runs",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("lease_token", sa.String(length=120), nullable=False),
        sa.Column("claimed_dirty_mask", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("starting_processed_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ending_processed_sequence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="claimed"),
        sa.Column("timings_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_projection_runs_conversation_created", "context_projection_runs", ["conversation_id", "created_at"])
    op.create_index("ix_context_projection_runs_status", "context_projection_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_context_projection_runs_status", table_name="context_projection_runs")
    op.drop_index("ix_context_projection_runs_conversation_created", table_name="context_projection_runs")
    op.drop_table("context_projection_runs")

    op.drop_index("ix_context_projection_state_lease", table_name="context_projection_state")
    op.drop_index("ix_context_projection_state_schedule", table_name="context_projection_state")
    op.drop_index("ix_context_projection_state_user_conversation", table_name="context_projection_state")
    op.drop_table("context_projection_state")

