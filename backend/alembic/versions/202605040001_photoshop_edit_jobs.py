"""add photoshop edit jobs

Revision ID: 202605040001
Revises: 202605070001
Create Date: 2026-05-04 00:01:00
"""

from alembic import op
import sqlalchemy as sa


revision = "202605040001"
down_revision = "202605070001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photoshop_edit_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("request_user_id", sa.Integer(), nullable=False),
        sa.Column("source_canvas_item_id", sa.String(length=255), nullable=False),
        sa.Column("source_asset_id", sa.Integer(), nullable=True),
        sa.Column("svg_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("claimed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("result_asset_id", sa.Integer(), nullable=True),
        sa.Column("result_canvas_item_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["claimed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_asset_id"], ["project_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["project_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("photoshop_edit_jobs")
