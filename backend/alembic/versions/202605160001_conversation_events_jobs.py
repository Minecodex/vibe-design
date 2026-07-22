"""add conversation events and compression jobs

Revision ID: 202605160001
Revises: 202605150001
Create Date: 2026-05-16 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605160001"
down_revision: Union[str, None] = "202605150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _big_id():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "conversation_events",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("lane", sa.String(length=30), nullable=False, server_default="user"),
        sa.Column("block_id", sa.String(length=120), nullable=True),
        sa.Column("agent_id", sa.String(length=120), nullable=True),
        sa.Column("tool_call_id", sa.String(length=120), nullable=True),
        sa.Column("artifact_id", sa.String(length=120), nullable=True),
        sa.Column("parent_block_id", sa.String(length=120), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_events_conversation_sequence"),
    )
    op.create_index("ix_conversation_events_conversation_sequence", "conversation_events", ["conversation_id", "sequence"])
    op.create_index("ix_conversation_events_user_conversation", "conversation_events", ["user_id", "conversation_id"])
    op.create_index("ix_conversation_events_type", "conversation_events", ["event_type"])

    op.create_table(
        "conversation_jobs",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_jobs_dedupe", "conversation_jobs", ["conversation_id", "kind", "dedupe_key", "status"])
    op.create_index("ix_conversation_jobs_status_next_run", "conversation_jobs", ["status", "next_run_at"])
    op.create_index("ix_conversation_jobs_conversation_kind", "conversation_jobs", ["conversation_id", "kind"])
    op.create_index("ix_conversation_jobs_lease", "conversation_jobs", ["lease_expires_at", "lease_owner"])


def downgrade() -> None:
    op.drop_index("ix_conversation_jobs_lease", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_conversation_kind", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_status_next_run", table_name="conversation_jobs")
    op.drop_index("ix_conversation_jobs_dedupe", table_name="conversation_jobs")
    op.drop_table("conversation_jobs")

    op.drop_index("ix_conversation_events_type", table_name="conversation_events")
    op.drop_index("ix_conversation_events_user_conversation", table_name="conversation_events")
    op.drop_index("ix_conversation_events_conversation_sequence", table_name="conversation_events")
    op.drop_table("conversation_events")
