"""Retire unfinished local media generation tasks.

Revision ID: 202607210001
Revises: 202605040001, 202606250001, 4f9d8d7b2c10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202607210001"
down_revision = ("202605040001", "202606250001", "4f9d8d7b2c10")
branch_labels = None
depends_on = None


def _retire_tasks(connection) -> None:
    generation_tasks = sa.table(
        "generation_tasks",
        sa.column("provider_code", sa.String()),
        sa.column("status", sa.String()),
        sa.column("progress", sa.Integer()),
        sa.column("workflow_stage", sa.String()),
        sa.column("last_error_type", sa.String()),
        sa.column("error_message", sa.Text()),
        sa.column("scheduler_next_run_at", sa.DateTime()),
        sa.column("scheduler_claim_token", sa.String()),
        sa.column("scheduler_claimed_at", sa.DateTime()),
        sa.column("scheduler_lease_expires_at", sa.DateTime()),
        sa.column("terminalized_at", sa.DateTime()),
        sa.column("terminal_side_effects_finalized_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = sa.func.now()
    connection.execute(
        generation_tasks.update()
        .where(generation_tasks.c.provider_code == "local_rembg")
        .where(generation_tasks.c.status.in_(("pending", "processing")))
        .values(
            status="failed",
            progress=100,
            workflow_stage="terminal_failed",
            last_error_type="feature_removed",
            error_message="元素编辑功能已下线 / Element editing has been retired",
            scheduler_next_run_at=None,
            scheduler_claim_token=None,
            scheduler_claimed_at=None,
            scheduler_lease_expires_at=None,
            terminalized_at=now,
            terminal_side_effects_finalized_at=now,
            updated_at=now,
        )
    )


def upgrade() -> None:
    _retire_tasks(op.get_bind())


def downgrade() -> None:
    # Terminal task state cannot be reconstructed safely.
    pass
