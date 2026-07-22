"""add harness agent step active state indexes

Revision ID: 202606040001
Revises: 202605280003
Create Date: 2026-06-04 22:45:00
"""

from alembic import op


revision = "202606040001"
down_revision = "202605280003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_harness_agent_steps_conversation_status_updated",
        "harness_agent_steps",
        ["conversation_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_harness_agent_steps_run_status_updated",
        "harness_agent_steps",
        ["run_id", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_harness_agent_steps_run_status_updated", table_name="harness_agent_steps")
    op.drop_index("ix_harness_agent_steps_conversation_status_updated", table_name="harness_agent_steps")
