"""add harness hot storage tables

Revision ID: 202605120002
Revises: 202605120001
Create Date: 2026-05-12 20:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "202605120002"
down_revision: Union[str, None] = "202605120001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _message_id_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _message_content_type():
    return mysql.LONGTEXT().with_variant(sa.Text(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "harness_conversations",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("runtime_profile", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("skill_id", sa.String(length=120), nullable=True),
        sa.Column("resolved_skill_id", sa.String(length=120), nullable=True),
        sa.Column("skill_resolution_source", sa.String(length=80), nullable=True),
        sa.Column("skill_selection_mode", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("artifact_mode", sa.String(length=40), nullable=False, server_default="web"),
        sa.Column("visual_basis", sa.JSON(), nullable=True),
        sa.Column("last_skill_decision_reason", sa.Text(), nullable=True),
        sa.Column("last_skill_decision_confidence", sa.Float(), nullable=True),
        sa.Column("phase", sa.String(length=40), nullable=False, server_default="executing"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="fast"),
        sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("runtime_status", sa.String(length=20), nullable=False, server_default="idle"),
        sa.Column("display_status", sa.String(length=40), nullable=False, server_default="空闲"),
        sa.Column("run_state", sa.String(length=30), nullable=False, server_default="idle"),
        sa.Column("stall_reason", sa.String(length=120), nullable=True),
        sa.Column("last_tool", sa.String(length=120), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_source", sa.String(length=60), nullable=True),
        sa.Column("turn_status", sa.String(length=30), nullable=True),
        sa.Column("run_id", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_version", sa.String(length=20), nullable=False, server_default="harness"),
        sa.Column("model_preferences", sa.JSON(), nullable=True),
        sa.Column("workspace_dir", sa.String(length=1024), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_preview", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_harness_conversations_user_scope_updated",
        "harness_conversations",
        ["user_id", "runtime_profile", "project_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_harness_conversations_runtime_status",
        "harness_conversations",
        ["runtime_status"],
        unique=False,
    )
    op.create_index(
        "ix_harness_conversations_status",
        "harness_conversations",
        ["status"],
        unique=False,
    )

    op.create_table(
        "harness_runtime",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("heartbeat_at", sa.Float(), nullable=True),
        sa.Column("user_interaction_json", sa.JSON(), nullable=True),
        sa.Column("plan_state_json", sa.JSON(), nullable=True),
        sa.Column("outline_runtime_json", sa.JSON(), nullable=True),
        sa.Column("runtime_state_json", sa.JSON(), nullable=True),
        sa.Column("failure_json", sa.JSON(), nullable=True),
        sa.Column("recovery_summary_json", sa.JSON(), nullable=True),
        sa.Column("recovery_history_json", sa.JSON(), nullable=True),
        sa.Column("parent_usage_log_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("conversation_id"),
    )

    op.create_table(
        "harness_messages",
        sa.Column("id", _message_id_type(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("tool_call_id", sa.String(length=120), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("content", _message_content_type(), nullable=True),
        sa.Column("blocks_json", sa.JSON(), nullable=True),
        sa.Column("attachments_json", sa.JSON(), nullable=True),
        sa.Column("tool_calls_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("streaming", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "message_id", name="uq_harness_messages_conversation_message_id"),
    )
    op.create_index(
        "ix_harness_messages_conversation_id_id",
        "harness_messages",
        ["conversation_id", "id"],
        unique=False,
    )

    op.create_table(
        "harness_workspace_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False, server_default="file"),
        sa.Column("path", sa.String(length=1024), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=40), nullable=False, server_default="file"),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("current_version_id", sa.String(length=40), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "external_id", name="uq_harness_workspace_files_conversation_external_id"),
    )
    op.create_index(
        "ix_harness_workspace_files_conversation_id",
        "harness_workspace_files",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_harness_workspace_files_conversation_id", table_name="harness_workspace_files")
    op.drop_table("harness_workspace_files")

    op.drop_index("ix_harness_messages_conversation_id_id", table_name="harness_messages")
    op.drop_table("harness_messages")

    op.drop_table("harness_runtime")

    op.drop_index("ix_harness_conversations_status", table_name="harness_conversations")
    op.drop_index("ix_harness_conversations_runtime_status", table_name="harness_conversations")
    op.drop_index("ix_harness_conversations_user_scope_updated", table_name="harness_conversations")
    op.drop_table("harness_conversations")
