"""backfill eligible legacy project asset origins

Revision ID: 202605180003
Revises: 202605180002
Create Date: 2026-05-18 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605180003"
down_revision: Union[str, None] = "202605180002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE project_assets
            SET origin_kind = 'ai_generated'
            WHERE origin_kind = 'legacy'
              AND (
                lower(url) LIKE 'references/generated/%'
                OR lower(url) LIKE '/references/generated/%'
                OR lower(url) LIKE 'assets/references/%'
                OR lower(url) LIKE '/assets/references/%'
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE project_assets
            SET origin_kind = 'local_upload'
            WHERE origin_kind = 'legacy'
              AND (
                lower(url) LIKE 'references/inputs/%'
                OR lower(url) LIKE '/references/inputs/%'
                OR lower(url) LIKE 'references/sources/%'
                OR lower(url) LIKE '/references/sources/%'
                OR lower(url) LIKE 'assets/inputs/%'
                OR lower(url) LIKE '/assets/inputs/%'
              )
            """
        )
    )


def downgrade() -> None:
    pass
