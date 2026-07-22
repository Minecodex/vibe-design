"""add agent workflow vnext tables

Revision ID: 202605280001
Revises: 202605270002
Create Date: 2026-05-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605280001"
down_revision: Union[str, None] = "202605270002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _big_id():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _json():
    return sa.JSON()


def upgrade() -> None:
    op.add_column(
        "harness_conversations",
        sa.Column("runtime_version", sa.String(length=20), nullable=False, server_default="v1"),
    )
    op.add_column("harness_conversations", sa.Column("active_run_id", sa.String(length=80), nullable=True))
    op.add_column("harness_conversations", sa.Column("runtime_snapshot_json", _json(), nullable=True))

    op.create_table(
        "harness_agent_runs",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("current_step_type", sa.String(length=80), nullable=True),
        sa.Column("input_json", _json(), nullable=False),
        sa.Column("runtime_snapshot_json", _json(), nullable=True),
        sa.Column("parent_usage_log_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_harness_agent_runs_run_id"),
        sa.UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_harness_agent_runs_conversation_idempotency",
        ),
    )
    op.create_index("ix_harness_agent_runs_conversation_status", "harness_agent_runs", ["conversation_id", "status"])
    op.create_index(
        "ix_harness_agent_runs_user_conversation_created",
        "harness_agent_runs",
        ["user_id", "conversation_id", "created_at"],
    )

    op.create_table(
        "harness_agent_steps",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("step_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("input_json", _json(), nullable=False),
        sa.Column("output_json", _json(), nullable=True),
        sa.Column("checkpoint_json", _json(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_owner", sa.String(length=120), nullable=True),
        sa.Column("claim_token", sa.String(length=120), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("depends_on_step_id", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id", name="uq_harness_agent_steps_step_id"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_harness_agent_steps_run_idempotency"),
    )
    op.create_index(
        "ix_harness_agent_steps_status_due",
        "harness_agent_steps",
        ["status", "priority", "next_run_at", "claim_expires_at"],
    )
    op.create_index("ix_harness_agent_steps_claim", "harness_agent_steps", ["claim_expires_at", "claim_owner"])
    op.create_index(
        "ix_harness_agent_steps_conversation_status",
        "harness_agent_steps",
        ["conversation_id", "status"],
    )
    op.create_index(
        "ix_harness_agent_steps_run_type_status",
        "harness_agent_steps",
        ["run_id", "step_type", "status"],
    )

    op.create_table(
        "harness_agent_activities",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("step_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("activity_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_ref", sa.String(length=255), nullable=True),
        sa.Column("output_ref", sa.String(length=255), nullable=True),
        sa.Column("diagnostics_json", _json(), nullable=True),
        sa.Column("elapsed_ms", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", name="uq_harness_agent_activities_activity_id"),
    )
    op.create_index("ix_harness_agent_activities_run_step", "harness_agent_activities", ["run_id", "step_id"])
    op.create_index(
        "ix_harness_agent_activities_type_status",
        "harness_agent_activities",
        ["activity_type", "status"],
    )
    op.drop_table("harness_runtime")
    op.drop_table("harness_agent_run_requests")


def downgrade() -> None:
    op.drop_index("ix_harness_agent_activities_type_status", table_name="harness_agent_activities")
    op.drop_index("ix_harness_agent_activities_run_step", table_name="harness_agent_activities")
    op.drop_table("harness_agent_activities")
    op.drop_index("ix_harness_agent_steps_run_type_status", table_name="harness_agent_steps")
    op.drop_index("ix_harness_agent_steps_conversation_status", table_name="harness_agent_steps")
    op.drop_index("ix_harness_agent_steps_claim", table_name="harness_agent_steps")
    op.drop_index("ix_harness_agent_steps_status_due", table_name="harness_agent_steps")
    op.drop_table("harness_agent_steps")
    op.drop_index("ix_harness_agent_runs_user_conversation_created", table_name="harness_agent_runs")
    op.drop_index("ix_harness_agent_runs_conversation_status", table_name="harness_agent_runs")
    op.drop_table("harness_agent_runs")
    op.create_table(
        "harness_runtime",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_interaction_json", _json(), nullable=True),
        sa.Column("plan_state_json", _json(), nullable=True),
        sa.Column("outline_runtime_json", _json(), nullable=True),
        sa.Column("runtime_state_json", _json(), nullable=True),
        sa.Column("failure_json", _json(), nullable=True),
        sa.Column("recovery_summary_json", _json(), nullable=True),
        sa.Column("recovery_history_json", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_table(
        "harness_agent_run_requests",
        sa.Column("id", _big_id(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("payload_json", _json(), nullable=False),
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
    op.drop_column("harness_conversations", "runtime_snapshot_json")
    op.drop_column("harness_conversations", "active_run_id")
    op.drop_column("harness_conversations", "runtime_version")
