"""reserved reference gallery legacy bridge

Revision ID: 202606120002
Revises: 202606110001
Create Date: 2026-06-12 00:00:02.000000

"""
from typing import Sequence, Union


revision: str = "202606120002"
down_revision: Union[str, None] = "202606110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
