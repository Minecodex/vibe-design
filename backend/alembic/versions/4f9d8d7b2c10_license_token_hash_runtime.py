"""license_token_hash_runtime

Revision ID: 4f9d8d7b2c10
Revises: b9dd9fbb39c0
Create Date: 2026-03-24 23:35:00.000000

"""

from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa


revision: str = "4f9d8d7b2c10"
down_revision: Union[str, None] = "b9dd9fbb39c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("license_records") as batch_op:
        batch_op.add_column(sa.Column("token_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, license_token FROM license_records")).mappings().all()
    for row in rows:
        token_hash = hashlib.sha256(row["license_token"].strip().encode()).hexdigest()
        bind.execute(
            sa.text("UPDATE license_records SET token_hash = :token_hash WHERE id = :id"),
            {"id": row["id"], "token_hash": token_hash},
        )

    with op.batch_alter_table("license_records") as batch_op:
        batch_op.drop_index("ix_license_records_license_id")
        batch_op.drop_column("license_id")
        batch_op.alter_column("token_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index("ix_license_records_token_hash", ["token_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("license_records") as batch_op:
        batch_op.add_column(sa.Column("license_id", sa.String(length=100), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, token_hash FROM license_records")).mappings().all()
    for row in rows:
        bind.execute(
            sa.text("UPDATE license_records SET license_id = :license_id WHERE id = :id"),
            {"id": row["id"], "license_id": row["token_hash"][:100]},
        )

    with op.batch_alter_table("license_records") as batch_op:
        batch_op.drop_index("ix_license_records_token_hash")
        batch_op.drop_column("token_hash")
        batch_op.alter_column("license_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_index("ix_license_records_license_id", ["license_id"], unique=True)
