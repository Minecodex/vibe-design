"""add conversation event idempotency key

Revision ID: 202605170005
Revises: 202605170004
Create Date: 2026-05-17 22:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605170005"
down_revision: Union[str, None] = "202605170004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversation_events") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint(
            "uq_conversation_events_conversation_idempotency_key",
            ["conversation_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation_events") as batch_op:
        batch_op.drop_constraint(
            "uq_conversation_events_conversation_idempotency_key",
            type_="unique",
        )
        batch_op.drop_column("idempotency_key")
