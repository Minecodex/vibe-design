"""reference gallery taxonomy

Revision ID: 202606210001
Revises: 202606120002, 202606130001
Create Date: 2026-06-21 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606210001"
down_revision: Union[str, Sequence[str], None] = ("202606120002", "202606130001")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_REFERENCE_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("针织毛衣短袖", ("挂拍3D", "平铺", "老钱风", "无影墙")),
    ("套装", ("光影墙", "立体暖光", "平铺", "情侣")),
    (
        "衬衫",
        (
            "挂拍3D",
            "挂拍商务",
            "挂拍休闲",
            "立体3D",
            "天台风",
            "港风",
            "立体暖光",
            "平铺",
            "无影墙",
            "外景",
            "白墙",
            "镂空",
            "无头模特",
            "户外",
            "天台",
            "毛毯平铺",
            "日系平铺",
            "模特",
        ),
    ),
    (
        "短袖",
        (
            "立体3D",
            "天台风",
            "立体暖光",
            "平铺",
            "山系户外",
            "无影墙",
            "俯拍",
            "白墙",
            "港风",
            "外景",
            "情侣",
            "毛毯",
            "光影墙",
            "灰墙模特",
            "店主风",
            "模特",
            "挂拍",
            "老钱风",
            "街头风",
            "灰墙挂拍",
        ),
    ),
    (
        "防晒衣",
        (
            "无影墙户外",
            "立体暖光",
            "平铺",
            "山系户外",
            "无影墙",
            "男模特",
            "立体3D",
            "情侣模特图",
            "日系平铺",
            "天台模特",
        ),
    ),
    (
        "休闲裤",
        (
            "港风",
            "立体暖光",
            "无影墙",
            "叠脚平铺",
            "平铺",
            "模特",
            "立体3D",
            "地毯",
            "外景",
            "酒店风",
            "红地板",
            "白底",
            "湘湖",
            "叠拍",
            "灰墙黑地",
            "yoa",
            "灰地板",
            "楼梯景",
            "灰背景",
            "天台",
        ),
    ),
    ("马甲", ("JEEP风", "JEEP风露头", "白墙", "平铺", "山系", "无影墙", "港风")),
    (
        "背心",
        ("光影墙", "海景", "黑墙", "黑墙露头", "平铺", "无影墙", "大牌挂拍", "立体暖光", "立体3D"),
    ),
    (
        "短裤",
        (
            "白底平铺",
            "港风",
            "黑地板",
            "无影墙",
            "立体暖光",
            "平铺",
            "山系户外",
            "立体3D",
            "模特",
            "灰墙黑地",
            "灰墙",
            "草地景",
            "红地板",
            "酒店",
            "天台",
            "黑通道",
            "yoa",
            "暖光平铺",
            "白底",
            "灰背景",
            "楼梯景",
        ),
    ),
    ("Polo衫", ("挂拍", "商务", "天台")),
)

DEFAULT_ADMIN_EMAIL = "admin@admin.com"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD_HASH = "$2b$12$Xt/BQ5KUUvrpGZKR/zcir.qytxTaZGgl4vxBWVDVyEaeySWoG1LjC"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def _default_reference_gallery_user_id() -> int:
    bind = op.get_bind()
    user_id = bind.execute(
        sa.text("SELECT id FROM users WHERE role = :role ORDER BY id LIMIT 1"),
        {"role": "admin"},
    ).scalar()
    if user_id is not None:
        return int(user_id)

    user_id = bind.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": DEFAULT_ADMIN_EMAIL},
    ).scalar()
    if user_id is not None:
        return int(user_id)

    bind.execute(
        sa.text(
            "INSERT INTO users (email, username, hashed_password, role, is_active, nickname) "
            "VALUES (:email, :username, :password, :role, :is_active, :nickname)"
        ),
        {
            "email": DEFAULT_ADMIN_EMAIL,
            "username": DEFAULT_ADMIN_USERNAME,
            "password": DEFAULT_ADMIN_PASSWORD_HASH,
            "role": "admin",
            "is_active": True,
            "nickname": DEFAULT_ADMIN_USERNAME,
        },
    )
    return int(
        bind.execute(
            sa.text("SELECT id FROM users WHERE email = :email"),
            {"email": DEFAULT_ADMIN_EMAIL},
        ).scalar_one()
    )


def _seed_default_reference_categories() -> None:
    bind = op.get_bind()
    created_by = _default_reference_gallery_user_id()
    for category_name, subcategory_names in DEFAULT_REFERENCE_CATEGORIES:
        bind.execute(
            sa.text(
                "INSERT INTO reference_categories (created_by, name) "
                "VALUES (:created_by, :name)"
            ),
            {"created_by": created_by, "name": category_name},
        )
        category_id = bind.execute(
            sa.text("SELECT id FROM reference_categories WHERE name = :name"),
            {"name": category_name},
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO reference_subcategories (category_id, created_by, name) "
                "VALUES (:category_id, :created_by, :name)"
            ),
            [
                {
                    "category_id": int(category_id),
                    "created_by": created_by,
                    "name": subcategory_name,
                }
                for subcategory_name in subcategory_names
            ],
        )


def upgrade() -> None:
    _drop_table_if_exists("prompts")
    _drop_table_if_exists("reference_images")
    _drop_table_if_exists("prompt_import_jobs")

    op.create_table(
        "reference_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_reference_categories_name"),
    )
    op.create_index(
        "ix_reference_categories_created_by",
        "reference_categories",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "reference_subcategories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["reference_categories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "category_id",
            "name",
            name="uq_reference_subcategories_category_name",
        ),
    )
    op.create_index(
        "ix_reference_subcategories_category_id",
        "reference_subcategories",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        "ix_reference_subcategories_created_by",
        "reference_subcategories",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "reference_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("subcategory_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subcategory_id"],
            ["reference_subcategories.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reference_images_created_by",
        "reference_images",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_reference_images_subcategory_id",
        "reference_images",
        ["subcategory_id"],
        unique=False,
    )
    _seed_default_reference_categories()


def downgrade() -> None:
    op.drop_index("ix_reference_images_subcategory_id", table_name="reference_images")
    op.drop_index("ix_reference_images_created_by", table_name="reference_images")
    op.drop_table("reference_images")

    op.drop_index("ix_reference_subcategories_created_by", table_name="reference_subcategories")
    op.drop_index("ix_reference_subcategories_category_id", table_name="reference_subcategories")
    op.drop_table("reference_subcategories")

    op.drop_index("ix_reference_categories_created_by", table_name="reference_categories")
    op.drop_table("reference_categories")
