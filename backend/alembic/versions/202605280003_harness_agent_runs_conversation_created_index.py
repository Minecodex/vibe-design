"""add harness agent runs conversation created index

Revision ID: 202605280003
Revises: 202605280002
Create Date: 2026-05-28 00:03:00
"""

from alembic import op


revision = "202605280003"
down_revision = "202605280002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_harness_agent_runs_conversation_created",
        "harness_agent_runs",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_harness_agent_runs_conversation_created", table_name="harness_agent_runs")
