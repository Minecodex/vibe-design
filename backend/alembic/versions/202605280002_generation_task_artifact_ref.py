"""generation task artifact_ref column + index

Revision ID: 202605280002
Revises: 202605280001
Create Date: 2026-05-28 00:02:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202605280002"
down_revision = "202605280001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("artifact_ref", sa.String(length=64), nullable=True),
        )

    _backfill_artifact_ref()

    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.create_index(
            "ix_generation_tasks_artifact_ref",
            ["artifact_ref"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_tasks") as batch_op:
        batch_op.drop_index("ix_generation_tasks_artifact_ref")
        batch_op.drop_column("artifact_ref")


def _backfill_artifact_ref() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute(
            """
            UPDATE generation_tasks
            SET artifact_ref = json_extract(params, '$.artifact_ref')
            WHERE artifact_ref IS NULL
              AND json_extract(params, '$.artifact_ref') IS NOT NULL
            """
        )
        return

    if dialect in {"mysql", "mariadb"}:
        op.execute(
            """
            UPDATE generation_tasks
            SET artifact_ref = JSON_UNQUOTE(JSON_EXTRACT(params, '$.artifact_ref'))
            WHERE artifact_ref IS NULL
              AND JSON_EXTRACT(params, '$.artifact_ref') IS NOT NULL
            """
        )
        return

    if dialect == "postgresql":
        op.execute(
            """
            UPDATE generation_tasks
            SET artifact_ref = params ->> 'artifact_ref'
            WHERE artifact_ref IS NULL
              AND params ->> 'artifact_ref' IS NOT NULL
            """
        )
