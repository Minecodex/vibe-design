from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from .base_model import TimestampMixin


class HarnessConversation(TimestampMixin, Base):
    __tablename__ = "harness_conversations"
    __table_args__ = (
        Index(
            "ix_harness_conversations_user_scope_updated",
            "user_id",
            "runtime_profile",
            "project_id",
            "updated_at",
        ),
        Index("ix_harness_conversations_runtime_status", "runtime_status"),
        Index("ix_harness_conversations_status", "status"),
    )

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="home")
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    skill_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_skill_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    skill_resolution_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    skill_selection_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    artifact_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="web")
    design_system_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_skill_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_skill_decision_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    phase: Mapped[str] = mapped_column(String(40), nullable=False, default="executing")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="fast")
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    runtime_status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    display_status: Mapped[str] = mapped_column(String(40), nullable=False, default="空闲")
    run_state: Mapped[str] = mapped_column(String(30), nullable=False, default="idle")
    stall_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_tool: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_activity_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    turn_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    active_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    runtime_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="harness")
    model_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workspace_dir: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_usage_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class HarnessAgentRun(TimestampMixin, Base):
    __tablename__ = "harness_agent_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_harness_agent_runs_run_id"),
        UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_harness_agent_runs_conversation_idempotency",
        ),
        Index("ix_harness_agent_runs_conversation_status", "conversation_id", "status"),
        Index("ix_harness_agent_runs_conversation_created", "conversation_id", "created_at"),
        Index(
            "ix_harness_agent_runs_user_conversation_created",
            "user_id",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    current_step_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runtime_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_usage_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class HarnessAgentStep(TimestampMixin, Base):
    __tablename__ = "harness_agent_steps"
    __table_args__ = (
        UniqueConstraint("step_id", name="uq_harness_agent_steps_step_id"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_harness_agent_steps_run_idempotency"),
        Index(
            "ix_harness_agent_steps_status_due",
            "status",
            "priority",
            "next_run_at",
            "claim_expires_at",
        ),
        Index("ix_harness_agent_steps_claim", "claim_expires_at", "claim_owner"),
        Index("ix_harness_agent_steps_conversation_status", "conversation_id", "status"),
        Index(
            "ix_harness_agent_steps_conversation_status_updated",
            "conversation_id",
            "status",
            "updated_at",
        ),
        Index("ix_harness_agent_steps_run_status_updated", "run_id", "status", "updated_at"),
        Index("ix_harness_agent_steps_run_type_status", "run_id", "step_type", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    step_id: Mapped[str] = mapped_column(String(80), nullable=False)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checkpoint_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_run_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(120), nullable=True)
    claim_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_renewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    depends_on_step_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class HarnessAgentActivity(TimestampMixin, Base):
    __tablename__ = "harness_agent_activities"
    __table_args__ = (
        UniqueConstraint("activity_id", name="uq_harness_agent_activities_activity_id"),
        Index("ix_harness_agent_activities_run_step", "run_id", "step_id"),
        Index("ix_harness_agent_activities_type_status", "activity_type", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    activity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False)
    step_id: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class HarnessResourceLease(TimestampMixin, Base):
    __tablename__ = "harness_resource_leases"
    __table_args__ = (
        UniqueConstraint("resource_type", "slot_index", name="uq_harness_resource_leases_resource_slot"),
        Index("ix_harness_resource_leases_resource_expires", "resource_type", "expires_at"),
        Index("ix_harness_resource_leases_holder", "holder_id", "owner_domain"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    holder_id: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_domain: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    acquired_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    last_renewed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)


class HarnessMessage(TimestampMixin, Base):
    __tablename__ = "harness_messages"
    __table_args__ = (
        Index("ix_harness_messages_conversation_id_id", "conversation_id", "id"),
        UniqueConstraint("conversation_id", "message_id", name="uq_harness_messages_conversation_message_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str] = mapped_column(String(40), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attachments_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_calls_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class HarnessWorkspaceFile(TimestampMixin, Base):
    __tablename__ = "harness_workspace_files"
    __table_args__ = (
        UniqueConstraint("conversation_id", "external_id", name="uq_harness_workspace_files_conversation_external_id"),
        Index("ix_harness_workspace_files_conversation_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="file")
    path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(40), nullable=False, default="file")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ConversationEvent(TimestampMixin, Base):
    __tablename__ = "conversation_events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_events_conversation_sequence"),
        UniqueConstraint("conversation_id", "idempotency_key", name="uq_conversation_events_conversation_idempotency_key"),
        Index("ix_conversation_events_conversation_sequence", "conversation_id", "sequence"),
        Index("ix_conversation_events_user_conversation", "user_id", "conversation_id"),
        Index("ix_conversation_events_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    lane: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_block_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class HarnessPresentationProjectionState(TimestampMixin, Base):
    __tablename__ = "harness_presentation_projection_state"
    __table_args__ = (
        Index("ix_harness_presentation_projection_user", "user_id", "conversation_id"),
        Index("ix_harness_presentation_projection_lease", "lease_expires_at", "lease_owner"),
    )

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    applied_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_observed_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="idle")
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContextProjectionState(TimestampMixin, Base):
    __tablename__ = "context_projection_state"
    __table_args__ = (
        Index("ix_context_projection_state_user_conversation", "user_id", "conversation_id"),
        Index("ix_context_projection_state_schedule", "next_project_at", "lease_expires_at"),
        Index("ix_context_projection_state_lease", "lease_expires_at", "lease_owner"),
    )

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_observed_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_processed_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dirty_mask: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_dirty_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_project_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ContextProjectionRun(TimestampMixin, Base):
    __tablename__ = "context_projection_runs"
    __table_args__ = (
        Index("ix_context_projection_runs_conversation_created", "conversation_id", "created_at"),
        Index("ix_context_projection_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(120), nullable=False)
    claimed_dirty_mask: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    starting_processed_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ending_processed_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="claimed")
    timings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
