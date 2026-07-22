"""seed_admin_user

Revision ID: b9dd9fbb39c0
Revises: d7e8f9a0b1c2
Create Date: 2026-03-04 20:11:34.573619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9dd9fbb39c0'
down_revision: Union[str, None] = '202603240001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(sa.text("SELECT id FROM users WHERE email = 'admin@admin.com'"))
    if not result.fetchone():
        bind.execute(
            sa.text(
                "INSERT INTO users (email, username, hashed_password, role, is_active, nickname) "
                "VALUES (:email, :username, :pw, :role, :is_active, :nickname)"
            ),
            {
                "email": 'admin@admin.com',
                "username": 'admin',
                "pw": '$2b$12$Xt/BQ5KUUvrpGZKR/zcir.qytxTaZGgl4vxBWVDVyEaeySWoG1LjC',
                "role": 'admin',
                "is_active": True,
                "nickname": 'admin'
            }
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM users WHERE email = 'admin@admin.com'"))
