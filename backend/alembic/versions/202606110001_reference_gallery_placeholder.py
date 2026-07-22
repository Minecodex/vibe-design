"""reserved revision before reference gallery

Revision ID: 202606110001
Revises: 202606090001
Create Date: 2026-06-11 00:00:01.000000

"""
from typing import Sequence, Union


revision: str = "202606110001"
down_revision: Union[str, None] = "202606090001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
