"""Add harness presentation projection state.

Revision ID: 202606070001
Revises: 202606060001
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202606070001"
down_revision = "202606060001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harness_presentation_projection_state",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("applied_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_observed_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="idle"),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_harness_presentation_projection_user",
        "harness_presentation_projection_state",
        ["user_id", "conversation_id"],
    )
    op.create_index(
        "ix_harness_presentation_projection_lease",
        "harness_presentation_projection_state",
        ["lease_expires_at", "lease_owner"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_harness_presentation_projection_lease",
        table_name="harness_presentation_projection_state",
    )
    op.drop_index(
        "ix_harness_presentation_projection_user",
        table_name="harness_presentation_projection_state",
    )
    op.drop_table("harness_presentation_projection_state")
