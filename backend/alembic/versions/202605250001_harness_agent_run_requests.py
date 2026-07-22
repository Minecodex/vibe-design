"""add harness agent run requests

Revision ID: 202605250001
Revises: 202605220001
Create Date: 2026-05-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605250001"
down_revision: Union[str, None] = "202605220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _big_id():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.add_column("harness_conversations", sa.Column("parent_usage_log_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE harness_conversations "
        "SET parent_usage_log_id = ("
        "SELECT harness_runtime.parent_usage_log_id "
        "FROM harness_runtime "
        "WHERE harness_runtime.conversation_id = harness_conversations.conversation_id"
        ") "
        "WHERE parent_usage_log_id IS NULL "
        "AND EXISTS ("
        "SELECT 1 FROM harness_runtime "
        "WHERE harness_runtime.conversation_id = harness_conversations.conversation_id "
        "AND harness_runtime.parent_usage_log_id IS NOT NULL"
        ")"
    )
    op.create_table(
        "harness_agent_run_requests",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_owner", sa.String(length=120), nullable=True),
        sa.Column("claim_token", sa.String(length=120), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=120), nullable=True),
        sa.Column("resource_waiting_for", sa.String(length=40), nullable=True),
        sa.Column("resource_wait_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_usage_log_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_harness_agent_run_requests_run_id"),
        sa.UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_harness_agent_run_requests_conversation_idempotency",
        ),
    )
    op.create_index(
        "ix_harness_agent_run_requests_status_due",
        "harness_agent_run_requests",
        ["status", "priority", "next_run_at", "claim_expires_at"],
    )
    op.create_index(
        "ix_harness_agent_run_requests_claim",
        "harness_agent_run_requests",
        ["claim_expires_at", "claim_owner"],
    )
    op.create_index(
        "ix_harness_agent_run_requests_conversation_status",
        "harness_agent_run_requests",
        ["conversation_id", "status"],
    )
    op.create_index(
        "ix_harness_agent_run_requests_user_conversation_created",
        "harness_agent_run_requests",
        ["user_id", "conversation_id", "created_at"],
    )
    op.create_index(
        "ix_harness_agent_run_requests_resource_wait",
        "harness_agent_run_requests",
        ["resource_waiting_for", "status"],
    )
    op.execute(
        "UPDATE harness_conversations "
        "SET runtime_status='failed', run_state='failed', turn_status='failed', "
        "last_error_summary='Agent run interrupted by architecture migration', "
        "finished_at=CURRENT_TIMESTAMP "
        "WHERE runtime_status='running'"
    )
    op.drop_index("ix_harness_runtime_owner_lease", table_name="harness_runtime")
    op.drop_column("harness_runtime", "run_id")
    op.drop_column("harness_runtime", "cancel_requested")
    op.drop_column("harness_runtime", "heartbeat_at")
    op.drop_column("harness_runtime", "owner_worker_id")
    op.drop_column("harness_runtime", "owner_token")
    op.drop_column("harness_runtime", "owner_claimed_at")
    op.drop_column("harness_runtime", "owner_last_renewed_at")
    op.drop_column("harness_runtime", "owner_lease_expires_at")
    op.drop_column("harness_runtime", "owner_checkpoint")
    op.drop_column("harness_runtime", "parent_usage_log_id")


def downgrade() -> None:
    op.drop_column("harness_conversations", "parent_usage_log_id")
    op.add_column("harness_runtime", sa.Column("parent_usage_log_id", sa.Integer(), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_checkpoint", sa.Integer(), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_last_renewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_token", sa.String(length=120), nullable=True))
    op.add_column("harness_runtime", sa.Column("owner_worker_id", sa.String(length=120), nullable=True))
    op.add_column("harness_runtime", sa.Column("heartbeat_at", sa.Float(), nullable=True))
    op.add_column("harness_runtime", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("harness_runtime", sa.Column("run_id", sa.String(length=80), nullable=True))
    op.create_index(
        "ix_harness_runtime_owner_lease",
        "harness_runtime",
        ["owner_lease_expires_at", "owner_worker_id"],
    )
    op.drop_index("ix_harness_agent_run_requests_resource_wait", table_name="harness_agent_run_requests")
    op.drop_index("ix_harness_agent_run_requests_user_conversation_created", table_name="harness_agent_run_requests")
    op.drop_index("ix_harness_agent_run_requests_conversation_status", table_name="harness_agent_run_requests")
    op.drop_index("ix_harness_agent_run_requests_claim", table_name="harness_agent_run_requests")
    op.drop_index("ix_harness_agent_run_requests_status_due", table_name="harness_agent_run_requests")
    op.drop_constraint("uq_harness_agent_run_requests_conversation_idempotency", "harness_agent_run_requests", type_="unique")
    op.drop_constraint("uq_harness_agent_run_requests_run_id", "harness_agent_run_requests", type_="unique")
    op.drop_table("harness_agent_run_requests")
